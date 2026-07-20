"""构建连接 HTTPS 后端的 Trend2SKU Qwen GitHub Pages 前端。"""
from __future__ import annotations

import argparse
import html
import shutil
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SOURCE_HTML = FRONTEND / "index-qwen-live.html"
API_META = '<meta name="trend2sku-api-base" content="" />'


def normalize_api_base(value: str) -> str:
    candidate = value.strip().rstrip("/")
    if not candidate:
        return ""
    parsed = urlsplit(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("API Base 必须是不含凭据、查询参数或片段的 HTTPS 地址")
    return urlunsplit(("https", parsed.netloc, parsed.path.rstrip("/"), "", ""))


def build_site(output: Path, api_base: str = "") -> None:
    output = output.resolve()
    if output in {ROOT.resolve(), FRONTEND.resolve()}:
        raise ValueError("输出目录不能覆盖项目源码")
    normalized_api_base = normalize_api_base(api_base)

    source_html = SOURCE_HTML.read_text(encoding="utf-8")
    if source_html.count(API_META) != 1:
        raise RuntimeError("未找到唯一的 API Base 元数据标记")
    rendered_html = source_html.replace(
        API_META,
        (
            '<meta name="trend2sku-api-base" '
            f'content="{html.escape(normalized_api_base, quote=True)}" />'
        ),
    )

    if output.exists():
        shutil.rmtree(output)
    static = output / "static"
    static.mkdir(parents=True)
    (output / "index.html").write_text(rendered_html, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="ascii")

    for filename in ("app-qwen-live.js", "styles-qwen-live.css"):
        shutil.copy2(FRONTEND / filename, static / filename)
    shutil.copytree(FRONTEND / "assets", static / "assets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    parser.add_argument("--api-base", default="")
    args = parser.parse_args()
    build_site(args.output, args.api_base)
    print(f"GitHub Pages artifact: {args.output.resolve()}")


if __name__ == "__main__":
    main()
