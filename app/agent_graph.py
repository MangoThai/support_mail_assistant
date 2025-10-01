from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, TypedDict

from langgraph.graph import StateGraph, END

from app.rag import retrieve_snippets
from app.reply import build_context, suggest_reply
from app.routing import classify_email
from app.ingest import Email


# ------------------ État de l'agent ------------------

class AgentState(TypedDict, total=False):
    query: str
    snippets: List[Dict[str, str]]
    email: Optional[Email]
    reply_text: Optional[str]      # réponse formatée (si e-mail présent)
    final_text: Optional[str]      # fallback quand pas d’e-mail


# ------------------ Nœuds (fonctions pures) ------------------

def node_retrieve(state: AgentState, kb_dir: str = "data/kb", persist_dir: str = "data/chroma") -> AgentState:
    q = state.get("query") or ""
    snips = retrieve_snippets(q, k=3, kb_dir=kb_dir, persist_dir=persist_dir)
    state["snippets"] = snips
    return state


def node_reply(state: AgentState, kb_dir: str = "data/kb", persist_dir: str = "data/chroma") -> AgentState:
    """
    Si un e-mail est chargé, on produit une réponse formatée via notre module reply.
    """
    email = state.get("email")
    snips = state.get("snippets") or []
    if email:
        routing = classify_email(email)
        ctx = build_context(email, routing_decision=routing, snippets=snips)
        state["reply_text"] = suggest_reply(email, ctx)
    return state


def node_format_without_email(state: AgentState) -> AgentState:
    """
    Si aucun e-mail n'est chargé, on renvoie un texte simple basé sur les snippets.
    """
    snips = state.get("snippets") or []
    if not snips:
        state["final_text"] = "Je n'ai trouvé aucune information pertinente dans la base."
        return state

    # Construire une réponse compacte avec citations
    lines = ["Voici des éléments de réponse basés sur la documentation :", ""]
    # Extraire jusqu'à 3 lignes commençant par '1. ', '2. ' etc. si disponibles
    steps: List[str] = []
    for sn in snips:
        for line in sn["content"].splitlines():
            if line.strip().startswith(("1.", "2.", "3.", "4.")):
                steps.append(line.strip())
            if len(steps) >= 4:
                break
        if len(steps) >= 4:
            break
    if steps:
        lines += steps
        lines.append("")

    # Bloc sources
    from pathlib import Path
    seen = set()
    src_lines = []
    for sn in snips:
        name = Path(sn.get("source", "")).name
        if name and name not in seen:
            seen.add(name)
            src_lines.append(f"- {name}")
    if src_lines:
        lines.append("Sources:")
        lines += src_lines

    lines.append("\nCordialement,\nL'équipe Support")
    state["final_text"] = "\n".join(lines)
    return state


# ------------------ Construction du graphe ------------------

def build_graph():
    """
    Graphe minimal :
    START -> retrieve -> [si email] reply -> END
                       -> [sinon] format_without_email -> END
    """
    g = StateGraph(AgentState)

    # Enregistrer les nœuds
    g.add_node("retrieve", node_retrieve)
    g.add_node("reply", node_reply)
    g.add_node("format_without_email", node_format_without_email)

    # Flux : START -> retrieve
    g.set_entry_point("retrieve")

    # Branches conditionnelles après retrieve
    def branch_on_email(state: AgentState):
        return "has_email" if state.get("email") is not None else "no_email"

    g.add_conditional_edges(
        "retrieve",
        branch_on_email,
        {
            "has_email": "reply",
            "no_email": "format_without_email",
        },
    )
    # Sorties
    g.add_edge("reply", END)
    g.add_edge("format_without_email", END)

    return g.compile()


# ------------------ API utilitaire pour la CLI/tests ------------------

def run_turn(graph, query: str, email_obj: Optional[Email], kb_dir: str = "data/kb", persist_dir: str = "data/chroma") -> str:
    """
    Lance un tour de conversation : prend une requête + (optionnel) un e-mail.
    Retourne un texte final (réponse formatée si e-mail, sinon synthèse + sources).
    """
    state: AgentState = {"query": query, "email": email_obj}
    # On peut passer des kwargs aux nœuds via .invoke(input, config={'configurable': {...}})
    out_state: AgentState = graph.invoke(
        state,
        config={"configurable": {"kb_dir": kb_dir, "persist_dir": persist_dir}},
    )

    # Selon le chemin emprunté, 'reply_text' ou 'final_text' sera rempli
    if out_state.get("reply_text"):
        return out_state["reply_text"]
    if out_state.get("final_text"):
        return out_state["final_text"]
    # Cas inattendu : on renvoie un message neutre
    return "Je n'ai pas pu générer de réponse."
