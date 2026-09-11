// Edge Worker for matteomastore.com.
//
// Static pages are served straight from the assets directory. Only /api/*
// runs this script first (see run_worker_first in wrangler.jsonc); any other
// request that reaches it is handed back to the asset server unchanged.
//
// POST /api/contact validates the form, verifies a Cloudflare Turnstile
// token, and emails the message to the single verified destination address
// configured on the CONTACT_EMAIL send_email binding. Nothing is stored.

const CONTACT_PATH = "/api/contact";
const TURNSTILE_ACTION = "contact";
const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";
const SITEVERIFY_TIMEOUT_MS = 10000;
const MAX_BODY_BYTES = 16 * 1024;
const MAX_TOKEN_LENGTH = 2048;
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
  return (
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
