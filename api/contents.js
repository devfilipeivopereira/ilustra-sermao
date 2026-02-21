const { SUPABASE_TABLE, sanitizeRecord, supabaseRequest, json, verifyAdmin } = require("./_supabase");

function parseLimit(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.min(n, 20000);
}

module.exports = async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const limit = parseLimit(req.query.limit, 20000);
      const offset = Math.max(0, Number(req.query.offset || 0) || 0);

      const params = new URLSearchParams();
      params.set("select", "*");
      params.set("offset", String(offset));
      params.set("limit", String(limit));
      params.set("order", "published_at.desc.nullslast");

      if (req.query.content_type) params.set("content_type", `eq.${req.query.content_type}`);
      if (req.query.author) params.set("author", `eq.${req.query.author}`);

      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "GET",
        query: params.toString(),
        prefer: "count=exact",
      });

      const contentRange = resp.headers.get("content-range") || "";
      const total = contentRange.includes("/") ? Number(contentRange.split("/")[1]) : null;
      return json(res, resp.status, { rows: Array.isArray(data) ? data : [], total });
    }

    if (req.method === "POST") {
      if (!verifyAdmin(req)) return json(res, 401, { error: "unauthorized" });
      const payload = sanitizeRecord(req.body || {});

      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "POST",
        query: "on_conflict=uuid",
        body: payload,
        prefer: "resolution=merge-duplicates,return=representation",
      });
      return json(res, resp.status, { row: Array.isArray(data) ? data[0] : data });
    }

    return json(res, 405, { error: "method_not_allowed" });
  } catch (error) {
    return json(res, 500, { error: "server_error", detail: String(error.message || error) });
  }
};
