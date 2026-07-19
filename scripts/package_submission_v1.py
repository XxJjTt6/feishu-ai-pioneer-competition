#!/usr/bin/env python3
"""Build the minimal Trend2SKU v2 source package from an explicit allowlist.

The legacy script filename is retained for command compatibility. The packager
refuses to overwrite existing artifacts and scans allowlisted text before copy;
binary assets are copied as bytes and are never decoded as text.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import re
import shutil
import stat
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "miniso-ai-product-studio-v2"

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
    "backend/miniso_studio/infrastructure/llm/qwen.py",
    "backend/tests/test_dynamic_api_input.py",
    "backend/tests/test_qwen_provider.py",
    "skills/voc-analysis/SKILL.md",
    "skills/working-backwards/SKILL.md",
    "scripts/pre_pr_check.py",
    "scripts/build_submission_documents_v1.py",
    "scripts/package_submission_v1.py",
    "deliverables/报名表_可直接粘贴文本_v1.txt",
    "deliverables/提交清单_v2.md",
)

GLOB_FILES = (
    "backend/miniso_studio/**/*.py",
    "backend/tests/test_*.py",
    "data/sample/*.jsonl",
)

FORBIDDEN_PARTS = {
    ".git",
    ".venv",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "__pycache__",
    "node_modules",
    "runs",
    "screenshots",
    "tmp",
    "processed",
    "generated",
    "report",
    "reports",
    "figures",
    "superpowers",
    ".cursor",
    ".learnings",
}

FORBIDDEN_NAMES = {
    ".env",
    ".coverage",
    ".DS_Store",
    "deploy.py",
    "update_hub.py",
    "server_exec.py",
    "cross_model_review.py",
    "开题报告_Part1_Part2.md",
}

TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".jsonl",
    ".md",
    ".py",
    ".txt",
}
TEXT_NAMES = {".env.example", ".gitignore"}

# Split high-risk markers so this scanner can safely include and scan itself.
FORBIDDEN_TEXT_MARKERS = (
    ("restricted key prefix", ("sk-" + "sp-").casefold()),
    ("authorization header", ("authorization" + " bearer").casefold()),
    ("authorization header", ("authorization:" + " bearer").casefold()),
    ("local user path", ("/" + "Users/").casefold()),
)
AUTHORIZATION_PATTERN = re.compile(
    "authorization" + r"\s*:?\s*bearer\s+[^\s\"'{}]+",
    re.IGNORECASE,
)
EMAIL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![A-Za-z0-9.-])"
)
IPV4_PATTERN = re.compile(
    r"(?<![\d.])(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\d.])"
)
SENSITIVE_ENV_NAME_PATTERN = re.compile(
    r"(?:API_KEY|TOKEN|PASSWORD|SECRET)$",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_text_file(path: Path) -> bool:
    if path.name not in TEXT_NAMES and path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    with path.open("rb") as handle:
        return b"\x00" not in handle.read(8192)


def _is_public_ip(value: str) -> bool:
    address = ipaddress.ip_address(value)
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def scan_forbidden_content(paths: list[Path]) -> None:
    violations: list[str] = []
    for path in sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix()):
        if not _is_text_file(path):
            continue
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        folded = text.casefold()
        for label, marker in FORBIDDEN_TEXT_MARKERS:
            if marker in folded:
                violations.append(f"{relative}: {label}")
        if AUTHORIZATION_PATTERN.search(text):
            violations.append(f"{relative}: authorization header")
        if EMAIL_PATTERN.search(text):
            violations.append(f"{relative}: email address")
        for value in IPV4_PATTERN.findall(text):
            if _is_public_ip(value):
                violations.append(f"{relative}: public IP address")
    if violations:
        raise RuntimeError(
            "Forbidden content detected in allowlisted text:\n"
            + "\n".join(sorted(set(violations)))
        )


def validate_env_example() -> None:
    example = ROOT / ".env.example"
    for line_number, raw_line in enumerate(
        example.read_text(encoding="utf-8").splitlines(),
        1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if SENSITIVE_ENV_NAME_PATTERN.search(name.strip()) and value.strip():
            raise RuntimeError(
                f".env.example contains a non-empty sensitive value at line {line_number}"
            )


def collect_files() -> list[Path]:
    paths = {ROOT / relative for relative in EXACT_FILES}
    for pattern in GLOB_FILES:
        paths.update(path for path in ROOT.glob(pattern) if path.is_file())

    missing = sorted(
        path.relative_to(ROOT).as_posix() for path in paths if not path.exists()
    )
    if missing:
        raise FileNotFoundError(
            "Allowlisted files are missing:\n" + "\n".join(missing)
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
        if relative.parts[0] == "deliverables" and relative.suffix.lower() in {
            ".docx",
            ".jpeg",
            ".jpg",
            ".pdf",
            ".png",
            ".webp",
        }:
            raise RuntimeError(f"Old report or screenshot entered allowlist: {relative}")
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
        raise FileExistsError("Refusing to overwrite existing package artifacts")

    validate_env_example()
    selected_files = collect_files()
    scan_forbidden_content(selected_files)
    output_dir.mkdir(parents=True, exist_ok=True)
    package_dir.mkdir()
    for source in selected_files:
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

    print(f"package_name={PACKAGE_NAME}")
    print(f"zip_name={zip_path.name}")
    print(f"zip_sha256={sha256(zip_path)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileExistsError, FileNotFoundError, RuntimeError) as exc:
        raise SystemExit(f"packaging_error: {exc}") from None
