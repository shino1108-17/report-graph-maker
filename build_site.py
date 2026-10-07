"""GitHub Pages で公開するサイトを _site/ に組み立てる．

  python build_site.py

_site/
├── index.html
└── static/
    ├── style.css, app.js, engine-worker.js
    └── py/   … ブラウザの中の Python（Pyodide）が読み込む，サーバー版と同じ Python ファイル
"""
from __future__ import annotations

import shutil
from pathlib import Path

BASE = Path(__file__).parent
SITE = BASE / "_site"
PY_FILES = ["schemas.py", "codegen.py", "renderer.py", "api_core.py"]


def build() -> Path:
    if SITE.exists():
        shutil.rmtree(SITE)
    shutil.copytree(BASE / "static", SITE / "static")
    shutil.move(SITE / "static" / "index.html", SITE / "index.html")
    (SITE / "static" / "py").mkdir()
    for name in PY_FILES:
        shutil.copy2(BASE / name, SITE / "static" / "py" / name)
    (SITE / ".nojekyll").touch()  # GitHub Pages に余計な変換をさせない
    return SITE


if __name__ == "__main__":
    print(f"{build()} にサイトを作りました")
