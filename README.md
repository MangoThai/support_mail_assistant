# Support Mail Assistant (MVP CLI)

Assistant en ligne de commande pour :
- **Ingestion** d’emails locaux (`data/emails/*.eml` ou `.txt`) vers un modèle `Email` (Pydantic)
- **Classification** (incident/demande/question + niveau d’urgence)
- **Outils** d’extraction (emails, URLs, IDs)
- **RAG** (recherche augmentée par la base `data/kb/*.md`), avec **citations des sources**
- **Réponse proposée** en français professionnel
- **Agent de chat** (LangGraph) + outils
- **Tests unitaires** pour les parties déterministes

## Prérequis
- macOS, Terminal intégré de VS Code
- Python 3.11+ recommandé
- Git + compte GitHub

## Installation (local)
```bash
# Cloner ou créer le projet
cd ~/dev/support_mail_assistant

# Créer/activer l'environnement
python3 -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# (Facultatif) copier .env.example vers .env et compléter
cp .env.example .env

# Tester la CLI
python main.py hello -n "Alice"


## Structure (local)

app/                # Code applicatif (ingest, routing, tools, rag, reply, agent_graph)
data/emails/        # Échantillons d’emails (.eml/.txt)
data/kb/            # Connaissance locale (.md)
tests/              # Tests unitaires (pytest)
.github/workflows/  # Intégration continue (CI)

## Développement

Branches de feature → Pull Request → CI → merge sur main.
Secrets dans .env (jamais commités). Documentez-les dans .env.example.
Dépendances via requirements.txt (versions figées).
Lancer les tests : python -m pytest -q.


