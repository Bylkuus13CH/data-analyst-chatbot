# 🌌 AstrIA

> Upload un CSV/Excel, pose des questions en langage naturel, génère des graphiques et obtiens des stats sur tes colonnes — via une API FastAPI + un front Streamlit.

---

## 🛠️ Stack

| Composant | Rôle |
|---|---|
| 🐍 Python | Base |
| ⚡ FastAPI | API backend |
| 🎨 Streamlit | Interface front |
| 🐼 Pandas | Manipulation des données |
| 📊 Matplotlib | Génération de graphiques |
| 🤖 OpenAI SDK | Optionnel — pour `/chat_llm` |

---

## 📁 Structure du projet

```
data-analyst-chatbot/
├── app/main.py          → API FastAPI
├── streamlit_app.py     → Interface Streamlit
├── tests/test_api.py    → Tests API
├── assets/              → Images du front
├── data/                → Datasets sérialisés
└── plots/               → Graphiques générés
```

---

## 🚀 Installation

Depuis le dossier `data-analyst-chatbot` :

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ▶️ Lancer l'application

Lancer dans 2 terminaux séparés.

**Terminal 1 — API :**

```bash
cd /Users/nel/Chatbot/data-analyst-chatbot
source ../.venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2 — Front :**

```bash
cd /Users/nel/Chatbot/data-analyst-chatbot
source ../.venv/bin/activate
streamlit run streamlit_app.py
```

🌐 **URLs :**
- API → `http://127.0.0.1:8000`
- Swagger → `http://127.0.0.1:8000/docs`
- Front → `http://localhost:8501`

---

## 🔑 Variables d'environnement

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ⚠️ Pour `/chat_llm` | — | Clé API OpenAI |
| `OPENAI_MODEL` | ❌ Non | `gpt-4.1-mini` | Modèle utilisé |
| `PLOTS_MAX_FILES` | ❌ Non | `100` | Nb max de graphiques |

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4.1-mini"
export PLOTS_MAX_FILES=100
```

---

## 🗺️ Flux d'utilisation rapide

1. 🌐 Ouvre le front `http://localhost:8501`
2. 📤 Upload un fichier CSV / XLSX
3. 💬 Pose une question libre
4. 📊 Demande un graphique
5. 🔍 Utilise l'analyse de colonne si besoin

---

## 📡 Endpoints principaux

```
GET  /health
POST /upload
GET  /datasets
POST /ask
POST /ask_plot
POST /plot
GET  /schema
GET  /columns
POST /describe
POST /top
POST /chat_llm
```

---

## 🧪 Tests

```bash
python3 -m pytest -q
```

---

## 🔧 Dépannage

### ❌ Erreur `Connection refused` dans Streamlit

**Cause :** API non lancée.

**Solution :** relancer FastAPI dans un autre terminal :

```bash
uvicorn app.main:app --reload
```

### ❌ Erreur "Aucune colonne numérique disponible"

**Cause fréquente :** colonnes lues en texte (format CSV non standard).

**Vérifie avec :**
- `GET /schema`
- `GET /columns`

Puis utilise les noms exacts des colonnes numériques dans ta question graphique.

---

## 📝 Remarques

- `dataset_id` peut être laissé vide dans la plupart des cas — l'API utilise le dernier upload.
- Les graphiques sont accessibles via les URLs `/plots/<fichier>.png`.

---

> 🌠 *AstrIA — Quand tes données rencontrent l'intelligence artificielle.*
