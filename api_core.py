"""サーバー（FastAPI）とブラウザ版（Pyodide）で共通に使う処理．

設定（JSON）を受け取り → 入力チェック → コード生成 → そのコードを実行して画像にする，
までをここにまとめている．main.py と static/engine-worker.js はこれを呼ぶだけ．
"""
from __future__ import annotations

import base64
import json

from pydantic import ValidationError

from codegen import generate_code
from renderer import RenderError, render
from schemas import JP_FONTS, LATIN_FONTS, GraphSettings

MEDIA_TYPES = {"png": "image/png", "svg": "image/svg+xml", "pdf": "application/pdf"}
PREVIEW_PX = 1000  # プレビュー画像の幅（画素）


class ApiError(Exception):
    """利用者に見せるエラー（status は HTTP のステータスコード）．"""

    def __init__(self, status: int, errors: list[str], code: str | None = None):
        super().__init__("; ".join(errors))
        self.status = status
        self.errors = errors
        self.code = code

    def body(self) -> dict:
        return {"errors": self.errors, **({"code": self.code} if self.code else {})}


# ------------------------------------------------------------ エラーメッセージを日本語に

_MESSAGES = {
    "greater_than_equal": "{ge} 以上にしてください",
    "less_than_equal": "{le} 以下にしてください",
    "greater_than": "{gt} より大きくしてください",
    "string_too_long": "{max_length} 文字以内にしてください",
    "too_long": "{max_length} 個以内にしてください",
    "too_short": "{min_length} 個以上必要です",
    "literal_error": "選べる値は {expected} です",
    "string_pattern_mismatch": "形式が正しくありません",
    "float_parsing": "数値を入力してください",
    "float_type": "数値を入力してください",
    "missing": "入力がありません",
}


def japanese_error(err: dict) -> str:
    where = ".".join(str(p) for p in err.get("loc", []) if p != "body")
    template = _MESSAGES.get(err.get("type", ""))
    if template:
        try:
            ctx = {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in err.get("ctx", {}).items()}
            msg = template.format(**ctx)
        except KeyError:
            msg = err.get("msg", "")
    else:
        msg = err.get("msg", "").removeprefix("Value error, ")
    return f"{where}: {msg}" if where and err.get("type") != "value_error" else msg


def _render_error(e: Exception) -> list[str]:
    text = str(e)
    if "Parse" in text or "mathtext" in text.lower():  # matplotlib の数式（$...$）の書き間違い
        return [
            "タイトル・ラベル・見出しの中の数式（$ と $ で囲んだ部分）を読み取れませんでした．",
            "$ そのものを表示したいときは \\$ と入力してください．",
            f"詳細: {' '.join(text.split())}",
        ]
    return [f"グラフを描けませんでした: {text}"]


# ------------------------------------------------------------ 本体

def validate(payload: dict) -> GraphSettings:
    try:
        return GraphSettings.model_validate(payload)
    except ValidationError as e:
        raise ApiError(422, [japanese_error(err) for err in e.errors()]) from e


def render_preview(payload: dict) -> dict:
    """プレビュー画像（PNG, base64）と，それを作ったコードを返す．"""
    settings = validate(payload)
    code = generate_code(settings)
    try:
        image, messages = render(code, preview_px=PREVIEW_PX)
    except RenderError as e:
        raise ApiError(400, _render_error(e), code) from e
    return {"image": base64.b64encode(image).decode("ascii"), "code": code, "warnings": messages}


def export_file(payload: dict) -> tuple[bytes, str]:
    """ダウンロード用のファイルの中身と形式（png / svg / pdf）を返す．"""
    settings = validate(payload)
    code = generate_code(settings)
    try:
        image, _ = render(code)
    except RenderError as e:
        raise ApiError(400, _render_error(e)) from e
    return image, settings.output.format


def available_fonts() -> dict:
    """選べるフォントのうち，実際に使えるものを返す．"""
    import matplotlib_fontja  # noqa: F401  IPAexゴシックを登録する
    from matplotlib import font_manager

    installed = {f.name for f in font_manager.fontManager.ttflist}
    return {
        "latin": [f for f in LATIN_FONTS if f == "" or f in installed],
        "jp": [f for f in JP_FONTS if f in installed],
    }


# ------------------------------------------------------------ ブラウザ版（Pyodide）用の入口

def handle_json(kind: str, payload_json: str = "null") -> str:
    """ブラウザ版から呼ぶ．結果は {"status": HTTP 相当の番号, "body": ...} の JSON 文字列．"""
    try:
        if kind == "fonts":
            return json.dumps({"status": 200, "body": available_fonts()})
        payload = json.loads(payload_json)
        if kind == "render":
            return json.dumps({"status": 200, "body": render_preview(payload)})
        if kind == "export":
            data, fmt = export_file(payload)
            body = {"data": base64.b64encode(data).decode("ascii"), "format": fmt, "media_type": MEDIA_TYPES[fmt]}
            return json.dumps({"status": 200, "body": body})
        raise ApiError(404, [f"不明な処理です: {kind}"])
    except ApiError as e:
        return json.dumps({"status": e.status, "body": e.body()})
