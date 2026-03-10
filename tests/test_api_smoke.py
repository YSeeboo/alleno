import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
