// Edge Worker for matteomastore.com.
//
// Static pages are served straight from the assets directory. Only /api/*
// runs this script first (see run_worker_first in wrangler.jsonc); any other
// request that reaches it is handed back to the asset server unchanged.
//
// POST /api/contact rate limits the caller, validates the form, verifies a
// Cloudflare Turnstile token, and emails the message to the single verified
// destination address configured on the CONTACT_EMAIL send_email binding.
// Nothing is stored.

const CONTACT_PATH = "/api/contact";
const TURNSTILE_ACTION = "contact";
const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const SITEVERIFY_TIMEOUT_MS = 10000;
const MAX_BODY_BYTES = 16 * 1024;
const MAX_TOKEN_LENGTH = 2048;
const MAX_CLIENT_IP_LENGTH = 64;
// The window configured on the CONTACT_RATE_LIMIT binding in wrangler.jsonc.
// Sent as Retry-After so a rate-limited caller knows when to try again; the
// window is public HTTP cache semantics, not an internal detail.
const RATE_LIMIT_WINDOW_SECONDS = "60";
const MAX_LENGTH = { name: 200, email: 320, subject: 300, message: 5000 };
const REQUIRED_MESSAGE = {
  name: "Enter your name.",
  email: "Enter your email.",
  subject: "Enter a subject.",
  message: "Enter a message.",
};
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const CONTROL_RE = /[\x00-\x1f\x7f]/;
const CONTROL_RUN_RE = /[\x00-\x1f\x7f]+/g;

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== CONTACT_PATH) {
      if (url.pathname.startsWith("/api/")) {
        return json(404, { error: "not_found" });
      }
      return env.ASSETS.fetch(request);
    }
    if (request.method !== "POST") {
      return json(405, { error: "method_not_allowed" }, { Allow: "POST" });
    }
    return handleContact(request, env);
  },
};

export async function handleContact(request, env) {
  if (!allowedOrigin(request, env)) {
    return json(403, { error: "forbidden" });
  }

  const contentType = (request.headers.get("Content-Type") || "").toLowerCase();
  if (!contentType.startsWith("application/json")) {
    return json(415, { error: "unsupported_media_type" });
  }

  const declaredLength = Number(request.headers.get("Content-Length") || "0");
  if (declaredLength > MAX_BODY_BYTES) {
    return json(413, { error: "too_large" });
  }

  // Gate order: the three checks above are free header lookups that reject
  // obviously wrong requests, so internet background noise never burns a
  // counter that a real sender behind the same NAT address shares. The limiter
  // then sits immediately before the first expensive step - buffering the body
  // - and well before siteverify, which is a paid subrequest with a network
  // round trip, and before the send_email binding that has the finite quota
  // this is really protecting. Shedding load cheaply is the point.
  if (!(await withinRateLimit(request, env))) {
    return json(429, { error: "rate_limited" }, { "Retry-After": RATE_LIMIT_WINDOW_SECONDS });
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > MAX_BODY_BYTES) {
    return json(413, { error: "too_large" });
  }

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (_error) {
    return json(400, { error: "invalid_json" });
  }

  const { errors, data } = validateContact(payload);
  if (Object.keys(errors).length) {
    return json(400, { error: "invalid", fields: errors });
  }

  if (!env.TURNSTILE_SECRET_KEY) {
    console.error("contact: TURNSTILE_SECRET_KEY is not configured");
    return json(503, { error: "unavailable" });
  }
  if (!(await verifyTurnstile(payload.turnstileToken, request, env))) {
    return json(403, { error: "verification_failed" });
  }

  try {
    await env.CONTACT_EMAIL.send(buildEmail(data, env));
  } catch (error) {
    // Log only the error code: the message body and addresses stay out of logs.
    console.error("contact: send failed", (error && error.code) || "unknown");
    return json(502, { error: "send_failed" });
  }
  return json(200, { status: "ok" });
}

// Second bot gate, behind Turnstile. Turnstile costs an attacker one solve per
// message; a scripted solver can buy those, but it cannot buy time.
//
// The limit is 5 calls per 60 seconds per client IP (see "ratelimits" in
// wrangler.jsonc - the binding supports only a 10s or 60s window). Five is
// chosen so no genuine sender can ever reach it: someone writing one message
// about a job submits it once, and even a double-clicked submit plus two
// corrected validation errors stays under five in the same minute. A solver
// farm trying to drain the send_email quota needs orders of magnitude more
// than five a minute to matter.
//
// FAIL OPEN, deliberately: if the binding is absent or limit() throws, the
// request is allowed through to the remaining gates and the reason is logged.
// Reasoning: this is the owner's only contact route during a job search, and a
// genuine enquiry that is silently refused is gone for good - the sender gets
// a generic failure and no reason to retry. Failing open restores exactly the
// posture this endpoint already ran with in production, which is not "open":
// Turnstile is still verified unconditionally and still fails closed, the
// origin is still pinned, and the mail still goes to one verified address. An
// attacker also cannot reach this path on purpose - the only value they
// influence that gets near limit() is the IP header, which Cloudflare
// overwrites at the edge. Fail closed would mean a tooling or config mismatch
// on a routine push (the "ratelimits" key needs Wrangler 4.36.0+) takes the
// whole contact form down.
//
// Being *over* the limit is the opposite case and does fail closed: 429.
export async function withinRateLimit(request, env) {
  const limiter = env.CONTACT_RATE_LIMIT;
  if (!limiter || typeof limiter.limit !== "function") {
    console.error("contact: rate limit binding missing");
    return true;
  }
  try {
    const { success } = await limiter.limit({ key: rateLimitKey(request) });
    // Only an explicit false rejects, so a malformed result also fails open.
    return success !== false;
  } catch (error) {
    // Log only the error code, like the send path: no keys, no addresses.
    console.error("contact: rate limit check failed", (error && error.code) || "unknown");
    return true;
  }
}

function rateLimitKey(request) {
  // CF-Connecting-IP is written by the edge and cannot be forged by the
  // client. Requests that somehow arrive without it share a single bucket
  // rather than escaping the limit. Control characters are stripped and the
  // value is capped so an unexpected header cannot inflate the key.
  const ip = (request.headers.get("CF-Connecting-IP") || "")
    .replace(CONTROL_RUN_RE, "")
    .trim()
    .slice(0, MAX_CLIENT_IP_LENGTH);
  return `contact:${ip || "unknown"}`;
}

export function validateContact(value) {
  const source = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const errors = {};
  const data = {};

  for (const [field, maximum] of Object.entries(MAX_LENGTH)) {
    const text = typeof source[field] === "string" ? source[field].trim() : "";
    if (!text) {
      errors[field] = REQUIRED_MESSAGE[field];
    } else if (text.length > maximum) {
      errors[field] = `Keep this under ${maximum} characters.`;
    } else {
      data[field] = text;
    }
  }

  if (data.email && (!EMAIL_RE.test(data.email) || CONTROL_RE.test(data.email))) {
    errors.email = "Enter a valid email address.";
  }
  return { errors, data };
}

export async function verifyTurnstile(token, request, env) {
  if (typeof token !== "string" || token.length === 0 || token.length > MAX_TOKEN_LENGTH) {
    return false;
  }
  const hostnames = csv(env.TURNSTILE_HOSTNAMES);
  if (hostnames.size === 0) {
    return false;
  }

  const body = new URLSearchParams({ secret: env.TURNSTILE_SECRET_KEY, response: token });
  const ip = request.headers.get("CF-Connecting-IP");
  if (ip) {
    body.set("remoteip", ip);
  }

  let result;
  try {
    const response = await fetch(SITEVERIFY_URL, {
      method: "POST",
      body,
      signal: AbortSignal.timeout(SITEVERIFY_TIMEOUT_MS),
    });
    if (!response.ok) {
      return false;
    }
    result = await response.json();
  } catch (_error) {
    // Network error, timeout, or a non-JSON body: fail closed.
    return false;
  }
  // A 200 response whose JSON body is literally `null` would make the checks
  // below throw a TypeError outside the try, which escapes as an opaque
  // platform error instead of this function's fail-closed `false`. Guarding
  // the shape cannot change the outcome for any other body: a string, number
  // or array simply has no matching `success`.
  return (
    Boolean(result) &&
    result.success === true &&
    result.action === TURNSTILE_ACTION &&
    hostnames.has(result.hostname)
  );
}

export function buildEmail(data, env) {
  const name = headerSafe(data.name);
  const subject = headerSafe(data.subject);
  return {
    from: { email: env.CONTACT_FROM, name: "matteomastore.com contact form" },
    to: env.CONTACT_TO,
    replyTo: { email: data.email, name },
    subject: `[matteomastore.com] ${subject}`,
    text: [
      `Name: ${name}`,
      `Email: ${data.email}`,
      `Subject: ${subject}`,
      "",
      data.message,
      "",
      "--",
      "Sent from the contact form on matteomastore.com.",
      "Reply to this email to answer the sender directly.",
    ].join("\n"),
  };
}

function headerSafe(text) {
  return text.replace(CONTROL_RUN_RE, " ").trim();
}

function allowedOrigin(request, env) {
  const origin = request.headers.get("Origin");
  return Boolean(origin) && csv(env.ALLOWED_ORIGINS).has(origin);
}

function csv(value) {
  return new Set(
    String(value || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  );
}

function json(status, body, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      ...extraHeaders,
    },
  });
}
