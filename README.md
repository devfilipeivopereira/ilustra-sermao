# ilustra-sermao

Plataforma de extração, classificação temática e CRUD de conteúdos para sermões, com backend em Supabase e frontend web.

## Estrutura do projeto

- `index.html`, `app.js`, `styles.css`: frontend (busca, filtros, seções por tipo e CRUD).
- `api/`: rotas serverless para leitura/escrita no Supabase.
- `extrair/`: pipeline TPW (Storyblok), taxonomia e migração.
- `sermoncentral/`: pipeline SermonCentral e migração.
- `data/`: saídas geradas localmente (`json`, `jsonl`, `csv`, `sqlite`) - ignorado no Git.
- `docs/`: documentação operacional.

## Fluxo recomendado

1. Extrair dados:
   - TPW: `python extrair\extract_content_pipeline.py`
   - SermonCentral: `python sermoncentral\sermoncentral_pipeline.py`
2. Aplicar tags temáticas:
   - `python extrair\apply_taxonomy_tags.py`
3. Criar schema no Supabase:
   - executar `extrair/supabase_ilustracaoes_de_sermoes.sql`
4. Migrar para Supabase:
   - TPW: `python extrair\migrate_to_supabase.py`
   - SermonCentral: `python sermoncentral\migrate_sermoncentral_to_supabase.py`
5. Rodar app:
   - local estático: `python -m http.server 5500`
   - com API local: `vercel dev`

## Variáveis de ambiente

Copie `.env.example` para `.env` e preencha:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_TABLE` (padrão: `ilustracaoes_de_sermoes`)
- `ADMIN_API_TOKEN`
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

## Deploy no Vercel

- Conecte o repositório.
- Configure as variáveis do `.env.example` no painel do Vercel.
- Faça deploy da branch `main`.

## Documentação adicional

- `docs/PROJECT_STRUCTURE.md`
- `docs/OPERATIONS.md`
- `sermoncentral/README.md`
- `extrair/TAXONOMIA_TAGS.md`
