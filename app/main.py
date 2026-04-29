from io import BytesIO
import os
import re
import unicodedata
import uuid
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel


PLOTS_DIR = Path("plots")
DATA_DIR = Path("data")
DATASETS_DIR = DATA_DIR / "datasets"
DATASET_PICKLE_PATH = DATA_DIR / "current_dataset.pkl"
MAX_PLOTS = int(os.getenv("PLOTS_MAX_FILES", "100"))

PLOTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATASETS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Data Analyst Chatbot API")
app.mount("/plots", StaticFiles(directory=str(PLOTS_DIR)), name="plots")

DATASTORE: dict[str, dict | str | None] = {
    "datasets": {},
    "active_dataset_id": None,
}


class QuestionRequest(BaseModel):
    question: str
    dataset_id: str | None = None


class PlotRequest(BaseModel):
    x_col: str
    y_col: str
    chart_type: str = "bar"
    dataset_id: str | None = None


class PlotQuestionRequest(BaseModel):
    question: str
    dataset_id: str | None = None


class LLMQuestionRequest(BaseModel):
    question: str
    model: str | None = None
    dataset_id: str | None = None


class DescribeRequest(BaseModel):
    column: str
    dataset_id: str | None = None


class TopRequest(BaseModel):
    sort_by: str
    n: int = 10
    ascending: bool = False
    dataset_id: str | None = None


def read_csv_with_fallback(content: bytes) -> pd.DataFrame:
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


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_only.lower().strip()


def _dataset_path(dataset_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", dataset_id)
    return DATASETS_DIR / f"{safe_id}.pkl"


def set_current_df(df: pd.DataFrame, dataset_id: str | None = None) -> str:
    ds_id = dataset_id or uuid.uuid4().hex[:12]
    DATASTORE["datasets"][ds_id] = df
    DATASTORE["active_dataset_id"] = ds_id
    df.to_pickle(_dataset_path(ds_id))
    df.to_pickle(DATASET_PICKLE_PATH)
    return ds_id


def get_current_df(dataset_id: str | None = None) -> pd.DataFrame | None:
    selected_id = dataset_id or DATASTORE.get("active_dataset_id")
    if selected_id:
        mem_df = DATASTORE["datasets"].get(selected_id)
        if mem_df is not None:
            return mem_df

        disk_path = _dataset_path(selected_id)
        if disk_path.exists():
            df = pd.read_pickle(disk_path)
            DATASTORE["datasets"][selected_id] = df
            DATASTORE["active_dataset_id"] = selected_id
            return df

        if dataset_id is not None:
            return None

    if DATASET_PICKLE_PATH.exists():
        df = pd.read_pickle(DATASET_PICKLE_PATH)
        fallback_id = selected_id or "default"
        DATASTORE["datasets"][fallback_id] = df
        DATASTORE["active_dataset_id"] = fallback_id
        return df

    return None


def find_column_name(df: pd.DataFrame, target: str) -> str | None:
    target_norm = normalize_text(target)
    for col in df.columns:
        if normalize_text(col) == target_norm:
            return col
    return None


def detect_columns_in_question(df: pd.DataFrame, question: str) -> list[str]:
    q_norm = normalize_text(question)
    found = []
    for col in df.columns:
        col_norm = normalize_text(col)
        if not col_norm:
            continue
        if re.search(rf"\b{re.escape(col_norm)}\b", q_norm):
            found.append(col)
    return found


def first_numeric_column_from_question(df: pd.DataFrame, question: str) -> str | None:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    if not numeric_cols:
        return None

    detected = detect_columns_in_question(df, question)
    for col in detected:
        if col in numeric_cols:
            return col

    return numeric_cols[0]


def detect_aggregation_operation(question_norm: str):
    checks = [
        ("moyenne", "mean", r"\bmoyenne\b|\bmoy\b|\bavg\b|\baverage\b"),
        ("mediane", "median", r"\bmediane\b|\bmedian\b"),
        ("somme", "sum", r"\bsomme\b|\btotal\b|\bsum\b"),
        ("minimum", "min", r"\bminimum\b|\bmin\b"),
        ("maximum", "max", r"\bmaximum\b|\bmax\b"),
    ]
    for label, method, pattern in checks:
        if re.search(pattern, question_norm):
            return label, method
    return None


def parse_top_query(question_norm: str):
    m = re.search(r"\b(top|bottom|haut|bas)\s+(\d+)\b", question_norm)
    if m:
        direction = m.group(1)
        normalized_direction = "top" if direction in {"top", "haut"} else "bottom"
        n = max(1, min(int(m.group(2)), 1000))
        return normalized_direction, n

    m_fr = re.search(r"\b(\d+)\s+(plus\s+grands?|plus\s+hauts?|plus\s+petits?|plus\s+bas)\b", question_norm)
    if not m_fr:
        return None

    n = max(1, min(int(m_fr.group(1)), 1000))
    label = m_fr.group(2)
    direction = "bottom" if ("petit" in label or "bas" in label) else "top"
    return direction, n


def detect_chart_type(question_norm: str) -> str:
    if any(token in question_norm for token in ["courbe", "line", "ligne"]):
        return "line"
    return "bar"


def _cleanup_old_plots(limit: int):
    files = sorted(PLOTS_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old_file in files[limit:]:
        old_file.unlink(missing_ok=True)


def save_plot(x_values, y_values, x_label: str, y_label: str, chart_type: str):
    if chart_type not in {"bar", "line"}:
        raise HTTPException(status_code=400, detail="chart_type doit etre 'bar' ou 'line'.")

    filename = f"{uuid.uuid4().hex}.png"
    filepath = PLOTS_DIR / filename

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

    _cleanup_old_plots(MAX_PLOTS)

    return {
        "message": "Graphique genere avec succes",
        "chart_path": str(filepath),
        "chart_url": f"/plots/{filename}",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or ""
    ext = filename.lower().split(".")[-1] if "." in filename else ""
    content = await file.read()

    try:
        if ext == "csv":
            df = read_csv_with_fallback(content)
        elif ext in {"xlsx", "xls"}:
            df = pd.read_excel(BytesIO(content))
        else:
            raise HTTPException(status_code=400, detail="Format non supporte. Utilise CSV ou Excel.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erreur lecture fichier: {str(e)}")

    dataset_id = set_current_df(df)

    return {
        "message": "Fichier charge avec succes",
        "filename": filename,
        "dataset_id": dataset_id,
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": df.columns.tolist(),
    }


@app.post("/ask")
def ask_data(question_request: QuestionRequest):
    df = get_current_df(question_request.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    q = question_request.question
    q_norm = normalize_text(q)

    if "combien" in q_norm and ("ligne" in q_norm or "lignes" in q_norm):
        return {"answer": f"Le dataset contient {len(df)} lignes."}

    if "colon" in q_norm and ("combien" in q_norm or "nombre" in q_norm):
        return {"answer": f"Le dataset contient {len(df.columns)} colonnes."}

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

    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if "manqu" in q_norm or "null" in q_norm or "vide" in q_norm:
        found_cols = detect_columns_in_question(df, q)
        if found_cols:
            col = found_cols[0]
            missing = int(df[col].isna().sum())
            return {"answer": f"La colonne '{col}' contient {missing} valeurs manquantes."}

        missing_per_col = {col: int(cnt) for col, cnt in df.isna().sum().items() if int(cnt) > 0}
        return {
            "answer": f"Le dataset contient {int(df.isna().sum().sum())} valeurs manquantes au total.",
            "missing_by_column": missing_per_col,
        }

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

    aggregation = detect_aggregation_operation(q_norm)
    if aggregation:
        op_label, op_method = aggregation

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

        chosen_col = first_numeric_column_from_question(df, q)
        if not chosen_col:
            return {"answer": f"Aucune colonne numerique trouvee pour calculer une {op_label}."}

        value = float(getattr(df[chosen_col], op_method)())
        return {"answer": f"La {op_label} de la colonne '{chosen_col}' est {value:.2f}."}

    return {
        "answer": (
            "Question non reconnue. Essaie: 'combien de lignes', 'combien de colonnes', "
            "'liste des colonnes', 'moyenne', 'somme', 'minimum', 'maximum', "
            "'valeurs manquantes', 'top 3 ventes'."
        )
    }


@app.post("/chat_llm")
def chat_llm(payload: LLMQuestionRequest):
    df = get_current_df(payload.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="OPENAI_API_KEY manquante. Definis la variable d'environnement pour utiliser /chat_llm.",
        )

    model = payload.model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    schema_info = ", ".join(f"{col} ({dtype})" for col, dtype in df.dtypes.items())
    preview_records = df.head(8).to_dict(orient="records")

    system_prompt = (
        "Tu es un data analyst assistant. "
        "Tu reponds en francais de facon claire et concise. "
        "Tu te bases uniquement sur le contexte dataset fourni."
    )
    user_prompt = (
        f"Schema colonnes: {schema_info}\n"
        f"Apercu lignes: {preview_records}\n"
        f"Question utilisateur: {payload.question}"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
                {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
            ],
        )
        return {"answer": response.output_text, "model": model, "source": "openai"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur appel LLM: {str(e)}")


@app.get("/schema")
def get_schema(dataset_id: str | None = Query(default=None)):
    df = get_current_df(dataset_id)
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
    df = get_current_df(payload.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    x_col = find_column_name(df, payload.x_col)
    y_col = find_column_name(df, payload.y_col)

    if x_col is None or y_col is None:
        raise HTTPException(status_code=400, detail="Colonne x_col ou y_col introuvable.")

    return save_plot(
        x_values=df[x_col],
        y_values=df[y_col],
        x_label=x_col,
        y_label=y_col,
        chart_type=payload.chart_type,
    )


@app.post("/ask_plot")
def ask_plot(payload: PlotQuestionRequest):
    df = get_current_df(payload.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    q = payload.question
    q_norm = normalize_text(q)
    cols = [c for c in df.columns]
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if not numeric_cols:
        raise HTTPException(status_code=400, detail="Aucune colonne numerique disponible pour tracer un graphique.")

    found_cols = detect_columns_in_question(df, q)

    if len(found_cols) >= 2:
        numeric_in_found = [c for c in found_cols if c in numeric_cols]
        non_numeric_in_found = [c for c in found_cols if c not in numeric_cols]
        if numeric_in_found and non_numeric_in_found:
            x_col = non_numeric_in_found[0]
            y_col = numeric_in_found[0]
        else:
            x_col = found_cols[0]
            y_col = found_cols[1]
    elif len(found_cols) == 1:
        only_col = found_cols[0]
        if only_col in numeric_cols:
            chart_type = detect_chart_type(q_norm)
            return save_plot(
                x_values=range(len(df)),
                y_values=df[only_col],
                x_label="index",
                y_label=only_col,
                chart_type=chart_type,
            )
        raise HTTPException(status_code=400, detail=f"La colonne '{only_col}' n'est pas numerique.")
    else:
        x_col = cols[0]
        y_col = numeric_cols[0]

    chart_type = detect_chart_type(q_norm)

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

    return create_plot(PlotRequest(x_col=x_col, y_col=y_col, chart_type=chart_type, dataset_id=payload.dataset_id))


@app.get("/columns")
def get_columns(dataset_id: str | None = Query(default=None)):
    df = get_current_df(dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    return {
        "columns": df.columns.tolist(),
        "numeric_columns": df.select_dtypes(include="number").columns.tolist(),
        "categorical_columns": df.select_dtypes(exclude="number").columns.tolist(),
    }


@app.get("/datasets")
def list_datasets():
    in_memory_ids = list(DATASTORE["datasets"].keys())
    on_disk_ids = [p.stem for p in DATASETS_DIR.glob("*.pkl")]
    all_ids = sorted(set(in_memory_ids + on_disk_ids))
    return {"active_dataset_id": DATASTORE.get("active_dataset_id"), "dataset_ids": all_ids}


@app.post("/describe")
def describe_column(payload: DescribeRequest):
    df = get_current_df(payload.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    column_name = find_column_name(df, payload.column)
    if column_name is None:
        raise HTTPException(status_code=400, detail=f"Colonne introuvable: {payload.column}")

    series = df[column_name]

    result = {
        "column": column_name,
        "dtype": str(series.dtype),
        "count": int(series.count()),
        "missing": int(series.isna().sum()),
        "unique": int(series.nunique(dropna=True)),
    }

    if pd.api.types.is_numeric_dtype(series):
        has_values = series.count() > 0
        result.update(
            {
                "mean": float(series.mean()) if has_values else None,
                "min": float(series.min()) if has_values else None,
                "max": float(series.max()) if has_values else None,
                "sum": float(series.sum()) if has_values else None,
            }
        )
    else:
        top_values = series.value_counts(dropna=True).head(10)
        result["top_values"] = top_values.to_dict()

    return result


@app.post("/top")
def top_rows(payload: TopRequest):
    df = get_current_df(payload.dataset_id)
    if df is None:
        raise HTTPException(status_code=400, detail="Aucun dataset charge. Upload d'abord un fichier.")

    sort_col = find_column_name(df, payload.sort_by)
    if sort_col is None:
        raise HTTPException(status_code=400, detail=f"Colonne introuvable: {payload.sort_by}")

    n = max(1, min(payload.n, 1000))
    sorted_df = df.sort_values(by=sort_col, ascending=payload.ascending).head(n)

    return {
        "sort_by": sort_col,
        "ascending": payload.ascending,
        "n": int(n),
        "data": sorted_df.to_dict(orient="records"),
    }
