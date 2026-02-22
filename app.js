const SECTION_DEFINITIONS = [
  { id: "all", label: "Tudo" },
  { id: "illustrations", label: "Ilustracoes" },
  { id: "sermons", label: "Sermoes" },
  { id: "series", label: "Series" },
  { id: "quotes", label: "Citacoes" },
  { id: "liturgy", label: "Liturgias" },
  { id: "articles", label: "Artigos" },
  { id: "others", label: "Outros" },
];

const state = {
  rows: [],
  filtered: [],
  selectedCategories: new Set(),
  selectedTags: new Set(),
  selectedType: "",
  selectedAuthor: "",
  search: "",
  sort: "recent",
  currentPage: 1,
  activeRow: null,
  adminEnabled: false,
  adminToken: localStorage.getItem("admin_api_token") || "",
  editingUuid: null,
  currentSection: getInitialSection(),
};

const MAX_CHIPS = 120;
const PAGE_SIZE = 20;

const els = {
  pageTitle: document.querySelector("h1"),
  metaLine: document.getElementById("metaLine"),
  resultCount: document.getElementById("resultCount"),
  cards: document.getElementById("cards"),
  pagination: document.getElementById("pagination"),
  sectionNav: document.getElementById("sectionNav"),
  sectionLinks: Array.from(document.querySelectorAll(".section-link")),
  searchInput: document.getElementById("searchInput"),
  typeSelect: document.getElementById("typeSelect"),
  authorSelect: document.getElementById("authorSelect"),
  sortSelect: document.getElementById("sortSelect"),
  categoryChips: document.getElementById("categoryChips"),
  tagChips: document.getElementById("tagChips"),
  clearFiltersBtn: document.getElementById("clearFiltersBtn"),
  cardTemplate: document.getElementById("cardTemplate"),
  storyModal: document.getElementById("storyModal"),
  closeModalBtn: document.getElementById("closeModalBtn"),
  modalTitle: document.getElementById("modalTitle"),
  modalMeta: document.getElementById("modalMeta"),
  modalSummary: document.getElementById("modalSummary"),
  modalBodyText: document.getElementById("modalBodyText"),
  modalSourceLink: document.getElementById("modalSourceLink"),
  adminModeBtn: document.getElementById("adminModeBtn"),
  newStoryBtn: document.getElementById("newStoryBtn"),
  editStoryBtn: document.getElementById("editStoryBtn"),
  deleteStoryBtn: document.getElementById("deleteStoryBtn"),
  editorModal: document.getElementById("editorModal"),
  editorTitle: document.getElementById("editorTitle"),
  closeEditorBtn: document.getElementById("closeEditorBtn"),
  saveStoryBtn: document.getElementById("saveStoryBtn"),
  f_title: document.getElementById("f_title"),
  f_slug: document.getElementById("f_slug"),
  f_content_type: document.getElementById("f_content_type"),
  f_source_component: document.getElementById("f_source_component"),
  f_author: document.getElementById("f_author"),
  f_url: document.getElementById("f_url"),
  f_lang: document.getElementById("f_lang"),
  f_published_at: document.getElementById("f_published_at"),
  f_summary: document.getElementById("f_summary"),
  f_body_text: document.getElementById("f_body_text"),
  f_categories: document.getElementById("f_categories"),
  f_top_level_categories: document.getElementById("f_top_level_categories"),
  f_bible_references: document.getElementById("f_bible_references"),
  f_keywords: document.getElementById("f_keywords"),
  f_citations: document.getElementById("f_citations"),
  f_canonical_ref: document.getElementById("f_canonical_ref"),
  f_auto_tags: document.getElementById("f_auto_tags"),
};

function getInitialSection() {
  const section = new URLSearchParams(window.location.search).get("secao") || "all";
  return normalizeSection(section);
}

function getSectionLabel(sectionId) {
  return SECTION_DEFINITIONS.find((item) => item.id === sectionId)?.label || "Tudo";
}

function normalizeSection(value) {
  const raw = String(value || "").trim().toLowerCase();
  return SECTION_DEFINITIONS.some((item) => item.id === raw) ? raw : "all";
}

function normalizeType(value) {
  return String(value || "").trim().toLowerCase();
}

function toList(value) {
  if (!value) return [];
  return String(value)
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function isUuidLike(value) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    String(value).trim()
  );
}

function isIllustrationType(type) {
  return type === "illustration" || type.includes("illustration");
}

function isSermonType(type) {
  return type === "sermon" || type.includes("_sermon");
}

function isSeriesType(type) {
  return type === "series" || type.includes("_series");
}

function isQuoteType(type) {
  return type === "quote" || type === "citation" || type.includes("quote") || type.includes("citation");
}

function isLiturgyType(type) {
  return type === "liturgy" || type.includes("liturgy");
}

function isArticleType(type) {
  return type === "article" || type.includes("article");
}

function rowInSection(row, section) {
  const type = normalizeType(row.content_type);
  if (section === "all") return true;
  if (section === "illustrations") return isIllustrationType(type);
  if (section === "sermons") return isSermonType(type);
  if (section === "series") return isSeriesType(type);
  if (section === "quotes") return isQuoteType(type);
  if (section === "liturgy") return isLiturgyType(type);
  if (section === "articles") return isArticleType(type);
  if (section === "others") {
    return !isIllustrationType(type) && !isSermonType(type) && !isSeriesType(type) && !isQuoteType(type) && !isLiturgyType(type) && !isArticleType(type);
  }
  return true;
}

function updateSectionUi() {
  const label = getSectionLabel(state.currentSection);
  els.pageTitle.textContent = `Biblioteca de ${label}`;
  for (const link of els.sectionLinks) {
    const isActive = link.dataset.section === state.currentSection;
    link.classList.toggle("active", isActive);
  }
}

function updateSectionInUrl(push = false) {
  const url = new URL(window.location.href);
  url.searchParams.set("secao", state.currentSection);
  if (push) {
    history.pushState({}, "", url);
  } else {
    history.replaceState({}, "", url);
  }
}

function setSection(section, push = true) {
  const normalized = normalizeSection(section);
  if (state.currentSection === normalized) return;
  state.currentSection = normalized;
  state.selectedType = "";
  els.typeSelect.value = "";
  updateSectionUi();
  updateSectionInUrl(push);
  update(true);
}

function normalizeRow(row) {
  const currentType = normalizeType(row.content_type);
  const inferredType = currentType
    ? currentType
    : String(row.slug || "").startsWith("sermon-illustrations/")
      ? "illustration"
      : "unknown";

  const categoryValues = [...toList(row.categories), ...toList(row.top_level_categories)].filter(
    (item) => !isUuidLike(item)
  );

  return {
    ...row,
    content_type: inferredType,
    categories_list: categoryValues,
    auto_tags_list: toList(row.auto_tags),
    published_ms: row.published_at ? Date.parse(row.published_at) : 0,
    searchable: [
      row.title,
      row.author,
      row.summary,
      row.body_text,
      row.citations,
      row.canonical_ref,
      inferredType,
      row.categories,
      row.auto_tags,
      row.keywords,
      row.bible_references,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase(),
  };
}

async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (state.adminToken) headers.Authorization = `Bearer ${state.adminToken}`;
  const response = await fetch(path, { ...options, headers });
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.error || `HTTP ${response.status}`);
  }
  return data;
}

async function loadDataFromApi() {
  const data = await apiFetch("/api/contents?limit=20000");
  if (!Array.isArray(data?.rows)) throw new Error("Resposta invalida da API.");
  return data.rows.map(normalizeRow);
}

async function loadDataFromFile() {
  const queryDataPath = new URLSearchParams(window.location.search).get("data");
  const tryPaths = queryDataPath
    ? [queryDataPath]
    : [
        "data/sermoncentral/sermoncentral_complete.jsonl",
        "data/sermoncentral/sermoncentral_complete.json",
        "data/tpw/tpw_content_complete.jsonl",
        "data/tpw/tpw_content_complete.json",
        "data/legacy/illustrations_complete.jsonl",
        "data/legacy/illustrations_complete.json",
      ];

  for (const path of tryPaths) {
    try {
      const response = await fetch(path);
      if (!response.ok) continue;

      if (path.endsWith(".jsonl")) {
        const text = await response.text();
        const lines = text.split("\n").filter(Boolean);
        return lines.map((line) => normalizeRow(JSON.parse(line)));
      }

      const data = await response.json();
      if (Array.isArray(data)) {
        return data.map(normalizeRow);
      }
    } catch (error) {
      console.warn(`Falha ao ler ${path}`, error);
    }
  }

  throw new Error("Nao foi possivel carregar dados locais.");
}

async function loadData() {
  try {
    return await loadDataFromApi();
  } catch (error) {
    console.warn("API indisponivel. Usando arquivos locais.", error);
    return loadDataFromFile();
  }
}

function getRowsInCurrentSection(rows = state.rows) {
  return rows.filter((row) => rowInSection(row, state.currentSection));
}

function fillAuthorFilter(rows) {
  const sectionRows = getRowsInCurrentSection(rows);
  const authors = [...new Set(sectionRows.map((row) => row.author).filter(Boolean))].sort();
  els.authorSelect.innerHTML = '<option value="">Todos os autores</option>';
  const fragment = document.createDocumentFragment();
  for (const author of authors) {
    const option = document.createElement("option");
    option.value = author;
    option.textContent = author;
    fragment.append(option);
  }
  els.authorSelect.append(fragment);
  if (state.selectedAuthor && !authors.includes(state.selectedAuthor)) {
    state.selectedAuthor = "";
    els.authorSelect.value = "";
  }
}

function fillTypeFilter(rows) {
  const types = [...new Set(rows.map((row) => row.content_type).filter(Boolean))].sort();
  els.typeSelect.innerHTML = '<option value="">Todos os tipos da secao</option>';
  const fragment = document.createDocumentFragment();
  for (const type of types) {
    const option = document.createElement("option");
    option.value = type;
    option.textContent = type;
    fragment.append(option);
  }
  els.typeSelect.append(fragment);
  if (state.selectedType && !types.includes(state.selectedType)) {
    state.selectedType = "";
    els.typeSelect.value = "";
  }
}

function buildChips(container, values, selectedSet) {
  container.innerHTML = "";
  const fragment = document.createDocumentFragment();
  for (const value of values.slice(0, MAX_CHIPS)) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter-chip${selectedSet.has(value) ? " active" : ""}`;
    button.textContent = value;
    button.dataset.value = value;
    button.addEventListener("click", () => {
      if (selectedSet.has(value)) {
        selectedSet.delete(value);
      } else {
        selectedSet.add(value);
      }
      update(true);
    });
    fragment.append(button);
  }
  container.append(fragment);
}

function bySort(a, b) {
  if (state.sort === "oldest") return a.published_ms - b.published_ms;
  if (state.sort === "title") return (a.title || "").localeCompare(b.title || "");
  return b.published_ms - a.published_ms;
}

function applyFilters() {
  const query = state.search.trim().toLowerCase();

  state.filtered = state.rows
    .filter((row) => {
      if (!rowInSection(row, state.currentSection)) return false;
      if (state.selectedType && row.content_type !== state.selectedType) return false;
      if (state.selectedAuthor && row.author !== state.selectedAuthor) return false;
      if (state.selectedCategories.size > 0) {
        const hasCategory = row.categories_list.some((item) => state.selectedCategories.has(item));
        if (!hasCategory) return false;
      }
      if (state.selectedTags.size > 0) {
        const hasTag = row.auto_tags_list.some((item) => state.selectedTags.has(item));
        if (!hasTag) return false;
      }
      if (query && !row.searchable.includes(query)) return false;
      return true;
    })
    .sort(bySort);
}

function setAdminUi() {
  const display = state.adminEnabled ? "inline-flex" : "none";
  els.newStoryBtn.style.display = display;
  els.editStoryBtn.style.display = display;
  els.deleteStoryBtn.style.display = display;
  els.adminModeBtn.textContent = state.adminEnabled ? "Admin ativo" : "Modo admin";
}

function openStoryModal(row) {
  state.activeRow = row;
  els.modalTitle.textContent = row.title || "Sem titulo";
  const pieces = [];
  if (row.content_type) pieces.push(`Tipo: ${row.content_type}`);
  if (row.author) pieces.push(`Autor: ${row.author}`);
  if (row.published_at) pieces.push(`Publicado em: ${new Date(row.published_at).toLocaleDateString("pt-BR")}`);
  if (row.categories) pieces.push(`Categorias: ${row.categories}`);
  if (row.auto_tags) pieces.push(`Tags: ${row.auto_tags}`);
  els.modalMeta.textContent = pieces.join(" | ");
  els.modalSummary.textContent = row.summary?.trim() ? row.summary.trim() : "";
  const fullText = row.body_text?.trim() || row.ai_text?.trim() || "Sem conteudo textual completo.";
  els.modalBodyText.textContent = fullText;
  if (row.url) {
    els.modalSourceLink.href = row.url;
    els.modalSourceLink.style.display = "inline-flex";
  } else {
    els.modalSourceLink.removeAttribute("href");
    els.modalSourceLink.style.display = "none";
  }
  if (typeof els.storyModal.showModal === "function") els.storyModal.showModal();
}

function renderPagination(totalPages) {
  els.pagination.innerHTML = "";
  if (totalPages <= 1) return;
  const fragment = document.createDocumentFragment();
  const prev = document.createElement("button");
  prev.className = "page-btn";
  prev.textContent = "Anterior";
  prev.disabled = state.currentPage === 1;
  prev.addEventListener("click", () => {
    if (state.currentPage > 1) {
      state.currentPage -= 1;
      update(false);
    }
  });
  fragment.append(prev);
  const windowSize = 5;
  const startPage = Math.max(1, state.currentPage - 2);
  const endPage = Math.min(totalPages, startPage + windowSize - 1);
  const adjustedStart = Math.max(1, endPage - windowSize + 1);
  for (let page = adjustedStart; page <= endPage; page += 1) {
    const btn = document.createElement("button");
    btn.className = `page-btn${page === state.currentPage ? " active" : ""}`;
    btn.textContent = String(page);
    btn.addEventListener("click", () => {
      state.currentPage = page;
      update(false);
    });
    fragment.append(btn);
  }
  const next = document.createElement("button");
  next.className = "page-btn";
  next.textContent = "Proxima";
  next.disabled = state.currentPage === totalPages;
  next.addEventListener("click", () => {
    if (state.currentPage < totalPages) {
      state.currentPage += 1;
      update(false);
    }
  });
  fragment.append(next);
  els.pagination.append(fragment);
}

function renderCards() {
  els.cards.innerHTML = "";
  els.pagination.innerHTML = "";
  if (state.filtered.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "Nenhum resultado com os filtros atuais.";
    els.cards.append(empty);
    return;
  }
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  if (state.currentPage > totalPages) state.currentPage = totalPages;
  const start = (state.currentPage - 1) * PAGE_SIZE;
  const end = start + PAGE_SIZE;
  const fragment = document.createDocumentFragment();
  for (const [index, row] of state.filtered.slice(start, end).entries()) {
    const clone = els.cardTemplate.content.cloneNode(true);
    const card = clone.querySelector(".card");
    card.style.animationDelay = `${Math.min(index * 16, 320)}ms`;
    clone.querySelector(".card-title").textContent = row.title || "Sem titulo";
    clone.querySelector(".date-pill").textContent = row.published_at
      ? new Date(row.published_at).toLocaleDateString("pt-BR")
      : "Sem data";
    clone.querySelector(".card-meta").textContent = `Autor: ${row.author || "Desconhecido"}`;
    const summary = row.summary?.trim();
    const body = row.body_text?.trim();
    const text = summary || body || "Sem conteudo textual.";
    clone.querySelector(".card-body").textContent = text.slice(0, 360) + (text.length > 360 ? "..." : "");
    const categoryRow = clone.querySelector(".pill-row.categories");
    row.categories_list.slice(0, 4).forEach((item) => {
      const span = document.createElement("span");
      span.className = "pill";
      span.textContent = item;
      categoryRow.append(span);
    });
    const link = clone.querySelector(".card-link");
    link.href = row.url || "#";
    link.textContent = row.url ? "Abrir link externo" : "Sem URL";
    link.addEventListener("click", (event) => event.stopPropagation());
    card.addEventListener("click", () => openStoryModal(row));
    fragment.append(clone);
  }
  els.cards.append(fragment);
  renderPagination(totalPages);
}

function updateCounters() {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  const sectionLabel = getSectionLabel(state.currentSection);
  els.resultCount.textContent = `${state.filtered.length} resultados em ${sectionLabel} | pagina ${state.currentPage} de ${totalPages}`;
}

function updateMetaLine() {
  const sectionRows = getRowsInCurrentSection();
  els.metaLine.textContent = `${state.rows.length.toLocaleString("pt-BR")} historias carregadas | ${sectionRows.length.toLocaleString("pt-BR")} na secao atual.`;
}

function update(resetPage = true) {
  if (resetPage) state.currentPage = 1;
  const sectionRows = getRowsInCurrentSection();
  fillTypeFilter(sectionRows);
  fillAuthorFilter(state.rows);
  applyFilters();
  const activeCategories = [...new Set(sectionRows.flatMap((row) => row.categories_list))]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
  buildChips(els.categoryChips, activeCategories, state.selectedCategories);
  const activeTags = [...new Set(sectionRows.flatMap((row) => row.auto_tags_list))]
    .filter(Boolean)
    .sort((a, b) => a.localeCompare(b));
  buildChips(els.tagChips, activeTags, state.selectedTags);
  renderCards();
  updateCounters();
  updateMetaLine();
}

function getDefaultEditorType() {
  if (state.currentSection === "illustrations") return "illustration";
  if (state.currentSection === "sermons") return "sermon";
  if (state.currentSection === "series") return "series";
  if (state.currentSection === "quotes") return "quote";
  if (state.currentSection === "liturgy") return "liturgy";
  if (state.currentSection === "articles") return "article";
  return "illustration";
}

function openEditor(row = null) {
  state.editingUuid = row?.uuid || null;
  els.editorTitle.textContent = row ? "Editar historia" : "Nova historia";
  els.f_title.value = row?.title || "";
  els.f_slug.value = row?.slug || "";
  els.f_content_type.value = row?.content_type || getDefaultEditorType();
  els.f_source_component.value = row?.source_component || "";
  els.f_author.value = row?.author || "";
  els.f_url.value = row?.url || "";
  els.f_lang.value = row?.lang || "";
  els.f_published_at.value = row?.published_at || "";
  els.f_summary.value = row?.summary || "";
  els.f_body_text.value = row?.body_text || "";
  els.f_categories.value = row?.categories || "";
  els.f_top_level_categories.value = row?.top_level_categories || "";
  els.f_bible_references.value = row?.bible_references || "";
  els.f_keywords.value = row?.keywords || "";
  els.f_citations.value = row?.citations || "";
  els.f_canonical_ref.value = row?.canonical_ref || "";
  els.f_auto_tags.value = row?.auto_tags || "";
  els.editorModal.showModal();
}

function readEditorPayload() {
  return {
    title: els.f_title.value.trim(),
    slug: els.f_slug.value.trim(),
    content_type: els.f_content_type.value.trim(),
    source_component: els.f_source_component.value.trim(),
    author: els.f_author.value.trim(),
    url: els.f_url.value.trim(),
    lang: els.f_lang.value.trim(),
    published_at: els.f_published_at.value.trim(),
    summary: els.f_summary.value.trim(),
    body_text: els.f_body_text.value.trim(),
    categories: els.f_categories.value.trim(),
    top_level_categories: els.f_top_level_categories.value.trim(),
    bible_references: els.f_bible_references.value.trim(),
    keywords: els.f_keywords.value.trim(),
    citations: els.f_citations.value.trim(),
    canonical_ref: els.f_canonical_ref.value.trim(),
    auto_tags: els.f_auto_tags.value.trim(),
    updated_at: new Date().toISOString(),
  };
}

async function saveStory() {
  const payload = readEditorPayload();
  if (!payload.title) {
    alert("Titulo e obrigatorio.");
    return;
  }
  if (!payload.auto_tags || toList(payload.auto_tags).length < 2) {
    alert("Informe pelo menos duas tags tematicas.");
    return;
  }
  try {
    if (state.editingUuid) {
      await apiFetch(`/api/contents/${encodeURIComponent(state.editingUuid)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      await apiFetch("/api/contents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    els.editorModal.close();
    await refreshData();
  } catch (error) {
    alert(`Erro ao salvar: ${error.message}`);
  }
}

async function deleteStory() {
  if (!state.activeRow?.uuid) return;
  if (!confirm(`Excluir "${state.activeRow.title || state.activeRow.uuid}"?`)) return;
  try {
    await apiFetch(`/api/contents/${encodeURIComponent(state.activeRow.uuid)}`, { method: "DELETE" });
    els.storyModal.close();
    await refreshData();
  } catch (error) {
    alert(`Erro ao excluir: ${error.message}`);
  }
}

async function refreshData() {
  const rows = await loadData();
  state.rows = rows;
  updateSectionUi();
  updateSectionInUrl(false);
  update(true);
}

function wireEvents() {
  els.sectionLinks.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      setSection(link.dataset.section, true);
    });
  });

  window.addEventListener("popstate", () => {
    const section = new URLSearchParams(window.location.search).get("secao") || "all";
    state.currentSection = normalizeSection(section);
    updateSectionUi();
    update(true);
  });

  els.searchInput.addEventListener("input", (event) => {
    state.search = event.target.value;
    update(true);
  });
  els.typeSelect.addEventListener("change", (event) => {
    state.selectedType = event.target.value;
    update(true);
  });
  els.authorSelect.addEventListener("change", (event) => {
    state.selectedAuthor = event.target.value;
    update(true);
  });
  els.sortSelect.addEventListener("change", (event) => {
    state.sort = event.target.value;
    update(true);
  });
  els.clearFiltersBtn.addEventListener("click", () => {
    state.search = "";
    state.selectedType = "";
    state.selectedAuthor = "";
    state.selectedCategories.clear();
    state.selectedTags.clear();
    state.sort = "recent";
    els.searchInput.value = "";
    els.typeSelect.value = "";
    els.authorSelect.value = "";
    els.sortSelect.value = "recent";
    update(true);
  });
  els.closeModalBtn.addEventListener("click", () => els.storyModal.close());
  els.storyModal.addEventListener("click", (event) => {
    const rect = els.storyModal.getBoundingClientRect();
    const inside =
      event.clientX >= rect.left &&
      event.clientX <= rect.right &&
      event.clientY >= rect.top &&
      event.clientY <= rect.bottom;
    if (!inside) els.storyModal.close();
  });
  els.adminModeBtn.addEventListener("click", () => {
    const current = state.adminToken || "";
    const token = prompt("Informe ADMIN_API_TOKEN (deixe vazio para sair):", current);
    if (token === null) return;
    state.adminToken = token.trim();
    if (state.adminToken) localStorage.setItem("admin_api_token", state.adminToken);
    else localStorage.removeItem("admin_api_token");
    state.adminEnabled = !!state.adminToken;
    setAdminUi();
  });
  els.newStoryBtn.addEventListener("click", () => openEditor());
  els.editStoryBtn.addEventListener("click", () => {
    if (!state.activeRow) return;
    openEditor(state.activeRow);
  });
  els.deleteStoryBtn.addEventListener("click", deleteStory);
  els.closeEditorBtn.addEventListener("click", () => els.editorModal.close());
  els.saveStoryBtn.addEventListener("click", saveStory);
}

async function boot() {
  try {
    state.adminEnabled = !!state.adminToken;
    setAdminUi();
    updateSectionUi();
    wireEvents();
    await refreshData();
  } catch (error) {
    els.metaLine.textContent = "Erro ao carregar dados.";
    els.cards.innerHTML = `<div class="empty-state">${error.message}<br/>Rode com servidor local: <code>python -m http.server 5500</code></div>`;
  }
}

boot();
