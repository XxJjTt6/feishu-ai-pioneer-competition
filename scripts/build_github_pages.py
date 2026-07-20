"""构建只包含浏览器运行资源的 GitHub Pages artifact。"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
APP_SCRIPT = '  <script src="static/app.js" defer></script>'
PAGES_SCRIPT = '  <script src="static/pages-demo.js" defer></script>'


def build_site(output: Path) -> None:
    output = output.resolve()
    if output in {ROOT.resolve(), FRONTEND.resolve()}:
        raise ValueError("输出目录不能覆盖项目源码")

    if output.exists():
        shutil.rmtree(output)
    static = output / "static"
    static.mkdir(parents=True)

    source_html = (FRONTEND / "index.html").read_text(encoding="utf-8")
    if source_html.count(APP_SCRIPT) != 1:
        raise RuntimeError("未找到唯一的前端入口脚本标记")
    pages_html = source_html.replace(APP_SCRIPT, f"{PAGES_SCRIPT}\n{APP_SCRIPT}")
    (output / "index.html").write_text(pages_html, encoding="utf-8")
    (output / ".nojekyll").write_text("", encoding="ascii")

    for filename in ("app.js", "pages-demo.js", "styles.css"):
        shutil.copy2(FRONTEND / filename, static / filename)
    shutil.copytree(FRONTEND / "assets", static / "assets")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build_site(args.output)
    print(f"GitHub Pages artifact: {args.output.resolve()}")


if __name__ == "__main__":
    main()
