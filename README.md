# Data Analyst Chatbot API

API FastAPI pour charger un dataset (CSV/Excel), poser des questions en langage naturel, obtenir des stats et générer des graphiques.

## Fonctionnalites

- Upload de fichier CSV/XLSX/XLS (`/upload`)
- Q&A dataset rule-based (`/ask`)
- Resume schema dataset (`/schema`)
- Colonnes par type (`/columns`)
- Description detaillee d'une colonne (`/describe`)
- Tri top N (`/top`)
- Graphiques explicites (`/plot`) et en langage naturel (`/ask_plot`)
- Chat LLM OpenAI base sur le dataset (`/chat_llm`)
- Listing des datasets charges (`/datasets`)

## Prerequis

- Python 3.11+
- `pip`

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Lancer l'API

```bash
uvicorn app.main:app --reload
```

API disponible sur `http://127.0.0.1:8000`

## Variables d'environnement

- `OPENAI_API_KEY`: obligatoire pour `/chat_llm`
- `OPENAI_MODEL`: optionnel, defaut `gpt-4.1-mini`
- `PLOTS_MAX_FILES`: optionnel, defaut `100`

Exemple:

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4.1-mini"
export PLOTS_MAX_FILES=100
```

## Tests

```bash
python3 -m pytest -q
```

## Exemples d'appels

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Upload

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -F "file=@test_data.csv"
```

### Ask

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"combien de lignes"}'
```

### Describe

```bash
curl -X POST "http://127.0.0.1:8000/describe" \
  -H "Content-Type: application/json" \
  -d '{"column":"ventes"}'
```

### Ask Plot

```bash
curl -X POST "http://127.0.0.1:8000/ask_plot" \
  -H "Content-Type: application/json" \
  -d '{"question":"graphique des ventes par region"}'
```

## Endpoints

- `GET /health`
- `POST /upload`
- `GET /datasets`
- `POST /ask`
- `POST /chat_llm`
- `GET /schema`
- `GET /columns`
- `POST /describe`
- `POST /top`
- `POST /plot`
- `POST /ask_plot`
