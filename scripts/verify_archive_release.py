#!/usr/bin/env python3
"""Read-only verification of a staged archive release; never imports the app."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checked_path(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or str(relative) in ("", "."):
        raise ValueError(f"清单中的路径不安全：{name}")
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"路径指向目录之外：{name}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"路径包含符号链接，请人工核对：{name}")
    return path


def directory_files(root):
    if not root.is_dir():
        raise ValueError(f"目录不存在：{root.name}")
    result = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"目录中存在符号链接：{path.relative_to(root)}")
        if path.is_file() and path.name != ".DS_Store":
            result.add(path.relative_to(root).as_posix())
    return result


def verify_release(release, target):
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or manifest.get("before") != "2026-10-29":
        raise ValueError("发布清单版本或本次归档截止日期不正确")
    payload = release / "payload"
    if directory_files(payload) != set(manifest["payload"]):
        raise ValueError("发布文件集合与清单不一致")
    errors = []
    for name, expected in manifest["payload"].items():
        path = checked_path(payload, name)
        if file_digest(path) != expected:
            errors.append(f"发布文件校验失败：{name}")
    for name, expected in manifest["expected_target"].items():
        path = checked_path(target, name)
        if expected is None:
            if path.exists():
                errors.append(f"原本应不存在的目标文件已存在：{name}")
        elif not path.is_file() or file_digest(path) != expected:
            errors.append(f"线上文件与备份基线不同：{name}")
    dist = checked_path(target, "frontend/dist")
    actual_dist = directory_files(dist)
    if actual_dist != set(manifest["expected_dist"]):
        errors.append("线上 frontend/dist 文件集合已变化")
    for name, expected in manifest["expected_dist"].items():
        path = checked_path(dist, name)
        if not path.is_file() or file_digest(path) != expected:
            errors.append(f"线上前端构建文件与备份不同：frontend/dist/{name}")
    # Extra front-end source files could otherwise silently disappear from the
    # newly compiled application even though deployment does not delete them.
    for root in ("frontend/src", "frontend/public"):
        expected_files = {
            name.removeprefix(root + "/")
            for name, digest in manifest["expected_target"].items()
            if digest is not None and name.startswith(root + "/")
        }
        if directory_files(checked_path(target, root)) != expected_files:
            errors.append(f"线上 {root} 文件集合与构建基线不同")
    if errors:
        raise ValueError("\n".join(errors))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest = verify_release(args.release_dir.resolve(), args.target.resolve())
    except (ValueError, OSError, KeyError, TypeError) as exc:
        raise SystemExit(f"校验未通过，未修改任何文件或数据库：\n{exc}")
    print(f"校验通过：{len(manifest['payload'])} 个发布文件完整，线上代码及前端构建与备份基线一致。")
    print("仅完成只读校验：未复制文件、未迁移数据库、未重启服务、未归档订单。")
    print("归档范围仍固定为北京时间 2026-10-29 00:00 之前。")


if __name__ == "__main__":
    main()
