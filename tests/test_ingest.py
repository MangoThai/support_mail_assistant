from pathlib import Path
from app.ingest import parse_email_file, load_local_emails, Email


def test_parse_eml_incident():
    p = Path("data/emails/sample_incident.eml")
    e = parse_email_file(p)
    assert isinstance(e, Email)
    assert e.from_ == "client@example.com"
    assert e.to == ["support@acme.test"]
    assert e.subject.startswith("[INCIDENT]")
    assert "erreur 502" in e.body.lower()
    assert e.attachments == []
    assert e.id and len(e.id) == 12


def test_parse_eml_demande_cc():
    p = Path("data/emails/sample_demande.eml")
    e = parse_email_file(p)
    assert e.from_ == "paul.utilisateur@example.com"
    assert "manager@example.com" in e.cc
    assert e.subject.startswith("[DEMANDE]")
    assert "créer un accès" in e.body.lower()


def test_parse_txt_question():
    p = Path("data/emails/sample_question.txt")
    e = parse_email_file(p)
    assert e.from_ == "claire@example.com"
    assert e.to == ["support@acme.test"]
    assert "Question sur la facture" in (e.subject or "")
    assert "#2025-09" in e.body
    assert e.attachments == []


def test_load_local_emails_order_and_count():
    emails = load_local_emails(Path("data/emails"))
    # 3 fichiers créés dans cette étape
    assert len(emails) == 3
    # Les IDs sont uniques (hash contenu)
    assert len({e.id for e in emails}) == 3
