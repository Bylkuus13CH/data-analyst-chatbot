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
    assert "ventes" in body["column_names"]


def test_ask_lines():
    upload_sample_csv()
    r = client.post("/ask", json={"question": "combien de lignes"})
    assert r.status_code == 200
    assert "4 lignes" in r.json()["answer"]


def test_describe_numeric():
    upload_sample_csv()
    r = client.post("/describe", json={"column": "ventes"})
    assert r.status_code == 200
    body = r.json()
    assert body["column"] == "ventes"
    assert body["sum"] == 4450.0


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
