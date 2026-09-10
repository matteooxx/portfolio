import { randomUUID } from "node:crypto";
import { DynamoDBClient } from "@aws-sdk/client-dynamodb";
import { DynamoDBDocumentClient, PutCommand } from "@aws-sdk/lib-dynamodb";
import { SESClient, SendTemplatedEmailCommand } from "@aws-sdk/client-ses";

const REGION = process.env.AWS_REGION || "us-east-1";
const TABLE_NAME = process.env.TABLE_NAME;
const SES_SENDER = process.env.SES_SENDER;
const SES_RECIPIENT = process.env.SES_RECIPIENT;
const SES_TEMPLATE = process.env.SES_TEMPLATE;
const TTL_DAYS = Number(process.env.TTL_DAYS || "90");
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || "http://localhost:8080")
  .split(",")
  .map((value) => value.trim())
  .filter(Boolean);

const ddb = DynamoDBDocumentClient.from(new DynamoDBClient({ region: REGION }));
const ses = new SESClient({ region: REGION });

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_LEN = { name: 200, email: 320, subject: 300, message: 5000 };

function corsHeaders(origin) {
  const headers = {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
    "Vary": "Origin",
  };
  if (origin && ALLOWED_ORIGINS.includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
  }
  return headers;
}

function respond(statusCode, body, origin) {
  return {
    statusCode,
    headers: { "Content-Type": "application/json", ...corsHeaders(origin) },
    body: JSON.stringify(body),
  };
}

function parseBody(event) {
  if (!event) return {};
  // API Gateway proxy event vs direct invoke.
  if (typeof event.body === "string") {
    const raw = event.isBase64Encoded
      ? Buffer.from(event.body, "base64").toString("utf8")
      : event.body;
    return JSON.parse(raw);
  }
  if (event.body && typeof event.body === "object") return event.body;
  return event;
}

function validate(input) {
  const errors = {};
  const data = {};
  for (const field of ["name", "email", "subject", "message"]) {
    const value = typeof input?.[field] === "string" ? input[field].trim() : "";
    if (!value) {
      errors[field] = `${field} is required`;
    } else if (value.length > MAX_LEN[field]) {
      errors[field] = `${field} exceeds ${MAX_LEN[field]} characters`;
    } else {
      data[field] = value;
    }
  }
  if (data.email && !EMAIL_RE.test(data.email)) {
    errors.email = "email is not a valid address";
  }
  return { errors, data };
}

export const handler = async (event) => {
  const headers = event?.headers || {};
  const origin = headers.origin || headers.Origin || "";

  // Preflight.
  const method =
    event?.requestContext?.http?.method || event?.httpMethod || "";
  if (method === "OPTIONS") {
    return { statusCode: 204, headers: corsHeaders(origin), body: "" };
  }

  let input;
  try {
    input = parseBody(event);
  } catch {
    return respond(400, { success: false, error: "Invalid JSON body" }, origin);
  }

  const { errors, data } = validate(input);
  if (Object.keys(errors).length > 0) {
    return respond(400, {
      success: false,
      error: "Validation failed",
      fields: errors,
    }, origin);
  }

  const submissionId = randomUUID();
  const timestamp = new Date().toISOString();
  const expiresAt = Math.floor(Date.now() / 1000) + TTL_DAYS * 86400;

  try {
    await ddb.send(
      new PutCommand({
        TableName: TABLE_NAME,
        Item: {
          submissionId,
          timestamp,
          name: data.name,
          email: data.email,
          subject: data.subject,
          message: data.message,
          expiresAt,
        },
      })
    );
  } catch (err) {
    console.error("DynamoDB PutItem failed", { submissionId, err });
    return respond(500, {
      success: false,
      error: "Failed to record submission",
    }, origin);
  }

  try {
    await ses.send(
      new SendTemplatedEmailCommand({
        Source: SES_SENDER,
        Destination: { ToAddresses: [SES_RECIPIENT] },
        ReplyToAddresses: [data.email],
        Template: SES_TEMPLATE,
        TemplateData: JSON.stringify({
          name: data.name,
          senderEmail: data.email,
          subject: data.subject,
          message: data.message,
          timestamp,
        }),
      })
    );
  } catch (err) {
    // Submission is already persisted; surface as server error so client can retry,
    // but log enough context to reconcile manually if needed.
    console.error("SES SendTemplatedEmail failed", { submissionId, err });
    return respond(500, {
      success: false,
      error: "Failed to send notification email",
      submissionId,
    }, origin);
  }

  return respond(200, {
    success: true,
    message: "Thanks — your message has been received.",
    submissionId,
  }, origin);
};
