const SUPABASE_URL = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY;
const SUPABASE_TABLE = process.env.SUPABASE_TABLE || "ilustracaoes_de_sermoes";
const ADMIN_API_TOKEN = process.env.ADMIN_API_TOKEN || "";

function ensureEnv() {
  if (!SUPABASE_URL) {
    throw new Error("Missing SUPABASE_URL");
  }
  if (!SUPABASE_SERVICE_ROLE_KEY) {
    throw new Error("Missing SUPABASE_SERVICE_ROLE_KEY");
  }
}

function buildHeaders(extra = {}) {
  return {
    apikey: SUPABASE_SERVICE_ROLE_KEY,
    Authorization: `Bearer ${SUPABASE_SERVICE_ROLE_KEY}`,
    "Content-Type": "application/json",
    ...extra,
  };
}

function normalizeCsvLike(value) {
  if (value == null) return "";
  if (Array.isArray(value)) return value.map((x) => String(x).trim()).filter(Boolean).join(", ");
  return String(value).trim();
}

function sanitizeRecord(input = {}) {
  const out = { ...input };
  const csvFields = [
    "categories",
    "top_level_categories",
    "bible_references",
    "keywords",
    "auto_tags",
  ];
  for (const field of csvFields) {
    if (field in out) out[field] = normalizeCsvLike(out[field]);
  }

  const dateFields = ["published_at", "updated_at", "created_at"];
  for (const field of dateFields) {
    if (!(field in out)) continue;
    const value = String(out[field] ?? "").trim();
    out[field] = value || null;
  }

  if (!out.uuid && typeof crypto !== "undefined" && crypto.randomUUID) {
    out.uuid = crypto.randomUUID();
  }
  if (!out.created_at) out.created_at = new Date().toISOString();
  if (!out.updated_at) out.updated_at = new Date().toISOString();
  if (!out.published_at) out.published_at = out.created_at;
  if (!out.content_type) out.content_type = "illustration";
  if (!out.title) out.title = "Sem titulo";
  if (!out.author) out.author = "Unknown";
  return out;
}

async function supabaseRequest(path, { method = "GET", query = "", body, prefer } = {}) {
  ensureEnv();
  const url = `${SUPABASE_URL.replace(/\/$/, "")}/rest/v1/${path}${query ? `?${query}` : ""}`;
  const headers = buildHeaders(prefer ? { Prefer: prefer } : {});
  const resp = await fetch(url, {
    method,
    headers,
    body: body == null ? undefined : JSON.stringify(body),
  });
  const text = await resp.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }
  return { resp, data };
}

function json(res, status, payload) {
  res.status(status).setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function verifyAdmin(req) {
  if (!ADMIN_API_TOKEN) return false;
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  return token && token === ADMIN_API_TOKEN;
}

module.exports = {
  SUPABASE_TABLE,
  sanitizeRecord,
  supabaseRequest,
  json,
  verifyAdmin,
};
