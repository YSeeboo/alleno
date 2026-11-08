import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_archive_release import verify_release


def digest(data):
    return hashlib.sha256(data.encode()).hexdigest()


@pytest.fixture
def staged(tmp_path):
    release = tmp_path / "release"
    target = tmp_path / "target"
    for path, data in {
        release / "payload/services/example.py": "new source",
        target / "services/example.py": "old source",
        target / "frontend/src/main.js": "existing app",
        target / "frontend/public/logo.svg": "existing logo",
        target / "frontend/dist/index.html": "old build",
    }.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    manifest = {
        "version": 1, "before": "2026-10-29",
        "payload": {"services/example.py": digest("new source")},
        "expected_target": {
            "services/example.py": digest("old source"),
            "services/new.py": None,
            "frontend/src/main.js": digest("existing app"),
            "frontend/public/logo.svg": digest("existing logo"),
        },
        "expected_dist": {"index.html": digest("old build")},
    }
    (release / "manifest.json").write_text(json.dumps(manifest))
    return release, target


def test_verifier_is_read_only(staged):
    release, target = staged
    before = {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert verify_release(release, target)["before"] == "2026-10-29"
    assert before == {p.relative_to(target): p.read_bytes() for p in target.rglob("*") if p.is_file()}


@pytest.mark.parametrize("name", ["services/example.py", "frontend/dist/index.html"])
def test_refuses_changed_online_file(staged, name):
    release, target = staged
    (target / name).write_text("online edits")
    with pytest.raises(ValueError, match="与备份"):
        verify_release(release, target)


def test_refuses_corrupted_payload(staged):
    release, target = staged
    (release / "payload/services/example.py").write_text("corrupted")
    with pytest.raises(ValueError, match="发布文件校验失败"):
        verify_release(release, target)


@pytest.mark.parametrize("name", ["services/new.py", "frontend/src/extra.js"])
def test_refuses_unexpected_existing_files(staged, name):
    release, target = staged
    (target / name).write_text("do not overwrite")
    with pytest.raises(ValueError):
        verify_release(release, target)


def test_refuses_extra_payload(staged):
    release, target = staged
    (release / "payload/extra.py").write_text("not in manifest")
    with pytest.raises(ValueError, match="文件集合"):
        verify_release(release, target)


def test_refuses_path_traversal(staged):
    release, target = staged
    manifest_path = release / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["expected_target"]["../outside"] = None
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="路径不安全"):
        verify_release(release, target)


def test_refuses_target_symlinks(staged, tmp_path):
    release, target = staged
    outside = tmp_path / "outside.py"
    outside.write_text("old source")
    (target / "services/example.py").unlink()
    (target / "services/example.py").symlink_to(outside)
    with pytest.raises(ValueError, match="目录之外|符号链接"):
        verify_release(release, target)
