import os
from pathlib import Path

import requests
import streamlit as st
from requests.exceptions import RequestException

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
ROBOT_IMAGE_PATH = Path("assets/robot.svg")

st.set_page_config(page_title="AstrIA", page_icon="🤖", layout="wide")

if "theme_mode" not in st.session_state:
    st.session_state.theme_mode = "dark"
if "dataset_id" not in st.session_state:
    st.session_state.dataset_id = None


def safe_request(method: str, endpoint: str, **kwargs):
    try:
        return requests.request(method, f"{API_BASE_URL}{endpoint}", timeout=60, **kwargs)
    except RequestException:
        st.error("API indisponible sur http://127.0.0.1:8000. Lance ou relance FastAPI avec: uvicorn app.main:app --reload")
        return None


def apply_theme(mode: str):
    if mode == "light":
        bg = "#f1f6ff"
        panel = "#ffffff"
        text = "#1b1935"
        muted = "#4b4a73"
        border = "rgba(116, 94, 255, 0.35)"
    else:
        bg = "#050507"
        panel = "#0c0d13"
        text = "#eff0ff"
        muted = "#a4a8c7"
        border = "rgba(127, 255, 140, 0.55)"

    st.markdown(
        f"""
        <style>
        :root {{
            --bg: {bg};
            --panel: {panel};
            --text: {text};
            --muted: {muted};
            --violet: #905fff;
            --green: #4dff99;
            --cyan: #43d9ff;
            --border: {border};
        }}
        .stApp {{
            background:
                radial-gradient(900px 480px at 12% -8%, rgba(144,95,255,0.26), transparent 60%),
                radial-gradient(1000px 600px at 90% 5%, rgba(67,217,255,0.20), transparent 60%),
                radial-gradient(1000px 640px at 50% 120%, rgba(77,255,153,0.12), transparent 70%),
                var(--bg);
            color: var(--text);
        }}
        .block-container {{
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }}
        h1,h2,h3,p,label,div {{ color: var(--text) !important; }}
        .brand {{
            border-radius: 20px;
            border: 1px solid var(--border);
            padding: 1rem 1.2rem;
            background: linear-gradient(135deg, rgba(144,95,255,0.20), rgba(67,217,255,0.10));
            box-shadow: 0 0 38px rgba(144,95,255,0.20);
            margin-bottom: 1rem;
        }}
        .panel {{
            border-radius: 16px;
            border: 1px solid var(--border);
            padding: 0.8rem;
            background: var(--panel);
            box-shadow: 0 0 24px rgba(77,255,153,0.10), 0 0 34px rgba(144,95,255,0.12);
            margin-bottom: 1rem;
        }}
        .guide {{
            border-radius: 14px;
            border: 1px dashed rgba(67,217,255,0.7);
            padding: 0.6rem;
            background: rgba(67,217,255,0.08);
            margin-bottom: 0.7rem;
            color: var(--muted) !important;
            font-size: 0.9rem;
        }}
        .stButton > button {{
            border: 1px solid transparent;
            background:
                linear-gradient(var(--panel), var(--panel)) padding-box,
                linear-gradient(90deg, var(--green), var(--violet), var(--cyan)) border-box;
            color: var(--text);
            border-radius: 12px;
            font-weight: 600;
            box-shadow: 0 0 18px rgba(77,255,153,0.30), 0 0 18px rgba(144,95,255,0.25);
        }}
        .stTextInput > div > div > input, .stFileUploader, .stTextArea textarea {{
            background: rgba(255,255,255,0.02);
            border: 1px solid rgba(144,95,255,0.5) !important;
            border-radius: 10px;
            color: var(--text);
        }}
        .robot-wrap {{
            border-radius: 26px;
            border: 1px solid rgba(144,95,255,0.45);
            background: radial-gradient(circle at 50% 20%, rgba(67,217,255,0.15), rgba(12,13,19,0.85));
            padding: 0.6rem;
            box-shadow: 0 0 28px rgba(67,217,255,0.22), 0 0 42px rgba(144,95,255,0.20);
        }}
        .hint {{
            text-align: center;
            color: var(--muted) !important;
            margin-top: 0.5rem;
            margin-bottom: 0;
            font-size: 0.92rem;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


apply_theme(st.session_state.theme_mode)

h1, h2 = st.columns([5, 1])
with h1:
    st.markdown(
        """
        <div class='brand'>
            <h1 style='margin:0;'>AstrIA</h1>
            <p style='margin:0.3rem 0 0 0;color:#a4a8c7;'>Ton copilote data. Le robot au centre te guide vers chaque action.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
with h2:
    mode = st.toggle("Mode clair", value=st.session_state.theme_mode == "light")
    st.session_state.theme_mode = "light" if mode else "dark"

left, center, right = st.columns([1.0, 1.8, 1.0])

with left:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.subheader("Upload")
    uploaded_file = st.file_uploader("CSV ou Excel", type=["csv", "xlsx", "xls"])
    if st.button("Uploader le dataset", use_container_width=True):
        if not uploaded_file:
            st.warning("Choisis un fichier d'abord.")
        else:
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type or "application/octet-stream")}
            r = safe_request("POST", "/upload", files=files)
            if r is None:
                st.stop()
            if r.ok:
                body = r.json()
                st.session_state.dataset_id = body.get("dataset_id")
                st.success("Dataset uploadé")
                st.json(body)
            else:
                st.error(r.text)

    st.caption(f"dataset_id actif: {st.session_state.dataset_id or 'dernier upload auto'}")

    st.subheader("Question libre")
    question = st.text_input("Ex: moyenne de Quantité")
    if st.button("Demander à AstrIA", use_container_width=True):
        if not question.strip():
            st.warning("Écris une question.")
        else:
            payload = {"question": question}
            if st.session_state.dataset_id:
                payload["dataset_id"] = st.session_state.dataset_id
            r = safe_request("POST", "/ask", json=payload)
            if r is None:
                st.stop()
            if r.ok:
                st.json(r.json())
            else:
                st.error(r.text)
    st.markdown("</div>", unsafe_allow_html=True)

with center:
    st.markdown("<div class='robot-wrap'>", unsafe_allow_html=True)
    if ROBOT_IMAGE_PATH.exists():
        st.image(str(ROBOT_IMAGE_PATH), width=560)
    else:
        st.warning("Image robot introuvable: assets/robot.png")
    st.markdown("<p class='hint'> </p>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

with right:
    st.markdown("<div class='panel'>", unsafe_allow_html=True)
    st.subheader("Graphique")
    plot_question = st.text_input("Ex: graphique du Chiffre d'affaires par Région")
    if st.button("Générer un graphique", use_container_width=True):
        if not plot_question.strip():
            st.warning("Écris une demande de graphique.")
        else:
            payload = {"question": plot_question}
            if st.session_state.dataset_id:
                payload["dataset_id"] = st.session_state.dataset_id
            r = safe_request("POST", "/ask_plot", json=payload)
            if r is None:
                st.stop()
            if r.ok:
                body = r.json()
                st.json(body)
                chart_url = body.get("chart_url")
                if chart_url:
                    st.image(f"{API_BASE_URL}{chart_url}", caption="Graphique AstrIA")
            else:
                st.error(r.text)

    st.subheader("Décrire une colonne")
    col_name = st.text_input("Ex: Chiffre d'affaires")
    if st.button("Analyser la colonne", use_container_width=True):
        if not col_name.strip():
            st.warning("Indique une colonne.")
        else:
            payload = {"column": col_name}
            if st.session_state.dataset_id:
                payload["dataset_id"] = st.session_state.dataset_id
            r = safe_request("POST", "/describe", json=payload)
            if r is None:
                st.stop()
            if r.ok:
                st.json(r.json())
            else:
                st.error(r.text)
    st.markdown("</div>", unsafe_allow_html=True)

with st.expander("Outils dataset"):
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("Voir /columns", use_container_width=True):
            params = {"dataset_id": st.session_state.dataset_id} if st.session_state.dataset_id else None
            r = safe_request("GET", "/columns", params=params)
            if r is not None:
                st.json(r.json() if r.ok else {"error": r.text})
    with c2:
        if st.button("Voir /schema", use_container_width=True):
            params = {"dataset_id": st.session_state.dataset_id} if st.session_state.dataset_id else None
            r = safe_request("GET", "/schema", params=params)
            if r is not None:
                st.json(r.json() if r.ok else {"error": r.text})
    with c3:
        if st.button("Voir /datasets", use_container_width=True):
            r = safe_request("GET", "/datasets")
            if r is not None:
                st.json(r.json() if r.ok else {"error": r.text})
