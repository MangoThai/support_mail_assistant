from app.rag import build_index, retrieve_snippets

def test_rag_502(tmp_path):
    # index persistant dans un dossier temporaire (pour ne rien salir)
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    res = retrieve_snippets("erreur 502 sur la connexion", k=3, kb_dir="data/kb", persist_dir=str(tmp_path))
    texts = [r["content"].lower() for r in res]
    sources = [r["source"] for r in res]
    assert any("502" in t or "bad gateway" in t for t in texts)
    assert any(s.endswith("incident_502.md") for s in sources)

def test_rag_creation_acces(tmp_path):
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    res = retrieve_snippets("créer un accès utilisateur avec profil standard", k=3, kb_dir="data/kb", persist_dir=str(tmp_path))
    texts = [r["content"].lower() for r in res]
    sources = [r["source"] for r in res]
    assert any("profil standard" in t for t in texts)
    assert any(s.endswith("provisioning_acces.md") for s in sources)

def test_rag_reset_password(tmp_path):
    build_index(kb_dir="data/kb", persist_dir=str(tmp_path))
    res = retrieve_snippets("réinitialiser mot de passe oublié", k=3, kb_dir="data/kb", persist_dir=str(tmp_path))
    texts = [r["content"].lower() for r in res]
    sources = [r["source"] for r in res]
    assert any("lien de réinitialisation" in t for t in texts)
    assert any(s.endswith("reset_mot_de_passe.md") for s in sources)
