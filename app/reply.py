from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr
from pathlib import Path
from typing import Dict, List, Optional

from app.routing import RoutingDecision, TicketType, Urgency
from app.tools import extract_emails, extract_urls, extract_ids


@dataclass(frozen=True)
class ReplyContext:
    """Contexte minimal et déterministe pour générer une réponse."""
    routing: RoutingDecision
    snippets: List[Dict[str, str]]  # [{"content": ..., "source": ..., "score": "..."}]
    extracted_emails: List[str]
    extracted_urls: List[str]
    extracted_ids: List[str]


def build_context(
    email_obj,
    routing_decision: RoutingDecision,
    snippets: Optional[List[Dict[str, str]]] = None,
) -> ReplyContext:
    """
    Construit un contexte déterministe à partir de l'email + routing + (optionnel) snippets RAG.
    - Pas d'appel réseau. Les snippets doivent être passés (tests) ou calculés en amont.
    """
    text = " ".join([email_obj.subject or "", email_obj.body or ""])
    return ReplyContext(
        routing=routing_decision,
        snippets=snippets or [],
        extracted_emails=extract_emails(text),
        extracted_urls=extract_urls(text),
        extracted_ids=extract_ids(text),
    )


def _guess_salutation(name_or_email: Optional[str]) -> str:
    # Essaie de récupérer le nom affiché si présent, sinon "Bonjour,"
    if not name_or_email:
        return "Bonjour,"
    display, _addr = parseaddr(name_or_email)
    if display:
        first = display.strip().split()[0]
        return f"Bonjour {first},"
    return "Bonjour,"


def _make_steps_from_snippets(snippets: List[Dict[str, str]], fallback_type: TicketType) -> List[str]:
    """
    Extrait des étapes numérotées depuis les snippets.
    Si aucune n'est trouvée, propose un plan générique selon le type.
    """
    steps: List[str] = []
    for sn in snippets:
        content = sn.get("content", "")
        for line in content.splitlines():
            if re.match(r"^\s*\d+\.\s+", line):
                clean = re.sub(r"^\s*", "", line).strip()
                steps.append(clean)
        if len(steps) >= 4:
            break

    if not steps:
        if fallback_type == TicketType.incident:
            steps = [
                "Identifier le périmètre de l'incident (utilisateur impacté, URL, horodatage).",
                "Reproduire l'erreur et collecter les logs pertinents.",
                "Appliquer la procédure de remédiation documentée si disponible.",
                "Escalader au niveau approprié si le blocage persiste.",
            ]
        elif fallback_type == TicketType.demande:
            steps = [
                "Vérifier la complétude de la demande et son éligibilité.",
                "Appliquer la procédure décrite dans la base de connaissances.",
                "Informer le demandeur des délais et validations nécessaires.",
                "Confirmer la bonne exécution et clore la demande.",
            ]
        else:  # question
            steps = [
                "Qualifier la question et vérifier la documentation existante.",
                "Fournir l'explication ou le lien vers la procédure adaptée.",
                "Proposer, si nécessaire, un rendez-vous court pour clarifier.",
            ]
    return steps[:4]


def _sources_block(snippets: List[Dict[str, str]]) -> str:
    if not snippets:
        return "Sources: (aucune référence trouvée)"
    seen = set()
    lines = []
    for sn in snippets:
        src = sn.get("source", "")
        name = Path(src).name if src else "(inconnu)"
        if name not in seen:
            seen.add(name)
            lines.append(f"- {name}")
    return "Sources:\n" + "\n".join(lines)


def _security_note() -> str:
    return (
        "Sécurité : Ne partagez jamais de mot de passe en clair. "
        "Ne communiquez pas d’informations sensibles (clés, tokens) par e-mail."
    )


def suggest_reply(email_obj, ctx: ReplyContext) -> str:
    """
    Génère une réponse professionnelle en français, avec étapes numérotées et citations de sources.
    Déterministe (aucun appel externe).
    """
    subject = email_obj.subject or "(sans objet)"
    salutation = _guess_salutation(email_obj.from_)
    rd = ctx.routing

    # Ouverture selon le type / l’urgence
    opening_parts = [f"{salutation}\n"]
    if rd.type == TicketType.incident:
        if rd.urgency in (Urgency.critique, Urgency.haute):
            opening_parts.append(
                "Nous avons bien pris en compte votre incident et le traitons en priorité."
            )
        else:
            opening_parts.append(
                "Nous avons bien pris en compte votre incident. Voici notre plan d'action."
            )
    elif rd.type == TicketType.demande:
        opening_parts.append("Merci pour votre demande. Voici la procédure envisagée :")
    else:
        opening_parts.append("Merci pour votre message. Voici des éléments de réponse :")

    # Étapes
    steps = _make_steps_from_snippets(ctx.snippets, rd.type)
    steps_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps))

    # Références détectées
    refs_lines: List[str] = []
    if ctx.extracted_ids:
        refs_lines.append("Références détectées : " + ", ".join(ctx.extracted_ids[:5]))
    if ctx.extracted_urls:
        refs_lines.append("Liens mentionnés : " + ", ".join(ctx.extracted_urls[:5]))
    refs_block = "\n".join(refs_lines) if refs_lines else ""

    sources = _sources_block(ctx.snippets)
    security = _security_note()

    body = "\n".join(
        part for part in [
            "".join(opening_parts),
            steps_str,
            refs_block,
            security,
            sources,
            "\nCordialement,\nL'équipe Support",
        ] if part
    )

    return f"Objet: RE: {subject}\n\n{body}\n"
