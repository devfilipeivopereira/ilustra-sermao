# Project Structure

## Camadas

- `frontend`: interface estática no root (`index.html`, `app.js`, `styles.css`).
- `api`: rotas serverless para CRUD e integração Supabase.
- `pipelines`: extração e normalização em `extrair/` e `sermoncentral/`.
- `data`: artefatos gerados localmente (não versionados).

## Decisões de organização

- Scripts antigos/duplicados foram removidos para reduzir ambiguidade.
- Apenas pipelines ativos permanecem.
- Dados brutos e exportações ficam fora do versionamento em `data/`.

## Principais pontos de entrada

- Frontend: `index.html`
- API lista/cria: `api/contents.js`
- API detalhe/edita/exclui: `api/contents/[uuid].js`
- Pipeline TPW: `extrair/extract_content_pipeline.py`
- Pipeline SermonCentral: `sermoncentral/sermoncentral_pipeline.py`
