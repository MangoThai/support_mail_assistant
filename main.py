from __future__ import annotations

import sys
import click
from pathlib import Path
from typing import Optional

from app.ingest import parse_email_file
from app.agent_graph import build_graph, run_turn
from app.rag import build_index


@click.group()
def cli():
    """Support Mail Assistant (CLI)"""
    pass


@cli.command()
def hello():
    """Commande de test simple."""
    click.echo("Hello from support_mail_assistant 👋")


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
    # Construire (ou reconstruire) l'index au démarrage
    build_index(kb_dir=kb_dir, persist_dir=persist_dir)
    graph = build_graph()
    loaded_email = None
    click.echo("=== Chat Support (local) ===")
    click.echo("Commandes: /load <fichier>, /clear, /exit")
    while True:
        try:
            msg = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            click.echo("\nBye.")
            break
        if not msg:
            continue
        if msg.lower() in {"/exit", "exit", "quit", ":q"}:
            click.echo("Bye.")
            break
        if msg.startswith("/load "):
            path = msg.split(" ", 1)[1].strip()
            p = Path(path)
            if not p.exists():
                click.echo(f"[!] Fichier introuvable: {p}")
                continue
            try:
                loaded_email = parse_email_file(p)
                click.echo(f"[ok] E-mail chargé: {p.name}")
            except Exception as e:
                click.echo(f"[!] Erreur parsing: {e}")
            continue
        if msg == "/clear":
            loaded_email = None
            click.echo("[ok] Contexte e-mail effacé.")
            continue

        # Exécuter un tour d'agent
        try:
            out = run_turn(graph, msg, email_obj=loaded_email, kb_dir=kb_dir, persist_dir=persist_dir)
            click.echo(out)
        except Exception as e:
            click.echo(f"[!] Erreur agent: {e}")


if __name__ == "__main__":
    cli()
