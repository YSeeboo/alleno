from config import settings


def test_upload_policy(client, monkeypatch):
    monkeypatch.setattr(settings, "OSS_BUCKET", "allenop-images")
    monkeypatch.setattr(settings, "OSS_ENDPOINT", "oss-cn-guangzhou.aliyuncs.com")
    monkeypatch.setattr(settings, "OSS_ACCESS_KEY_ID", "test-id")
    monkeypatch.setattr(settings, "OSS_ACCESS_KEY_SECRET", "test-secret")
    monkeypatch.setattr(settings, "OSS_PUBLIC_BASE_URL", "https://img.ycbhomeland.top")

    resp = client.post(
        "/api/uploads/policy",
        json={
            "kind": "part",
            "filename": "sample.png",
            "content_type": "image/png",
            "entity_id": "PJ-0001",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["host"] == "https://allenop-images.oss-cn-guangzhou.aliyuncs.com"
    assert data["public_url"].startswith("https://img.ycbhomeland.top/parts/pj-0001/")
    assert data["key"].endswith(".png")
    assert data["oss_access_key_id"] == "test-id"


def test_upload_policy_rejects_invalid_type(client):
    resp = client.post(
        "/api/uploads/policy",
        json={"kind": "order", "filename": "sample.png", "content_type": "image/png"},
    )
    assert resp.status_code == 400


def test_upload_policy_rejects_invalid_extension(client):
    resp = client.post(
        "/api/uploads/policy",
        json={"kind": "part", "filename": "sample.pdf", "content_type": "application/pdf"},
    )
    assert resp.status_code == 400
