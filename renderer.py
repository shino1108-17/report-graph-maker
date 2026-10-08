"""codegen.py が作ったコードを実行して画像にする．

実行するのはサーバー自身が設定から生成したコードだけ（ユーザーのコードは受け取らない）．
"""
from __future__ import annotations

import io
import threading
import warnings

import matplotlib

matplotlib.use("Agg")  # サーバーでは画面を使わない
import matplotlib.pyplot as plt  # noqa: E402

# matplotlib は複数スレッドから同時に使うと壊れるので，1 つずつ順番に描く
_lock = threading.Lock()


class RenderError(Exception):
    pass


def _run(code: str):
    namespace: dict = {"__name__": "graph_app"}  # "__main__" ではないので自動保存は動かない
    exec(compile(code, "graph.py", "exec"), namespace)
    return namespace


def render(code: str, preview_px: int | None = None) -> tuple[bytes, list[str]]:
    """コードを実行して画像のバイト列を返す．

    preview_px を指定すると，幅がおよそその画素数になる PNG を返す（プレビュー用）．
    指定しなければ，コード内の save_graph() でそのまま保存する（ダウンロード用）．
    """
    buf = io.BytesIO()
    with _lock, matplotlib.rc_context(), warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        fig = None
        try:
            ns = _run(code)
            fig = ns["draw_graph"]()
            if preview_px is None:
                ns["save_graph"](fig, buf)
            else:
                width_inch = fig.get_figwidth()
                dpi = round(max(50, min(600, preview_px / width_inch)))  # 整数にする（小数は非推奨）
                fig.savefig(buf, format="png", dpi=dpi, transparent=ns["TRANSPARENT"])
        except Exception as e:  # matplotlib の数式（$...$）の書き間違いなど
            raise RenderError(f"{type(e).__name__}: {e}") from e
        finally:
            if fig is not None:
                plt.close(fig)
            plt.close("all")
    # 利用者に役立つ警告（文字が無い等）だけを返す．ライブラリの「非推奨」の警告は開発者向けなので除く
    messages = sorted({_friendly(str(w.message)) for w in caught if not issubclass(w.category, DeprecationWarning)})
    return buf.getvalue(), messages


# よく出る matplotlib の警告を，分かりやすい日本語にする
_FRIENDLY = {
    "constrained_layout not applied": "文字や凡例が図に対して大きすぎて，余白を自動で調整できませんでした．"
                                      "図を大きくするか，文字を小さくしてください（近似曲線の式は凡例の外に出すと収まることがあります）．",
}


def _friendly(message: str) -> str:
    for key, text in _FRIENDLY.items():
        if key in message:
            return text
    return message
