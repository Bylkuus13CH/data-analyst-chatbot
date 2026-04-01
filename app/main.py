from io import BytesIO
import os
import re
import unicodedata
import uuid

import matplotlib
matplotlib.use("Agg")  # backend non-GUI pour serveur/API
import matplotlib.pyplot as plt
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


# On crée les dossiers utiles au démarrage.
# - plots: stockage des images générées
# - data: stockage du dataset sérialisé pour survivre aux reloads
os.makedirs("plots", exist_ok=True)
os.makedirs("data", exist_ok=True)

app = FastAPI(title="Data Analyst Chatbot API")

# Permet d'accéder aux images via /plots/<nom_fichier>.png
app.mount("/plots", StaticFiles(directory="plots"), name="plots")

# Stockage temporaire en mémoire du DataFrame courant.
DATASTORE = {"df": None}

# Sauvegarde disque du dernier dataset chargé.
DATASET_PICKLE_PATH = os.path.join("data", "current_dataset.pkl")


def read_csv_with_fallback(content: bytes) -> pd.DataFrame:
    # Essaie plusieurs encodages pour eviter les erreurs utf-8 frequentes.
    encodings = ["utf-8", "cp1252", "latin1"]
    last_error = None
    for enc in encodings:
        try:
            return pd.read_csv(BytesIO(content), encoding=enc)
        except UnicodeDecodeError as e:
            last_error = e
    raise UnicodeDecodeError(
        "csv",
        content,
        0,
        1,
        f"Impossible de decoder le CSV avec encodages testes: {encodings}. Derniere erreur: {last_error}",
    )


def get_current_df():
    # 1) Priorité à la mémoire (plus rapide).
    df = DATASTORE.get("df")
    if df is not None:
        return df

    # 2) Si mémoire vide (ex: reload), on recharge depuis le disque.
    if os.path.exists(DATASET_PICKLE_PATH):
        df = pd.read_pickle(DATASET_PICKLE_PATH)
        DATASTORE["df"] = df
        return df

    # 3) Aucun dataset disponible.
    return None


def normalize_text(value: str) -> str:
    # Normalise accents/casse pour un matching plus robuste.
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_only.lower()


def find_column_name(df: pd.DataFrame, target: str):
    # Retrouve le vrai nom de colonne (insensible aux accents/casse).
    target_norm = normalize_text(target)
    for col in df.columns:
        if normalize_text(col) == target_norm:
            return col
    return None


def detect_columns_in_question(df: pd.DataFrame, question: str):
    # Détecte les colonnes mentionnées dans la question (matching normalisé).
    q_norm = normalize_text(question)
    found = []
    for col in df.columns:
        col_norm = normalize_text(col)
        if col_norm and col_norm in q_norm:
            found.append(col)
    return found


def first_numeric_column_from_question(df: pd.DataFrame, question: str):
    # Choisit d'abord une colonne numérique mentionnée, sinon fallback sur la 1ère numérique.
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return None

    q_norm = normalize_text(question)
    for col in numeric_cols:
        if normalize_text(col) in q_norm:
            return col
    return numeric_cols[0]


def detect_aggregation_operation(question_norm: str):
    # Détecte l'opération d'agrégation demandée dans la question.
    # Renvoie: (label_humain, methode_pandas) ou None.
    checks = [
        ("moyenne", "mean", r"\bmoyenne\b"),
        ("mediane", "median", r"\bmediane\b|\bmedian\b"),
        ("somme", "sum", r"\bsomme\b|\btotal\b"),
        ("minimum", "min", r"\bminimum\b|\bmin\b"),
        ("maximum", "max", r"\bmaximum\b|\bmax\b"),
    ]
    for label, method, pattern in checks:
        if re.search(pattern, question_norm):
            return label, method
    return None


def parse_top_query(question_norm: str):
    # Détecte un motif simple de type "top 3" ou "bottom 5".
    # Renvoie (direction, n) où direction ∈ {"top", "bottom"}.
    m = re.search(r"\b(top|bottom)\s+(\d+)\b", question_norm)
    if not m:
        return None
    direction = m.group(1)
    n = max(1, min(int(m.group(2)), 1000))
    return direction, n


def save_plot(x_values, y_values, x_label: str, y_label: str, chart_type: str):
    # Validation du type pour éviter les valeurs arbitraires.
    if chart_type not in {"bar", "line"}:
        raise HTTPException(status_code=400, detail="chart_type doit etre 'bar' ou 'line'.")

    filename = f"{uuid.uuid4().hex}.png"
    filepath = os.path.join("plots", filename)

    plt.figure(figsize=(8, 4))
    if chart_type == "line":
        plt.plot(x_values, y_values)
    else:
        plt.bar(x_values, y_values)

    plt.xlabel(x_label)
    plt.ylabel(y_label)
    plt.title(f"{chart_type.upper()} - {y_label} par {x_label}")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(filepath)
    plt.close()

    return {
        "message": "Graphique genere avec succes",
        "chart_path": filepath,
        "chart_url": f"/plots/{filename}",
    }


@app.get("/health")
def health():
    # Endpoint de vérification rapide.
    return {"status": "ok"}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    # Récupère nom + extension du fichier envoyé.
    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    content = await file.read()

    # Lecture du fichier selon son format.
    try:
        if ext == "csv":
            df = read_csv_with_fallback(content)
        elif ext in {"xlsx", "xls"}:
            df = pd.read_excel(BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Format non supporte. Utilise CSV ou Excel.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    # Sauvegarde en mémoire + disque.
    DATASTORE["df"] = df
    df.to_pickle(DATASET_PICKLE_PATH)

    # Retourne un résumé du dataset.
    return {
        "message": "Fichier charge avec succes",
        "filename": filename,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": df.columns.tolist(),
    }


class QuestionRequest(BaseModel):
    # Requête pour /ask.
    question: str


class PlotRequest(BaseModel):
    # Requête pour /plot (mode explicite).
    x_col: str
    y_col: str
    chart_type: str = "bar"


class PlotQuestionRequest(BaseModel):
    # Requête pour /ask_plot (mode langage naturel).
    question: str


@app.post("/ask")
def ask_data(question_request: QuestionRequest):
    # Récupère le dataset courant.
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    # Normalise la question.
    q = question_request.question
    q_norm = normalize_text(q)

    # Cas: nombre de lignes.
    if "combien" in q_norm and ("ligne" in q_norm or "lignes" in q_norm):
        return {"answer": f"Le dataset contient {len(df)} lignes."}

    # Cas: nombre de colonnes.
    if "colon" in q_norm and ("combien" in q_norm or "nombre" in q_norm):
        return {"answer": f"Le dataset contient {len(df.columns)} colonnes."}

    # Cas: lister les colonnes.
    if ("colonne" in q_norm or "colonnes" in q_norm) and (
        "liste" in q_norm or "quelles" in q_norm or "affiche" in q_norm or "montre" in q_norm
    ):
        numeric = df.select_dtypes(include="number").columns.tolist()
        categorical = df.select_dtypes(exclude="number").columns.tolist()
        return {
            "answer": "Voici les colonnes disponibles.",
            "columns": df.columns.tolist(),
            "numeric_columns": numeric,
            "categorical_columns": categorical,
        }

    # Colonnes numériques pour les calculs.
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # Cas: valeurs manquantes (global ou par colonne).
    if "manqu" in q_norm or "null" in q_norm or "vide" in q_norm:
        found_cols = detect_columns_in_question(df, q)
        if found_cols:
            col = found_cols[0]
            missing = int(df[col].isna().sum())
            return {"answer": f"La colonne '{col}' contient {missing} valeurs manquantes."}

        missing_per_col = {
            col: int(cnt) for col, cnt in df.isna().sum().items() if int(cnt) > 0
        }
        return {
            "answer": f"Le dataset contient {int(df.isna().sum().sum())} valeurs manquantes au total.",
            "missing_by_column": missing_per_col,
        }

    # Cas: top/bottom N sur une colonne numérique.
    top_query = parse_top_query(q_norm)
    if top_query:
        direction, n = top_query
        chosen_col = first_numeric_column_from_question(df, q)
        if not chosen_col:
            return {"answer": "Aucune colonne numerique trouvee pour faire un top/bottom."}
        ascending = direction == "bottom"
        result = df.sort_values(by=chosen_col, ascending=ascending).head(n)
        return {
            "answer": f"{direction.upper()} {n} lignes sur '{chosen_col}'.",
            "data": result.to_dict(orient="records"),
        }

    # Cas: opérations d'agrégation (moyenne, mediane, somme, min, max).
    aggregation = detect_aggregation_operation(q_norm)
    if aggregation:
        op_label, op_method = aggregation

        # Mode "par": agrégation groupée, ex: "somme des ventes par region".
        if "par" in q_norm:
            found_cols = detect_columns_in_question(df, q)
            group_col = next((c for c in found_cols if c not in numeric_cols), None)
            value_col = next((c for c in found_cols if c in numeric_cols and c != group_col), None)

            if group_col and value_col:
                grouped = df.groupby(group_col, dropna=False)[value_col].agg(op_method).reset_index()
                return {
                    "answer": f"{op_label.capitalize()} de '{value_col}' par '{group_col}'.",
                    "data": grouped.to_dict(orient="records"),
                }

            return {
                "answer": (
                    "Je n'ai pas pu identifier clairement les colonnes pour une question '... par ...'. "
                    "Precise une colonne numerique (a calculer) et une colonne de regroupement."
                )
            }

        # Mode simple: agrégation sur une seule colonne numérique.
        chosen_col = first_numeric_column_from_question(df, q)
        if not chosen_col:
            return {"answer": f"Aucune colonne numerique trouvee pour calculer une {op_label}."}

        value = float(getattr(df[chosen_col], op_method)())
        return {"answer": f"La {op_label} de la colonne '{chosen_col}' est {value:.2f}."}

    # Cas par défaut si question non reconnue.
    return {
        "answer": (
            "Question non reconnue. Essaie: 'combien de lignes', 'combien de colonnes', "
            "'liste des colonnes', 'moyenne', 'somme', 'minimum', 'maximum', "
            "'valeurs manquantes', 'top 3 ventes'."
        )
    }


@app.get("/schema")
def get_schema():
    # Donne une vue structurelle du dataset (utile pour debug/frontend).
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    return {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "preview": df.head(5).to_dict(orient="records"),
    }


@app.post("/plot")
def create_plot(payload: PlotRequest):
    # Génération de graphique à partir de paramètres explicites.
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    # Validation des colonnes demandées.
    if payload.x_col not in df.columns or payload.y_col not in df.columns:
        raise HTTPException(status_code=400, detail="Colonne x_col ou y_col introuvable.")

    return save_plot(
        x_values=df[payload.x_col],
        y_values=df[payload.y_col],
        x_label=payload.x_col,
        y_label=payload.y_col,
        chart_type=payload.chart_type,
    )


@app.post("/ask_plot")
def ask_plot(payload: PlotQuestionRequest):
    # Génération de graphique à partir d'une question texte.
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    q = payload.question
    q_norm = normalize_text(q)
    cols = [c for c in df.columns]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # Impossible de tracer Y sans colonne numérique.
    if not numeric_cols:
        raise HTTPException(status_code=400, detail="Aucune colonne numerique disponible pour tracer un graphique.")

    # Détection simple des colonnes mentionnées dans la question.
    found_cols = detect_columns_in_question(df, q)

    # Cas 1: au moins 2 colonnes détectées (x, y).
    if len(found_cols) >= 2:
        x_col = found_cols[0]
        y_col = found_cols[1]
    # Cas 2: une seule colonne détectée.
    elif len(found_cols) == 1:
        only_col = found_cols[0]
        if only_col in numeric_cols:
            # Si unique colonne numérique, on trace par index (sans muter le DataFrame).
            chart_type = "line" if ("courbe" in q_norm or "line" in q_norm) else "bar"
            return save_plot(
                x_values=range(len(df)),
                y_values=df[only_col],
                x_label="index",
                y_label=only_col,
                chart_type=chart_type,
            )
        else:
            raise HTTPException(status_code=400, detail=f"La colonne '{only_col}' n'est pas numerique.")
    # Cas 3: aucune colonne détectée -> fallback.
    else:
        x_col = cols[0]
        y_col = numeric_cols[0]

    # Détection simple du type de graphe.
    chart_type = "line" if ("courbe" in q_norm or "line" in q_norm) else "bar"

    # Si X est catégorielle et Y numérique, agrège pour éviter les doublons visuels.
    if x_col not in numeric_cols and y_col in numeric_cols:
        op = detect_aggregation_operation(q_norm)
        agg_method = op[1] if op else "sum"
        grouped = df.groupby(x_col, dropna=False)[y_col].agg(agg_method).reset_index()
        return save_plot(
            x_values=grouped[x_col],
            y_values=grouped[y_col],
            x_label=x_col,
            y_label=y_col,
            chart_type=chart_type,
        )

    # Réutilise l'endpoint /plot pour ne pas dupliquer la logique.
    return create_plot(PlotRequest(x_col=x_col, y_col=y_col, chart_type=chart_type))

# =========================================================
# MODELES DE REQUETE (Body JSON) POUR LES NOUVEAUX ENDPOINTS
# =========================================================

class DescribeRequest(BaseModel):
    # Nom de la colonne à analyser dans /describe
    column: str


class TopRequest(BaseModel):
    # Nom de la colonne utilisée pour trier les lignes
    sort_by: str
    # Nombre de lignes à retourner (défaut 10)
    n: int = 10
    # Sens du tri: False = du plus grand au plus petit, True = du plus petit au plus grand
    ascending: bool = False


# =========================================================
# ENDPOINT: /columns
# But: lister les colonnes du dataset par type
# =========================================================
@app.get("/columns")
def get_columns():
    # Récupère le dataset courant (mémoire ou disque via get_current_df)
    df = get_current_df()
    if df is None:
        # Bloque l'appel si aucun upload n'a été fait
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    # Retourne:
    # - toutes les colonnes
    # - les colonnes numériques (int, float...)
    # - les colonnes non numériques (texte, date, etc.)
    return {
        "columns": df.columns.tolist(),
        "numeric_columns": df.select_dtypes(include="number").columns.tolist(),
        "categorical_columns": df.select_dtypes(exclude="number").columns.tolist(),
    }


# =========================================================
# ENDPOINT: /describe
# But: donner un résumé d'une colonne (stats + infos qualité)
# =========================================================
@app.post("/describe")
def describe_column(payload: DescribeRequest):
    # Récupère le dataset courant
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    # Vérifie que la colonne demandée existe
    if payload.column not in df.columns:
        raise HTTPException(status_code=400, detail=f"Colonne introuvable: {payload.column}")

    # Série pandas de la colonne demandée
    series = df[payload.column]

    # Bloc d'infos commun (quel que soit le type de la colonne)
    result = {
        "column": payload.column,                 # nom de la colonne
        "dtype": str(series.dtype),              # type pandas
        "count": int(series.count()),            # nb de valeurs non nulles
        "missing": int(series.isna().sum()),     # nb de valeurs manquantes
        "unique": int(series.nunique(dropna=True)),  # nb de valeurs distinctes
    }

    # Si la colonne est numérique: on calcule des stats de base
    if pd.api.types.is_numeric_dtype(series):
        has_values = series.count() > 0
        result.update(
            {
                "mean": float(series.mean()) if has_values else None,  # moyenne
                "min": float(series.min()) if has_values else None,    # minimum
                "max": float(series.max()) if has_values else None,    # maximum
                "sum": float(series.sum()) if has_values else None,    # somme
            }
        )
    else:
        # Si non numérique: on renvoie les 10 valeurs les plus fréquentes
        top_values = series.value_counts(dropna=True).head(10)
        result["top_values"] = top_values.to_dict()

    return result


# =========================================================
# ENDPOINT: /top
# But: trier le dataset sur une colonne et renvoyer les N premières lignes
# =========================================================
@app.post("/top")
def top_rows(payload: TopRequest):
    # Récupère le dataset courant
    df = get_current_df()
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    # Vérifie que la colonne de tri existe
    if payload.sort_by not in df.columns:
        raise HTTPException(status_code=400, detail=f"Colonne introuvable: {payload.sort_by}")

    # Sécurise n pour éviter des réponses trop lourdes:
    # min 1, max 1000
    n = max(1, min(payload.n, 1000))

    # Tri puis extraction des n premières lignes
    sorted_df = df.sort_values(by=payload.sort_by, ascending=payload.ascending).head(n)

    # Réponse finale JSON
    return {
        "sort_by": payload.sort_by,                  # colonne utilisée pour le tri
        "ascending": payload.ascending,              # sens du tri
        "n": int(n),                                 # n réellement utilisé
        "data": sorted_df.to_dict(orient="records"),# lignes retournées
    }
