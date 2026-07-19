#!/usr/bin/env python3
"""Build the minimal Trend2SKU source package from an explicit allowlist.

The packager intentionally refuses to overwrite an existing destination. Build
into a fresh staging directory, verify it, and only then promote that directory
to the final submission location.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "miniso-ai-product-studio-v1"

EXACT_FILES = (
    ".env.example",
    ".gitignore",
    "README.md",
    "requirements.txt",
    "requirements-dev.txt",
    "run.py",
    "frontend/index.html",
    "frontend/app.js",
    "frontend/styles.css",
    "frontend/assets/miniso-v1/mood-charm-v1.png",
    "frontend/assets/miniso-v1/city-scent-charm-v1.png",
    "frontend/assets/miniso-v1/cocreate-patch-kit-v1.png",
    "web/landing/index.html",
    "data/README.md",
    "data/make_sample.py",
    "docs/ai_vs_experience.md",
    "docs/methodology_whitepaper.md",
    "docs/references.md",
    "docs/报名提交材料.md",
    "docs/开题报告补充材料.md",
    "docs/迁移说明.md",
    "skills/voc-analysis/SKILL.md",
    "skills/working-backwards/SKILL.md",
    "scripts/pre_pr_check.py",
    "scripts/build_submission_documents_v1.py",
    "scripts/package_submission_v1.py",
    "deliverables/报名表_可直接粘贴文本_v1.txt",
)

GLOB_FILES = (
    "backend/miniso_studio/**/*.py",
    "backend/tests/test_*.py",
    "data/sample/*.jsonl",
)

FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    "__pycache__",
    "runs",
    "tmp",
    "processed",
    "generated",
    "report",
    "figures",
    "superpowers",
    ".cursor",
    ".learnings",
}

FORBIDDEN_NAMES = {
    ".env",
    "deploy.py",
    "update_hub.py",
    "server_exec.py",
    "cross_model_review.py",
    "开题报告_Part1_Part2.md",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_files() -> list[Path]:
    paths = {ROOT / relative for relative in EXACT_FILES}
    for pattern in GLOB_FILES:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())

    missing = [path for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError(
            "Allowlisted files are missing:\n" + "\n".join(str(path) for path in missing)
        )

    selected: list[Path] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        relative = path.relative_to(ROOT)
        if path.is_symlink():
            raise RuntimeError(f"Symlinks are not allowed: {relative}")
        if any(part in FORBIDDEN_PARTS for part in relative.parts):
            raise RuntimeError(f"Forbidden path entered allowlist: {relative}")
        if relative.name in FORBIDDEN_NAMES:
            raise RuntimeError(f"Forbidden file entered allowlist: {relative}")
        if relative.name.startswith(".env") and relative.name != ".env.example":
            raise RuntimeError(f"Secret-bearing env file entered allowlist: {relative}")
        selected.append(path)
    return selected


def write_manifest(package_dir: Path) -> Path:
    manifest = package_dir / "MANIFEST.sha256"
    files = sorted(
        (path for path in package_dir.rglob("*") if path.is_file() and path != manifest),
        key=lambda item: item.relative_to(package_dir).as_posix(),
    )
    lines = [f"{sha256(path)}  ./{path.relative_to(package_dir).as_posix()}" for path in files]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(package_dir: Path) -> None:
    manifest = package_dir / "MANIFEST.sha256"
    expected: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, relative = line.split("  ./", 1)
        expected[relative] = digest

    actual_files = {
        path.relative_to(package_dir).as_posix(): path
        for path in package_dir.rglob("*")
        if path.is_file() and path != manifest
    }
    if set(expected) != set(actual_files):
        missing = sorted(set(expected) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected))
        raise RuntimeError(f"Manifest file-set mismatch; missing={missing}, extra={extra}")
    mismatched = [name for name, path in actual_files.items() if sha256(path) != expected[name]]
    if mismatched:
        raise RuntimeError(f"Manifest checksum mismatch: {mismatched}")


def build_zip(package_dir: Path, zip_path: Path) -> None:
    fixed_time = (2026, 7, 19, 0, 0, 0)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(
            (item for item in package_dir.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(package_dir).as_posix(),
        ):
            archive_name = f"{PACKAGE_NAME}/{path.relative_to(package_dir).as_posix()}"
            info = zipfile.ZipInfo(archive_name, fixed_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    output_dir = args.output_dir.resolve()
    package_dir = output_dir / PACKAGE_NAME
    zip_path = output_dir / f"{PACKAGE_NAME}.zip"
    zip_checksum = output_dir / f"{PACKAGE_NAME}.zip.sha256"
    if package_dir.exists() or zip_path.exists() or zip_checksum.exists():
        raise FileExistsError("Refusing to overwrite an existing v1 package")

    output_dir.mkdir(parents=True, exist_ok=True)
    package_dir.mkdir()
    for source in collect_files():
        relative = source.relative_to(ROOT)
        destination = package_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    write_manifest(package_dir)
    verify_manifest(package_dir)
    build_zip(package_dir, zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        bad_file = archive.testzip()
        if bad_file is not None:
            raise RuntimeError(f"ZIP CRC check failed: {bad_file}")
    zip_checksum.write_text(
        f"{sha256(zip_path)}  {zip_path.name}\n",
        encoding="utf-8",
    )

    print(f"package_dir={package_dir}")
    print(f"zip={zip_path}")
    print(f"zip_sha256={sha256(zip_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
