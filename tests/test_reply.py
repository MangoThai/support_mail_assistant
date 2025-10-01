from pathlib import Path
from app.ingest import parse_email_file
from app.routing import classify_email
from app.rag import build_index, retrieve_snippets
from app.reply import build_context, suggest_reply

def test_reply_incident_with_citations(tmp_path):
    # Index RAG temporaire pour tests
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))

    email = parse_email_file(Path("data/emails/sample_incident.eml"))
    routing = classify_email(email)
    snippets = retrieve_snippets("erreur 502 connexion", k=3, kb_dir="data/kb", persist_dir=str(tmp_path))
    ctx = build_context(email, routing_decision=routing, snippets=snippets)

    reply = suggest_reply(email, ctx)
    assert "Objet: RE:" in reply
    assert "1." in reply and "2." in reply
    assert "Sources:" in reply
    assert "incident_502.md" in reply
    assert "Ne partagez jamais de mot de passe en clair" in reply

def test_reply_handles_ids_and_urls(tmp_path):
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    email = parse_email_file(Path("data/emails/sample_question.txt"))
    routing = classify_email(email)
    snippets = retrieve_snippets("facture frais traitement", k=3, kb_dir="data/kb", persist_dir=str(tmp_path))
    ctx = build_context(email, routing_decision=routing, snippets=snippets)
    reply = suggest_reply(email, ctx)
    assert "#2025-09" in reply
