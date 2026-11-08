import json
from pathlib import Path

import pytest

from config import settings
from scripts import archive_production_orders as cli


def test_backup_keeps_password_out_of_argv_and_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://allen:do-not-print@localhost/shop_test")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        assert "do-not-print" not in " ".join(args)
        if args[0] == "pg_dump":
            assert kwargs["env"]["PGPASSWORD"] == "do-not-print"
            Path(args[args.index("--file") + 1]).write_bytes(b"PGDMP-test-content")

    monkeypatch.setattr(cli.subprocess, "run", run)
    path = tmp_path / "backup.dump"
    cli.backup(path)
    assert len(calls) == 2
    assert path.stat().st_mode & 0o777 == 0o600
    metadata = Path(str(path) + ".json")
    assert metadata.stat().st_mode & 0o777 == 0o600
    assert "do-not-print" not in metadata.read_text()
    cli.validate_backup(path)
    with pytest.raises(ValueError, match="已存在"):
        cli.backup(path)


def test_backup_database_and_content_must_match(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://allen:secret@localhost/shop_test")
    monkeypatch.setattr(cli.subprocess, "run", lambda *args, **kwargs: None)
    path = tmp_path / "backup.dump"
    cli.backup(path)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://allen:secret@localhost/other_test")
    with pytest.raises(ValueError, match="不匹配"):
        cli.validate_backup(path)
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://allen:secret@localhost/shop_test")
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="校验失败"):
        cli.validate_backup(path)


def test_preview_files_are_private_and_never_overwritten(tmp_path):
    path = tmp_path / "preview.json"
    cli.write_json(path, {"snapshot": "真实业务明细"})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        cli.write_json(path, {})
    assert json.loads(path.read_text())["snapshot"] == "真实业务明细"
