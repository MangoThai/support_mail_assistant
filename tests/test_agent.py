from pathlib import Path
from app.ingest import parse_email_file
from app.routing import classify_email
from app.rag import build_index
from app.agent_graph import build_graph, run_turn

def test_agent_reply_with_email(tmp_path):
    # Index KB dans un répertoire temporaire
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    # E-mail d'incident
    email = parse_email_file(Path("data/emails/sample_incident.eml"))
    g = build_graph()
    out = run_turn(g, "erreur 502 sur la connexion", email_obj=email, kb_dir="data/kb", persist_dir=str(tmp_path))
    assert "Sources:" in out
    assert "incident_502.md" in out
    assert "Objet: RE:" in out  # on a formaté une réponse pour l'e-mail

def test_agent_answer_without_email(tmp_path):
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    g = build_graph()
    out = run_turn(g, "réinitialiser mot de passe oublié", email_obj=None, kb_dir="data/kb", persist_dir=str(tmp_path))
    assert "Sources:" in out
    assert "reset_mot_de_passe.md" in out
