from pathlib import Path
from app.ingest import parse_email_file
from app.routing import classify_email, TicketType, Urgency

def test_routing_incident_critique():
    e = parse_email_file(Path("data/emails/sample_incident.eml"))
    r = classify_email(e)
    assert r.type == TicketType.incident
    assert r.urgency == Urgency.critique
    assert any("incident" in x for x in r.matched_features)

def test_routing_demande_normale():
    e = parse_email_file(Path("data/emails/sample_demande.eml"))
    r = classify_email(e)
    assert r.type == TicketType.demande
    assert r.urgency == Urgency.normale

def test_routing_question_basse():
    e = parse_email_file(Path("data/emails/sample_question.txt"))
    r = classify_email(e)
    assert r.type == TicketType.question
    assert r.urgency == Urgency.basse

def test_routing_fallback_question_basse():
    from app.routing import RoutingDecision
    from app.ingest import Email
    e = Email(
        id="x", raw_path="mem",
        from_="a@b", to=["c@d"], cc=[], bcc=[],
        subject=None, date=None, body="Bonjour", attachments=[]
    )
    r = classify_email(e)
    assert r.type == TicketType.question
    assert r.urgency == Urgency.basse
