-- Cria tabela consolidada para historias/ilustracoes/citacoes/liturgia/series.
-- Nome solicitado: ilustracaoes_de_sermoes
create table if not exists public.ilustracaoes_de_sermoes (
  uuid text primary key,
  story_id bigint,
  slug text,
  url text,
  content_type text,
  source_component text,
  title text,
  author text,
  summary text,
  body_text text,
  citations text,
  canonical_ref text,
  categories text,
  top_level_categories text,
  bible_references text,
  keywords text,
  auto_tags text,
  lang text,
  published_at timestamptz,
  updated_at timestamptz,
  created_at timestamptz,
  ai_text text,
  imported_at timestamptz not null default now()
);

create index if not exists idx_ids_content_type on public.ilustracaoes_de_sermoes(content_type);
create index if not exists idx_ids_author on public.ilustracaoes_de_sermoes(author);
create index if not exists idx_ids_published_at on public.ilustracaoes_de_sermoes(published_at desc);
create index if not exists idx_ids_slug on public.ilustracaoes_de_sermoes(slug);

-- Busca textual simples (opcional)
create extension if not exists pg_trgm;
create index if not exists idx_ids_title_trgm on public.ilustracaoes_de_sermoes using gin (title gin_trgm_ops);
create index if not exists idx_ids_body_trgm on public.ilustracaoes_de_sermoes using gin (body_text gin_trgm_ops);

-- Habilita RLS (recomendado para Supabase)
alter table public.ilustracaoes_de_sermoes enable row level security;

-- Leitura publica (ajuste se necessario)
drop policy if exists "read_ilustracaoes_de_sermoes" on public.ilustracaoes_de_sermoes;
create policy "read_ilustracaoes_de_sermoes"
on public.ilustracaoes_de_sermoes
for select
to anon, authenticated
using (true);

-- Escrita somente via service role no backend/script (nao criar policy de insert para anon)
