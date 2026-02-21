# ilustra-sermao

Pipeline de extração, classificação temática e CRUD de conteúdos para sermões (ilustrações, citações, liturgia e séries), com persistência em SQLite/Supabase e frontend web.

## O que este projeto faz

- Extrai conteúdos da API Storyblok (The Pastor's Workshop).
- Normaliza campos textuais e resolve relações.
- Classifica automaticamente cada registro com tags temáticas (ex.: `tema:fe`, `tema:amor`, `tema:duvida`).
- Gera arquivos de saída (`json`, `jsonl`, `csv`, `sqlite`).
- Permite CRUD completo no Supabase via API serverless.
- Frontend com filtros por tipo, autor, categorias e tags.

## Estrutura principal

- `extrair/extract_content_pipeline.py`: extração consolidada.
- `extrair/content_taxonomy.py`: regras de taxonomia temática.
- `extrair/apply_taxonomy_tags.py`: reaplica classificação em lote.
- `extrair/migrate_to_supabase.py`: migração via REST (Supabase).
- `extrair/migrate_to_postgres_direct.py`: migração direta via Postgres.
- `api/contents.js`: listagem e criação (`GET`, `POST`).
- `api/contents/[uuid].js`: detalhe, edição e exclusão (`GET`, `PATCH`, `DELETE`).
- `index.html`, `app.js`, `styles.css`: frontend.

## Requisitos

- Python 3.10+
- Node.js 20+ (para Vercel/API)
- Conta Supabase com tabela `public.ilustracaoes_de_sermoes`

## 1) Extração de conteúdo

```powershell
python extrair\extract_content_pipeline.py
```

Variáveis úteis:

- `STORYBLOK_TOKEN`
- `PER_PAGE`
- `MAX_WORKERS`
- `MAX_PAGES`
- `OUTPUT_PREFIX` (default: `tpw_content_complete`)
- `FOLDERS` (default: `sermon-illustrations,quotes,liturgy,series`)

## 2) Classificação temática

```powershell
python extrair\apply_taxonomy_tags.py
```

Gera/atualiza o campo `auto_tags` em todos os outputs.

## 3) Supabase: schema da tabela

Rodar no SQL Editor:

- `extrair/supabase_ilustracaoes_de_sermoes.sql`

## 4) Migração para Supabase

### Via REST

```powershell
$env:SUPABASE_URL="https://seu-dominio-supabase"
$env:SUPABASE_SERVICE_ROLE_KEY="sua_service_role_key"
$env:SUPABASE_TABLE="ilustracaoes_de_sermoes"
$env:SOURCE_JSONL="tpw_content_complete.jsonl"
python extrair\migrate_to_supabase.py
```

### Via Postgres direto (alternativa)

```powershell
pip install psycopg[binary]
$env:DATABASE_URL="postgresql://user:pass@host:5432/postgres"
$env:PG_TABLE="public.ilustracaoes_de_sermoes"
$env:SOURCE_JSONL="tpw_content_complete.jsonl"
python extrair\migrate_to_postgres_direct.py
```

## 5) CRUD API + frontend

As rotas CRUD ficam em `/api/contents`.

- `GET /api/contents`
- `POST /api/contents`
- `GET /api/contents/:uuid`
- `PATCH /api/contents/:uuid`
- `DELETE /api/contents/:uuid`

Escrita exige `ADMIN_API_TOKEN` no servidor + `Authorization: Bearer <token>`.

No frontend:

- botão **Modo admin** ativa criação/edição/exclusão.
- filtros por tipo, autor, categoria e tags.

## 6) Deploy no Vercel

Configurar variáveis de ambiente:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_TABLE=ilustracaoes_de_sermoes`
- `ADMIN_API_TOKEN`

`vercel.json` já incluído para runtime Node nas funções.

## Segurança

- Nunca versionar chaves reais.
- Rotacionar credenciais se já foram expostas.
- Usar `ADMIN_API_TOKEN` forte e diferente da chave Supabase.
