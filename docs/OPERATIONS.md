# Operations

## 1) Extração TPW

```powershell
python extrair\extract_content_pipeline.py
```

Saídas esperadas em `data/tpw/` (ou no prefixo configurado por variável de ambiente).

## 2) Extração SermonCentral

```powershell
python sermoncentral\sermoncentral_pipeline.py
```

Saídas esperadas em `data/sermoncentral/`.

## 3) Classificação temática

```powershell
python extrair\apply_taxonomy_tags.py
```

## 4) Migração para Supabase

TPW:

```powershell
python extrair\migrate_to_supabase.py
```

SermonCentral:

```powershell
python sermoncentral\migrate_sermoncentral_to_supabase.py
```

## 5) Frontend e API

Somente frontend estático:

```powershell
python -m http.server 5500
```

Frontend + API Vercel local:

```powershell
vercel dev
```
