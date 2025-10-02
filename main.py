from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, Iterable

import click
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table

from app.ingest import parse_email_file, Email
from app.routing import classify_email
from app.rag import build_index, retrieve_snippets
from app.reply import build_context, suggest_reply


console = Console()
load_dotenv()  # charge .env si présent (CHROMA_TELEMETRY_DISABLED, etc.)


@click.group()
def cli():
    """Support Mail Assistant (CLI)"""
    pass


@cli.command()
def hello():
    """Commande de test simple."""
    click.echo("Hello from support_mail_assistant 👋")


def _iter_email_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
    else:
        for ext in ("*.eml", "*.txt"):
            yield from sorted(path.glob(ext))


def _email_to_dict(e: Email) -> dict:
    # Compat Pydantic v2 : .model_dump(); fallback en dict
    to_js = getattr(e, "model_dump", None)
    return to_js() if to_js else e.__dict__


@cli.command()
@click.option("--path", "path_str", default="data/emails", show_default=True,
              help="Fichier .eml/.txt ou dossier contenant des emails.")
@click.option("--json", "as_json", is_flag=True, help="Affiche le JSON complet par email.")
def ingest(path_str: str, as_json: bool):
    """
    Lit un ou plusieurs emails depuis un fichier/dossier, et affiche un résumé.
    """
    path = Path(path_str)
    if not path.exists():
        console.print(f"[red]Chemin introuvable:[/red] {path}")
        sys.exit(1)

    files = list(_iter_email_files(path))
    if not files:
        console.print(f"[yellow]Aucun email trouvé dans:[/yellow] {path}")
        sys.exit(0)

    if as_json:
        import json
        for f in files:
            try:
                e = parse_email_file(f)
                console.print_json(data=_email_to_dict(e))
            except Exception as ex:
                console.print(f"[red]Erreur parsing {f.name}:[/red] {ex}")
        return

    table = Table(title="Emails ingérés", box=box.SIMPLE_HEAVY)
    table.add_column("Fichier")
    table.add_column("From")
    table.add_column("Subject")
    table.add_column("Date")

    ok = 0
    for f in files:
        try:
            e = parse_email_file(f)
            table.add_row(f.name, e.from_ or "-", e.subject or "-", str(e.date or "-"))
            ok += 1
        except Exception as ex:
            table.add_row(f.name, "[red]Erreur[/red]", str(ex), "-")

    console.print(table)
    console.print(f"[green]Total parsé avec succès:[/green] {ok}/{len(files)}")


@cli.command()
@click.option("--file", "file_str", required=True, help="Chemin d'un email .eml ou .txt")
def classify(file_str: str):
    """
    Classifie un email (type: incident/demande/question + urgence).
    """
    p = Path(file_str)
    if not p.exists():
        console.print(f"[red]Fichier introuvable:[/red] {p}")
        sys.exit(1)

    try:
        email = parse_email_file(p)
        routing = classify_email(email)
    except Exception as ex:
        console.print(f"[red]Erreur:[/red] {ex}")
        sys.exit(2)

    table = Table(title="Classification", box=box.SIMPLE_HEAVY)
    table.add_column("Champ")
    table.add_column("Valeur")
    table.add_row("Type", routing.type.value)
    table.add_row("Urgence", routing.urgency.value)
    table.add_row("Features", ", ".join(routing.matched_features) or "-")
    console.print(table)


@cli.command(name="suggest-reply")
@click.option("--file", "file_str", required=True, help="Chemin d'un email .eml ou .txt")
@click.option("--kb-dir", default="data/kb", show_default=True, help="Répertoire des fichiers .md")
@click.option("--persist-dir", default="data/chroma", show_default=True, help="Répertoire de l'index persistant")
@click.option("--k", default=3, show_default=True, help="Nombre d'extraits (snippets) à citer")
def suggest_reply_cmd(file_str: str, kb_dir: str, persist_dir: str, k: int):
    """
    Propose une réponse (ton pro FR, étapes numérotées) avec citations des sources.
    """
    p = Path(file_str)
    if not p.exists():
        console.print(f"[red]Fichier introuvable:[/red] {p}")
        sys.exit(1)

    try:
        email = parse_email_file(p)
        # Reconstruire l'index à chaque appel reste simple et sûr pour le MVP.
        build_index(kb_dir=kb_dir, persist_dir=persist_dir)
        # Requête naïve = sujet (fallback sur le début du corps)
        query = (email.subject or (email.body or "")[:200]) or ""
        snippets = retrieve_snippets(query, k=k, kb_dir=kb_dir, persist_dir=persist_dir)
        routing = classify_email(email)
        ctx = build_context(email, routing_decision=routing, snippets=snippets)
        out = suggest_reply(email, ctx)
        console.print(out)
    except Exception as ex:
        console.print(f"[red]Erreur:[/red] {ex}")
        sys.exit(2)


@cli.command()
@click.option("--kb-dir", default="data/kb", show_default=True, help="Répertoire des fichiers .md")
@click.option("--persist-dir", default="data/chroma", show_default=True, help="Répertoire de l'index Chroma (persistant)")
def chat(kb_dir: str, persist_dir: str):
    """
    Démarre un mini-chat local :
      - /load <path.eml|.txt> : charge un e-mail pour contextualiser les réponses
      - /clear : efface l'e-mail chargé
      - /exit : quitter
      - tout autre texte : question / requête
    """
    from app.agent_graph import build_graph, run_turn

    # Index prêt au démarrage
    build_index(kb_dir=kb_dir, persist_dir=persist_dir)
    graph = build_graph()
    loaded_email = None
    console.print("[bold]=== Chat Support (local) ===[/bold]")
    console.print("Commandes: /load <fichier>, /clear, /exit")
    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nBye.")
            break
        if not msg:
            continue
        if msg.lower() in {"/exit", "exit", "quit", ":q"}:
            console.print("Bye.")
            break
        if msg.startswith("/load "):
            path = msg.split(" ", 1)[1].strip()
            p = Path(path)
            if not p.exists():
                console.print(f"[red]Fichier introuvable:[/red] {p}")
                continue
            try:
                loaded_email = parse_email_file(p)
                console.print(f"[green]E-mail chargé:[/green] {p.name}")
            except Exception as e:
                console.print(f"[red]Erreur parsing:[/red] {e}")
            continue
        if msg == "/clear":
            loaded_email = None
            console.print("[yellow]Contexte e-mail effacé.[/yellow]")
            continue

        try:
            out = run_turn(graph, msg, email_obj=loaded_email, kb_dir=kb_dir, persist_dir=persist_dir)
            console.print(out)
        except Exception as e:
            console.print(f"[red]Erreur agent:[/red] {e}")


if __name__ == "__main__":
    cli()
