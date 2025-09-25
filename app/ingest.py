from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from hashlib import sha256
from pathlib import Path
from typing import List, Optional


@dataclass(frozen=True)
class Email:
    """Représentation normalisée d'un email local."""
    id: str                     # hash stable du fichier
    raw_path: str               # chemin du fichier source
    from_: Optional[str]        # adresse "From"
    to: List[str]               # adresses "To"
    cc: List[str]               # adresses "Cc"
    bcc: List[str]              # adresses "Bcc" (rare dans .eml reçus)
    subject: Optional[str]      # sujet
    date: Optional[datetime]    # horodatage si présent
    body: str                   # texte du message (text/plain)
    attachments: List[str]      # noms de fichiers attachés (si .eml)


# ------------------------
# API principale
# ------------------------

def parse_email_file(path: Path) -> Email:
    """
    Détecte l'extension et parse un .eml (RFC 5322) ou un .txt "type email".
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".eml":
        return _parse_eml(path)
    elif path.suffix.lower() == ".txt":
        return _parse_txt(path)
    else:
        raise ValueError(f"Extension non supportée: {path.suffix}")


def load_local_emails(folder: Path) -> List[Email]:
    """
    Charge tous les .eml/.txt d'un dossier (non récursif) et renvoie une liste d'Email.
    L'ordre est trié par nom de fichier pour un comportement déterministe.
    """
    folder = Path(folder)
    files = sorted([p for p in folder.iterdir() if p.suffix.lower() in {".eml", ".txt"}])
    return [parse_email_file(p) for p in files]


# ------------------------
# Helpers internes
# ------------------------

def _stable_id_from_file(path: Path) -> str:
    """Crée un identifiant stable basé sur le contenu du fichier."""
    data = path.read_bytes()
    return sha256(data).hexdigest()[:12]


def _addresses_from_header(msg: EmailMessage, header: str) -> List[str]:
    values = msg.get_all(header, [])
    return [addr for _, addr in getaddresses(values) if addr]


def _extract_body_from_email_message(msg: EmailMessage) -> str:
    """
    Récupère le contenu text/plain (évite les pièces jointes).
    - Si multipart: choisit la première part 'text/plain' non attachée.
    - Sinon: get_content() du message directement.
    """
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get_content_disposition() == "attachment":
                continue
            if part.get_content_type() == "text/plain":
                # policy.default -> get_content() renvoie str décodé
                return part.get_content()
        # fallback si pas de text/plain trouvé
        return ""
    else:
        if msg.get_content_type() == "text/plain":
            return msg.get_content()
        return ""

def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def _parse_eml(path: Path) -> Email:
    msg = BytesParser(policy=policy.default).parsebytes(path.read_bytes())

    body = _extract_body_from_email_message(msg)
    attachments = []
    for part in msg.iter_attachments():
        filename = part.get_filename()
        if filename:
            attachments.append(filename)

    return Email(
        id=_stable_id_from_file(path),
        raw_path=str(path),
        from_=(_addresses_from_header(msg, "From")[0] if _addresses_from_header(msg, "From") else None),
        to=_addresses_from_header(msg, "To"),
        cc=_addresses_from_header(msg, "Cc"),
        bcc=_addresses_from_header(msg, "Bcc"),
        subject=(msg.get("Subject") or None),
        date=_parse_date(msg.get("Date")),
        body=body.strip(),
        attachments=attachments,
    )


def _parse_txt(path: Path) -> Email:
    """
    Format .txt supporté:
    - Entêtes optionnelles en haut (From/To/Cc/Subject/Date) au format 'Header: valeur'
    - Une ligne vide
    - Corps du message
    Si aucune ligne vide: tout est considéré comme corps.
    """
    text = path.read_text(encoding="utf-8", errors="replace")

    # Séparer headers / body sur la première ligne vide
    header_part, sep, body_part = text.partition("\n\n")
    headers = {}
    if sep:  # on a trouvé une ligne vide => header_part contient (peut-être) des entêtes
        for line in header_part.splitlines():
            if ":" in line:
                key, val = line.split(":", 1)
                headers[key.strip().lower()] = val.strip()
        body = body_part
    else:
        # Pas de headers détectés
        body = text

    # Normalisation des champs
    from_ = headers.get("from")
    to = [addr for _, addr in getaddresses([headers.get("to", "")])]
    cc = [addr for _, addr in getaddresses([headers.get("cc", "")])]
    subject = headers.get("subject")
    date = _parse_date(headers.get("date"))

    return Email(
        id=_stable_id_from_file(path),
        raw_path=str(path),
        from_=from_,
        to=to,
        cc=cc,
        bcc=[],
        subject=subject,
        date=date,
        body=body.strip(),
        attachments=[],
    )
