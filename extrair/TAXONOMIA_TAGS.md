# Taxonomia de Tags

Sistema de tags automáticas aplicado em todos os registros (`illustration`, `quote`, `liturgy`, `series`).

## Estrutura
- `type:*`: tipo base do conteúdo (`type:illustration`, `type:quote`, etc.).
- `format:*`: formato editorial (`format:quote`, `form:story`, `form:study`, etc.).
- `theme:*`: tema teológico/pastoral (`theme:faith`, `theme:prayer`, `theme:justice`, etc.).
- `season:*`: calendário cristão (`season:advent`, `season:easter`, etc.).
- `scripture:*`: marcação de uso bíblico (`scripture:referenced`).
- `source:*`: metadados de autoria/citação (`source:author_known`, `source:has_citation`).
- `usage:*`: intenção de uso (`usage:sermon_quote`, `usage:worship_service`, `usage:series_planning`).
- `length:*`: tamanho do texto (`length:short`, `length:medium`, `length:long`).

## Regras mínimas
- Todo registro recebe no mínimo 2 tags.
- O sistema garante sempre:
  - uma tag de `type:*`
  - uma tag adicional estrutural (`format:*`/`source:*`/`length:*`).

## Implementação
- Regras: `extrair/content_taxonomy.py`
- Aplicação em lote: `extrair/apply_taxonomy_tags.py`
- Integração no pipeline de extração: `extrair/extract_content_pipeline.py`
