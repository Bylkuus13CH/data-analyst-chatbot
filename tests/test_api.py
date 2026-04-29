import os

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def upload_sample_csv():
    csv_content = (
        "region,produit,ventes,prix,quantite\n"
        "Nord,Clavier,1200,49.9,24\n"
        "Sud,Souris,800,19.9,40\n"
        "Est,Ecran,1500,199.9,8\n"
        "Ouest,Casque,950,79.9,12\n"
    )
    files = {"file": ("sample.csv", csv_content, "text/csv")}
    return client.post("/upload", files=files)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_upload():
    r = upload_sample_csv()
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == 4
    assert "dataset_id" in body
    assert "ventes" in body["column_names"]


def test_upload_invalid_format():
    files = {"file": ("sample.txt", "hello", "text/plain")}
    r = client.post("/upload", files=files)
    assert r.status_code == 400
    assert "Format non supporte" in r.json()["detail"]


def test_ask_lines():
    upload_sample_csv()
    r = client.post("/ask", json={"question": "combien de lignes"})
    assert r.status_code == 200
    assert "4 lignes" in r.json()["answer"]


def test_ask_without_dataset():
    r = client.post("/ask", json={"question": "combien de lignes", "dataset_id": "does-not-exist"})
    assert r.status_code == 400


def test_describe_numeric():
    upload_sample_csv()
    r = client.post("/describe", json={"column": "ventes"})
    assert r.status_code == 200
    body = r.json()
    assert body["column"] == "ventes"
    assert body["sum"] == 4450.0


def test_describe_invalid_column():
    upload_sample_csv()
    r = client.post("/describe", json={"column": "inconnue"})
    assert r.status_code == 400


def test_top_rows():
    upload_sample_csv()
    r = client.post("/top", json={"sort_by": "ventes", "n": 2, "ascending": False})
    assert r.status_code == 200
    body = r.json()
    assert body["n"] == 2
    assert body["data"][0]["ventes"] == 1500


def test_ask_plot():
    upload_sample_csv()
    r = client.post("/ask_plot", json={"question": "graphique des ventes par region"})
    assert r.status_code == 200
    body = r.json()
    assert "chart_url" in body
    assert body["chart_url"].startswith("/plots/")


def test_ask_top_frasing_plus_grands():
    upload_sample_csv()
    r = client.post("/ask", json={"question": "2 plus grands ventes"})
    assert r.status_code == 200
    body = r.json()
    assert "TOP 2" in body["answer"]
    assert len(body["data"]) == 2


def test_chat_llm_missing_key():
    upload_sample_csv()
    previous = os.environ.pop("OPENAI_API_KEY", None)
    try:
        r = client.post("/chat_llm", json={"question": "resume"})
        assert r.status_code == 400
        assert "OPENAI_API_KEY" in r.json()["detail"]
    finally:
        if previous:
            os.environ["OPENAI_API_KEY"] = previous


def test_list_datasets():
    upload_sample_csv()
    r = client.get("/datasets")
    assert r.status_code == 200
    body = r.json()
    assert "dataset_ids" in body
    assert len(body["dataset_ids"]) >= 1
