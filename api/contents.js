const { SUPABASE_TABLE, sanitizeRecord, supabaseRequest, json, verifyAdmin } = require("./_supabase");

function parseLimit(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.min(n, 100);
}

function parseOffset(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return 0;
  return Math.floor(n);
}

function normalizeSort(value) {
  const sort = String(value || "recent").trim().toLowerCase();
  if (sort === "oldest") return "published_at.asc.nullsfirst";
  if (sort === "title") return "title.asc.nullslast";
  return "published_at.desc.nullslast";
}

function normalizeSection(value) {
  return String(value || "all").trim().toLowerCase();
}

function sectionTypes(section) {
  const map = {
    illustrations: ["illustration", "sermoncentral_illustration"],
    sermons: ["sermon", "sermoncentral_sermon"],
    series: ["series", "sermoncentral_series"],
    quotes: ["quote", "citation"],
    liturgy: ["liturgy"],
    articles: ["article", "sermoncentral_article"],
  };
  return map[section] || [];
}

function escapeLike(value) {
  return String(value || "")
    .replace(/[%_]/g, " ")
    .replace(/[(),]/g, " ")
    .trim();
}

function toInList(values) {
  return values.map((v) => `"${String(v).replace(/"/g, "")}"`).join(",");
}

module.exports = async function handler(req, res) {
  try {
    if (req.method === "GET") {
      const limit = parseLimit(req.query.limit, 20);
      const offset = parseOffset(req.query.offset);
      const sort = normalizeSort(req.query.sort);
      const section = normalizeSection(req.query.section);
      const search = escapeLike(req.query.search || "");

      const params = new URLSearchParams();
      params.set(
        "select",
        "uuid,slug,url,content_type,source_component,title,author,summary,categories,top_level_categories,auto_tags,lang,published_at,updated_at,created_at"
      );
      params.set("offset", String(offset));
      params.set("limit", String(limit));
      params.set("order", sort);

      if (req.query.content_type) params.set("content_type", `eq.${req.query.content_type}`);
      if (req.query.author) params.set("author", `eq.${req.query.author}`);
      if (search) {
        params.set(
          "or",
          `title.ilike.*${search}*,summary.ilike.*${search}*,author.ilike.*${search}*,categories.ilike.*${search}*,auto_tags.ilike.*${search}*`
        );
      }

      const types = sectionTypes(section);
      if (section === "others") {
        const known = [
          "illustration",
          "sermoncentral_illustration",
          "sermon",
          "sermoncentral_sermon",
          "series",
          "sermoncentral_series",
          "quote",
          "citation",
          "liturgy",
          "article",
          "sermoncentral_article",
        ];
        params.set("content_type", `not.in.(${toInList(known)})`);
      } else if (types.length > 0 && !req.query.content_type) {
        params.set("content_type", `in.(${toInList(types)})`);
      }

      const { resp, data } = await supabaseRequest(SUPABASE_TABLE, {
        method: "GET",
        query: params.toString(),
        prefer: "count=exact",
      });

      const contentRange = resp.headers.get("content-range") || "";
      const total = contentRange.includes("/") ? Number(contentRange.split("/")[1]) : null;
      res.setHeader("Cache-Control", "s-maxage=60, stale-while-revalidate=300");
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
