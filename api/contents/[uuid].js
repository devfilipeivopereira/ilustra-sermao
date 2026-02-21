const { SUPABASE_TABLE, sanitizeRecord, supabaseRequest, json, verifyAdmin } = require("../_supabase");

module.exports = async function handler(req, res) {
  const uuid = String(req.query.uuid || "").trim();
  if (!uuid) return json(res, 400, { error: "missing_uuid" });

  try {
    if (req.method === "GET") {
      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "GET",
        query: `select=*&uuid=eq.${encodeURIComponent(uuid)}&limit=1`,
      });
      const row = Array.isArray(data) ? data[0] || null : null;
      return json(res, resp.status, { row });
    }

    if (req.method === "PATCH") {
      if (!verifyAdmin(req)) return json(res, 401, { error: "unauthorized" });
      const payload = sanitizeRecord({ ...(req.body || {}), updated_at: new Date().toISOString() });
      delete payload.uuid;

      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "PATCH",
        query: `uuid=eq.${encodeURIComponent(uuid)}`,
        body: payload,
        prefer: "return=representation",
      });
      const row = Array.isArray(data) ? data[0] || null : data;
      return json(res, resp.status, { row });
    }

    if (req.method === "DELETE") {
      if (!verifyAdmin(req)) return json(res, 401, { error: "unauthorized" });
      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "DELETE",
        query: `uuid=eq.${encodeURIComponent(uuid)}`,
        prefer: "return=representation",
      });
      return json(res, resp.status, { deleted: true, data });
    }

    return json(res, 405, { error: "method_not_allowed" });
  } catch (error) {
    return json(res, 500, { error: "server_error", detail: String(error.message || error) });
  }
};
