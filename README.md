# 🌌 AstrIA — Data Analyst Chatbot API

> Pose des questions en langage naturel sur tes données. Obtiens des stats, des schémas, des graphiques — instantanément.

---

## ✨ Fonctionnalités

| Endpoint | Description |
|---|---|
| 📤 `/upload` | Upload de fichier CSV / XLSX / XLS |
| 🤖 `/ask` | Q&A rule-based sur le dataset |
| 🧾 `/schema` | Résumé du schéma du dataset |
| 🗂️ `/columns` | Colonnes triées par type |
| 🔍 `/describe` | Description détaillée d'une colonne |
| 🏆 `/top` | Tri Top N |
| 📊 `/plot` | Graphiques explicites |
| 💬 `/ask_plot` | Graphiques en langage naturel |
| 🧠 `/chat_llm` | Chat OpenAI basé sur le dataset |
| 📁 `/datasets` | Listing des datasets chargés |

---

## 🛠️ Prérequis

- 🐍 Python **3.11+**
- 📦 `pip`

---

## 🚀 Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## ▶️ Lancer l'API

```bash
uvicorn app.main:app --reload
```

🌐 API disponible sur `http://127.0.0.1:8000`

## 🖥️ Lancer le front (Streamlit)

```bash
streamlit run streamlit_app.py
```

🎨 Front disponible sur `http://localhost:8501`
Si le front affiche une erreur de connexion (`127.0.0.1:8000`), relance l'API FastAPI dans un autre terminal.

---

## 🔑 Variables d'environnement

| Variable | Requis | Défaut | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ Oui | — | Obligatoire pour `/chat_llm` |
| `OPENAI_MODEL` | ❌ Non | `gpt-4.1-mini` | Modèle OpenAI utilisé |
| `PLOTS_MAX_FILES` | ❌ Non | `100` | Nombre max de fichiers de graphiques |

```bash
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4.1-mini"
export PLOTS_MAX_FILES=100
```

---

## 🧪 Tests

```bash
python3 -m pytest -q
```

---

## 📡 Exemples d'appels

### 🏥 Health check

```bash
curl http://127.0.0.1:8000/health
```

### 📤 Upload

```bash
curl -X POST "http://127.0.0.1:8000/upload" \
  -F "file=@test_data.csv"
```

### 💬 Ask

```bash
curl -X POST "http://127.0.0.1:8000/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"combien de lignes"}'
```

### 🔍 Describe

```bash
curl -X POST "http://127.0.0.1:8000/describe" \
  -H "Content-Type: application/json" \
  -d '{"column":"ventes"}'
```

### 📊 Ask Plot

```bash
curl -X POST "http://127.0.0.1:8000/ask_plot" \
  -H "Content-Type: application/json" \
  -d '{"question":"graphique des ventes par region"}'
```

---

## 🗺️ Tous les endpoints

```
GET  /health
POST /upload
GET  /datasets
POST /ask
POST /chat_llm
GET  /schema
GET  /columns
POST /describe
POST /top
POST /plot
POST /ask_plot
```

---

> 🌠 *AstrIA — Quand tes données rencontrent l'intelligence artificielle.*
