from __future__ import annotations

import re
from enum import Enum
from typing import List
from pydantic import BaseModel, Field

from app.ingest import Email


class TicketType(str, Enum):
    incident = "incident"
    demande = "demande"
    question = "question"


class Urgency(str, Enum):
    critique = "critique"
    haute = "haute"
    normale = "normale"
    basse = "basse"


class RoutingDecision(BaseModel):
    type: TicketType
    urgency: Urgency
    matched_features: List[str] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)


# --- Règles (regex simples) ---
_INCIDENT_HINTS = [
    r"\bincident\b", r"\bpanne\b", r"\bbug\b", r"\berreur\b",
    r"\bimpossible\b", r"ne\s+(marche|fonctionne)\s+pas", r"\bbloqu(?:e|é|ée|ant|ante)?\b",
    r"\b(?:echec|échec)\b",
]
_DEMANDE_HINTS = [
    r"\bcr[ée]er?\b", r"\bcr[ée]ation\b", r"\bajout(?:er)?\b",
    r"\bacc[eè]s\b", r"\bdemande\b", r"\bactiver?\b", r"\bsuppression\b",
]
_QUESTION_HINTS = [
    r"\?", r"\bpouvez[- ]?vous\b", r"\bcomment\b", r"\bpourquoi\b", r"\bquelle?s?\b",
]

_URGENCY_STRONG = [r"\burgent(?:e|es)?\b", r"\burgence\b", r"\basap\b", r"\bimm[ée]diat(?:e|ement)?\b"]
_URGENCY_BLOCKING = [r"\bcritique\b", r"\bbloqu(?:e|é|ée|ant|ante)?\b", r"\bproduction\b", r"\b(?:en )?panne\b", r"\bdown\b"]
_HTTP_ERROR = r"\b[45]\d\d\b"  # 4xx/5xx


def _search_any(patterns: List[str], text: str, feature_prefix: str, sink: List[str]) -> int:
    count = 0
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            sink.append(f"{feature_prefix}:{p}")        # ex: hint_incident:\bincident\b
    # recompute to avoid double loop:
            count += 1
    return count


def _score_urgency(text: str, features: List[str]) -> int:
    score = 0
    score += 2 * _search_any(_URGENCY_STRONG, text, "urg_strong", features)
    score += 2 * _search_any(_URGENCY_BLOCKING, text, "urg_block", features)
    if re.search(_HTTP_ERROR, text):
        features.append("http_error")
        score += 1
    if re.search(r"\berreur\b", text, re.IGNORECASE):
        features.append("kw:erreur")
        score += 1
    return score


def classify_email(email: Email) -> RoutingDecision:
    text = " ".join(filter(None, [email.subject or "", email.body or ""])).lower()
    features: List[str] = []
    reasons: List[str] = []

    # Type
    subj = (email.subject or "").lower()
    if "[incident]" in subj:
        t = TicketType.incident
        features.append("tag:[INCIDENT]")   # trace brute
        features.append("tag:[incident]")   # version normalisée (pour les tests/filtrages)
    elif "[demande]" in subj:
        t = TicketType.demande
        features.append("tag:[DEMANDE]")
        features.append("tag:[demande]")
    else:
        inc = _search_any(_INCIDENT_HINTS, text, "hint_incident", features)
        dem = _search_any(_DEMANDE_HINTS, text, "hint_demande", features)
        que = _search_any(_QUESTION_HINTS, text, "hint_question", features)
        if inc > dem and inc >= que:
            t = TicketType.incident
        elif dem > inc and dem >= que:
            t = TicketType.demande
        else:
            t = TicketType.question

    # Urgence
    score = _score_urgency(text, features)
    if t == TicketType.incident:
        score += 1

    if score >= 4:
        u = Urgency.critique
    elif score >= 2:
        u = Urgency.haute
    elif t == TicketType.question and score == 0:
        u = Urgency.basse
    else:
        u = Urgency.normale

    # Raisons (audit)
    if "tag:[INCIDENT]" in features or "tag:[incident]" in features:
        reasons.append("Sujet contient [INCIDENT].")
    if "tag:[DEMANDE]" in features or "tag:[demande]" in features:
        reasons.append("Sujet contient [DEMANDE].")
    if any(f.startswith("urg_strong") for f in features):
        reasons.append("Termes d’urgence forts détectés.")
    if any(f.startswith("urg_block") for f in features):
        reasons.append("Termes bloquants/production détectés.")
    if "http_error" in features:
        reasons.append("Code HTTP d’erreur détecté.")
    if "kw:erreur" in features:
        reasons.append("Mot-clé 'erreur' détecté.")

    return RoutingDecision(type=t, urgency=u, matched_features=features, reasons=reasons)