// Tests for worker/index.mjs. Run with: node --test tests/worker.test.mjs
// No network: siteverify is replaced by a stub and the email binding records
// what it would send.

import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import worker from "../worker/index.mjs";

const realFetch = globalThis.fetch;

const VALID = {
  name: "Test User",
  email: "test@example.com",
  subject: "Hello",
  message: "A test message",
  turnstileToken: "token-123",
};

const PASS = { success: true, action: "contact", hostname: "matteomastore.com" };

afterEach(() => {
  globalThis.fetch = realFetch;
});

function makeEnv(overrides = {}) {
  const sent = [];
  const env = {
    TURNSTILE_SECRET_KEY: "test-secret",
    TURNSTILE_HOSTNAMES: "matteomastore.com",
    ALLOWED_ORIGINS: "https://matteomastore.com",
    CONTACT_FROM: "contact@matteomastore.com",
    CONTACT_TO: "owner@example.com",
    CONTACT_EMAIL: {
      async send(message) {
        sent.push(message);
        return { messageId: "message-1" };
      },
    },
    ASSETS: {
      async fetch() {
        return new Response("asset", { status: 200 });
      },
    },
    ...overrides,
  };
  return { env, sent };
}

function contactRequest(body, headers = {}) {
  return new Request("https://matteomastore.com/api/contact", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: "https://matteomastore.com",
      "CF-Connecting-IP": "203.0.113.7",
      ...headers,
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

function stubSiteverify(result, { ok = true, fail = false } = {}) {
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), body: new URLSearchParams(init.body) });
    if (fail) {
      throw new Error("network down");
    }
    return new Response(JSON.stringify(result), { status: ok ? 200 : 500 });
  };
  return calls;
}

test("sends a verified message to the configured destination", async () => {
  const calls = stubSiteverify(PASS);
  const { env, sent } = makeEnv();

  const response = await worker.fetch(contactRequest(VALID), env);

  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://challenges.cloudflare.com/turnstile/v0/siteverify");
  assert.equal(calls[0].body.get("secret"), "test-secret");
  assert.equal(calls[0].body.get("response"), "token-123");
  assert.equal(calls[0].body.get("remoteip"), "203.0.113.7");
  assert.equal(sent.length, 1);
  assert.equal(sent[0].to, "owner@example.com");
  assert.equal(sent[0].from.email, "contact@matteomastore.com");
  assert.deepEqual(sent[0].replyTo, { email: "test@example.com", name: "Test User" });
  assert.equal(sent[0].subject, "[matteomastore.com] Hello");
  assert.match(sent[0].text, /A test message/);
});

test("strips control characters from header fields", async () => {
  stubSiteverify(PASS);
  const { env, sent } = makeEnv();

  const response = await worker.fetch(
    contactRequest({ ...VALID, name: "Eve\r\nBcc: x@example.com", subject: "Hi\nthere" }),
    env,
  );

  assert.equal(response.status, 200);
  assert.doesNotMatch(sent[0].replyTo.name, /[\r\n]/);
  assert.doesNotMatch(sent[0].subject, /[\r\n]/);
});

test("rejects other origins before calling siteverify", async () => {
  const calls = stubSiteverify(PASS);
  const { env, sent } = makeEnv();

  const response = await worker.fetch(
    contactRequest(VALID, { Origin: "https://evil.example" }),
    env,
  );

  assert.equal(response.status, 403);
  assert.equal(calls.length, 0);
  assert.equal(sent.length, 0);
});

test("accepts only POST", async () => {
  const { env } = makeEnv();
  const response = await worker.fetch(
    new Request("https://matteomastore.com/api/contact"),
    env,
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("Allow"), "POST");
});

test("accepts only JSON bodies", async () => {
  const { env } = makeEnv();
  const response = await worker.fetch(
    contactRequest("name=x", { "Content-Type": "application/x-www-form-urlencoded" }),
    env,
  );
  assert.equal(response.status, 415);
});

test("rejects oversized bodies", async () => {
  const { env, sent } = makeEnv();
  const response = await worker.fetch(
    contactRequest({ ...VALID, message: "x".repeat(20000) }),
    env,
  );
  assert.equal(response.status, 413);
  assert.equal(sent.length, 0);
});

test("returns field errors for invalid input", async () => {
  const calls = stubSiteverify(PASS);
  const { env } = makeEnv();

  const response = await worker.fetch(
    contactRequest({ ...VALID, email: "not-an-email", subject: "  " }),
    env,
  );

  assert.equal(response.status, 400);
  const body = await response.json();
  assert.equal(body.fields.email, "Enter a valid email address.");
  assert.equal(body.fields.subject, "Enter a subject.");
  assert.equal(calls.length, 0);
});

test("rejects a missing Turnstile token without calling siteverify", async () => {
  const calls = stubSiteverify(PASS);
  const { env, sent } = makeEnv();

  const { turnstileToken: _omit, ...withoutToken } = VALID;
  const response = await worker.fetch(contactRequest(withoutToken), env);

  assert.equal(response.status, 403);
  assert.equal(calls.length, 0);
  assert.equal(sent.length, 0);
});

test("rejects failed, wrong-action, and wrong-hostname verifications", async () => {
  for (const result of [
    { ...PASS, success: false },
    { ...PASS, action: "login" },
    { ...PASS, hostname: "evil.example" },
  ]) {
    stubSiteverify(result);
    const { env, sent } = makeEnv();
    const response = await worker.fetch(contactRequest(VALID), env);
    assert.equal(response.status, 403, JSON.stringify(result));
    assert.equal(sent.length, 0);
  }
});

test("fails closed when siteverify is unreachable or errors", async () => {
  for (const options of [{ fail: true }, { ok: false }]) {
    stubSiteverify(PASS, options);
    const { env, sent } = makeEnv();
    const response = await worker.fetch(contactRequest(VALID), env);
    assert.equal(response.status, 403);
    assert.equal(sent.length, 0);
  }
});

test("reports an unconfigured secret as unavailable", async () => {
  const calls = stubSiteverify(PASS);
  const { env, sent } = makeEnv({ TURNSTILE_SECRET_KEY: "" });

  const response = await worker.fetch(contactRequest(VALID), env);

  assert.equal(response.status, 503);
  assert.equal(calls.length, 0);
  assert.equal(sent.length, 0);
});

test("reports a send failure without leaking details", async () => {
  stubSiteverify(PASS);
  const { env } = makeEnv({
    CONTACT_EMAIL: {
      async send() {
        const error = new Error("boom");
        error.code = "E_RATE_LIMIT_EXCEEDED";
        throw error;
      },
    },
  });
  const originalError = console.error;
  console.error = () => {};
  try {
    const response = await worker.fetch(contactRequest(VALID), env);
    assert.equal(response.status, 502);
    assert.deepEqual(await response.json(), { error: "send_failed" });
  } finally {
    console.error = originalError;
  }
});

test("hands non-API paths to the asset server and 404s unknown API paths", async () => {
  const { env } = makeEnv();

  const page = await worker.fetch(new Request("https://matteomastore.com/about"), env);
  assert.equal(page.status, 200);
  assert.equal(await page.text(), "asset");

  const unknown = await worker.fetch(new Request("https://matteomastore.com/api/other"), env);
  assert.equal(unknown.status, 404);
});
