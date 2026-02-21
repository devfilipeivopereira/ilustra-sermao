import unicodedata


def _norm(value):
    text = str(value or "").lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text


ESSENCE_THEMES = {
    "tema:fe": [
        "faith",
        "believe",
        "belief",
        "trust",
        "fidelity",
        "confianca em deus",
        "fe",
    ],
    "tema:amor": [
        "love",
        "charity",
        "compassion",
        "kindness",
        "amar",
        "amor",
    ],
    "tema:duvida": [
        "doubt",
        "uncertainty",
        "skeptic",
        "questioning",
        "duvida",
        "incerteza",
    ],
    "tema:esperanca": [
        "hope",
        "future",
        "promise",
        "restoration",
        "esperanca",
        "promessa",
    ],
    "tema:graca": [
        "grace",
        "mercy",
        "undeserved",
        "forgiven",
        "graca",
        "misericordia",
    ],
    "tema:perdao": [
        "forgive",
        "forgiveness",
        "reconcile",
        "reconciliation",
        "perdao",
    ],
    "tema:oracao": [
        "prayer",
        "pray",
        "intercession",
        "amen",
        "oracao",
        "orar",
    ],
    "tema:adoracao": [
        "worship",
        "praise",
        "adoration",
        "call to worship",
        "adoracao",
        "louvor",
    ],
    "tema:sofrimento": [
        "suffering",
        "pain",
        "grief",
        "lament",
        "trauma",
        "sofrimento",
        "dor",
    ],
    "tema:ansiedade_medo": [
        "anxiety",
        "fear",
        "worry",
        "stress",
        "burnout",
        "ansiedade",
        "medo",
    ],
    "tema:sabedoria": [
        "wisdom",
        "wise",
        "fool",
        "prudence",
        "sabedoria",
    ],
    "tema:discipulado": [
        "disciple",
        "follow jesus",
        "obedience",
        "sanctification",
        "discipulado",
    ],
    "tema:evangelismo_missao": [
        "evangelism",
        "gospel",
        "witness",
        "mission",
        "outreach",
        "evangelismo",
        "missao",
    ],
    "tema:igreja_comunidade": [
        "church",
        "congregation",
        "pastor",
        "body of christ",
        "igreja",
        "comunidade",
    ],
    "tema:familia_relacionamentos": [
        "family",
        "parent",
        "mother",
        "father",
        "marriage",
        "children",
        "familia",
        "casamento",
    ],
    "tema:justica_compaixao": [
        "justice",
        "oppressed",
        "racism",
        "equity",
        "poor",
        "justica",
    ],
    "tema:trabalho_dinheiro": [
        "money",
        "wealth",
        "poverty",
        "work",
        "career",
        "success",
        "dinheiro",
        "trabalho",
    ],
    "tema:ressurreicao_vida_nova": [
        "resurrection",
        "risen",
        "empty tomb",
        "new life",
        "easter",
        "ressurreicao",
    ],
    "tema:encarnacao_advento": [
        "incarnation",
        "advent",
        "christmas",
        "nativity",
        "epiphany",
        "encarnacao",
        "advento",
    ],
    "tema:espirito_santo": [
        "holy spirit",
        "spirit of god",
        "pentecost",
        "espirito santo",
    ],
    "tema:reino_de_deus": [
        "kingdom of god",
        "kingdom",
        "reign of god",
        "reino de deus",
    ],
    "tema:arrependimento": [
        "repent",
        "repentance",
        "sin",
        "confession",
        "arrependimento",
        "pecado",
    ],
}


def _score_text(text, terms):
    score = 0
    for term in terms:
        if term in text:
            score += 1
    return score


def classify_record(record):
    title = _norm(record.get("title", ""))
    summary = _norm(record.get("summary", ""))
    body = _norm(record.get("body_text", ""))
    categories = _norm(record.get("categories", ""))
    top_categories = _norm(record.get("top_level_categories", ""))
    keywords = _norm(record.get("keywords", ""))
    citations = _norm(record.get("citations", ""))

    theme_scores = {}
    for theme_tag, terms in ESSENCE_THEMES.items():
        score = 0
        score += _score_text(title, terms) * 4
        score += _score_text(summary, terms) * 3
        score += _score_text(categories, terms) * 3
        score += _score_text(top_categories, terms) * 3
        score += _score_text(keywords, terms) * 2
        score += _score_text(body, terms) * 1
        score += _score_text(citations, terms) * 1
        if score > 0:
            theme_scores[theme_tag] = score

    ranked = sorted(theme_scores.items(), key=lambda item: item[1], reverse=True)
    essence_tags = [tag for tag, score in ranked if score >= 2][:4]

    if not essence_tags and ranked:
        essence_tags = [ranked[0][0]]

    # Garante no minimo duas tags tematicas
    if len(essence_tags) == 0:
        essence_tags = ["tema:vida_crista", "tema:reflexao"]
    elif len(essence_tags) == 1:
        fallback = "tema:vida_crista" if essence_tags[0] != "tema:vida_crista" else "tema:reflexao"
        essence_tags.append(fallback)

    return sorted(set(essence_tags))
