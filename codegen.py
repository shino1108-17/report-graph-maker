"""グラフ設定（GraphSettings）から，単体で実行できる matplotlib のコードを作る．

ここで作ったコード文字列を
  ・画面に表示する
  ・サーバーで実行して画像を作る
の両方に使うので，表示内容と実際の画像がずれない．

【安全のための決まり】
ユーザーが入力した文字列（見出し・タイトルなど）は，必ず repr() で Python の
文字列リテラルにしてから埋め込む．コメントの中には入れない（改行でコメントから
抜け出されるのを防ぐため）．数値は float にしてから repr() で埋め込む．
"""
from __future__ import annotations

import math
import unicodedata

from schemas import SERIF_FONTS, GraphSettings, ParsedData, parse_data

CHART_NAMES = {
    "scatter": "散布図（点のみ）",
    "scatter_line": "散布図（直線とマーカー）",
    "line": "折れ線",
    "bar": "棒グラフ（縦）",
}
LINESTYLE_NAMES = {"-": "実線", "--": "破線", ":": "点線", "-.": "一点鎖線", "none": "線なし"}
MARKER_NAMES = {"o": "丸", "s": "四角", "^": "上三角", "v": "下三角", "D": "ひし形",
                "x": "×", "+": "＋", "*": "星", "none": "点なし"}
LEGEND_NAMES = {
    "best": "データと重ならない場所を自動で選ぶ",
    "upper right": "右上", "upper left": "左上", "lower right": "右下", "lower left": "左下",
}
ERROR_NAMES = {
    "sd": "標準偏差（繰り返し測定から計算）",
    "se": "標準誤差 = 標準偏差 / √(測定回数)（繰り返し測定から計算）",
}
TREND_NAMES = {
    "linear": "1 次式（直線） y = ax + b",
    "poly2": "2 次式 y = ax² + bx + c",
    "poly3": "3 次式 y = ax³ + bx² + cx + d",
    "exp": "指数 y = a·e^(bx)",
    "log": "対数 y = a·ln(x) + b",
    "power": "累乗 y = a·x^b",
}
ERRORBAR_LINEWIDTH = 0.8
GRID_COLOR = "#d0d0d0"
OUTER_BORDER_COLOR = "#808080"


def _str(text: str) -> str:
    """文字列を Python の文字列リテラルにする（repr を使うので安全．なるべく "..." で囲む）．"""
    r = repr(text)
    if r.startswith("'") and '"' not in text:
        # repr が '...' を選ぶのは「' も " も含まない」か「両方含む」とき．" を含まないなら前者
        r = '"' + r[1:-1] + '"'
    return r


def _str_list(values: list[str]) -> str:
    return "[" + ", ".join(_str(v) for v in values) + "]"


def _width(text: str) -> int:
    """表示幅（全角文字は 2 と数える）．コメントの位置を揃えるのに使う．"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text: str, width: int) -> str:
    return text + " " * max(1, width - _width(text))


def _num(v: float | None) -> str:
    """数値をコード用の文字列にする（None は空欄 = np.nan）．"""
    if v is None:
        return "np.nan"
    v = float(v)
    return repr(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)


def _num_list(values: list[float | None]) -> str:
    return "[" + ", ".join(_num(v) for v in values) + "]"


def _mm(v: float) -> str:
    return f"{v:g}"


class _Code:
    """インデント付きで 1 行ずつコードを書きためる小さな道具．"""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.indent = 0

    def __call__(self, line: str = "") -> None:
        self.lines.append(("    " * self.indent + line) if line else "")

    def text(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def generate_code(s: GraphSettings) -> str:
    d: ParsedData = parse_data(s.data, s.chart_type)
    w = _Code()
    ct = s.chart_type
    is_scatter = ct in ("scatter", "scatter_line")
    out = s.output
    n_points = len(d.x) if is_scatter else len(d.x_labels)
    styles = [s.series[g.style] for g in d.groups]          # 系列ごとの見た目の設定
    trends = [st.trend if is_scatter else "none" for st in styles]  # 近似曲線は散布図のときだけ
    has_trials = any(len(g.trials) > 1 for g in d.groups)
    has_percent = any(st.error == "percent" for st in styles)
    tickers = []  # matplotlib.ticker から使う道具
    if (is_scatter and s.x_axis.step and not s.x_axis.log) or (s.y_axis.step and not s.y_axis.log):
        tickers.append("MultipleLocator")
    if (is_scatter and s.x_axis.tick_decimals is not None) or s.y_axis.tick_decimals is not None:
        tickers.append("FormatStrFormatter")
    if any(_integer_ticks(s, a) for a in "xy"):
        tickers.append("MaxNLocator")
    if s.minor_ticks and not is_scatter:
        tickers.append("AutoMinorLocator")

    # ======================================================== ヘッダ
    w('"""')
    w(f"実験レポート用グラフ作成アプリが生成したコードです（{CHART_NAMES[ct]}）．")
    w(f"このファイルを実行すると，同じグラフが graph.{out.format} に保存されます．")
    w()
    w("  実行方法:   python graph.py")
    w("  必要なもの: pip install matplotlib numpy" + (" matplotlib-fontja" if s.font.jp == "IPAexGothic" else ""))
    w()
    w("コードの構成:")
    w("  1. データ        … 表に入力した値と，系列ごとの見た目")
    w("  2. 保存の設定    … ファイル名・解像度・背景")
    w("  3. draw_graph()  … グラフを描く")
    w("  4. save_graph()  … ファイルに保存する")
    w('"""')
    w("import matplotlib")
    w('matplotlib.use("Agg")  # 画面に表示せず，画像ファイルを作るだけの設定')
    w("import matplotlib.pyplot as plt")
    w("import numpy as np")
    if has_trials:
        w("import warnings")
    if tickers:
        w(f"from matplotlib.ticker import {', '.join(tickers)}  # 目盛りを細かく設定するための道具")
    if s.font.jp == "IPAexGothic":
        w("import matplotlib_fontja  # 日本語フォント（IPAexゴシック）を使えるようにする")
    w()

    # ======================================================== 1. データ
    w("# ===== 1. データ（表に入力した値） =====")
    w("# np.nan は「空欄」の意味（その点は描かれない）")
    w(f"x_title = {_str(d.x_name)}  # 1列目（X）の見出し")
    if is_scatter:
        w(f"x = {_num_list(d.x)}")
    else:
        w("# 折れ線・棒グラフでは，X は「項目名」として等間隔に並べる（Excel と同じ）")
        w(f"x_labels = {_str_list(d.x_labels)}")
    w()
    w("# 系列（2列目以降）ごとのデータと見た目")
    w("series = [")
    for i, (g, st, trend) in enumerate(zip(d.groups, styles, trends)):
        first = i == 0  # 見た目の説明コメントは最初の系列にだけ付ける

        def item(key: str, value: str, comment: str, always: bool = False) -> None:
            pad = f'        "{key}": {value},'
            w(_pad(pad, 40) + f" # {comment}" if (first or always) and comment else pad)

        w("    {")
        item("name", _str(g.name), "凡例に表示される名前")
        if len(g.trials) > 1:
            w(f"        # 繰り返し測定（{len(g.trials)} 回分．1 行が 1 回分）．平均を計算して描く")
            w('        "trials": [')
            for values in g.trials:
                w(f"            {_num_list(values)},")
            w("        ],")
        else:
            item("y", _num_list(g.y), "")
        if st.error == "column" and g.err is not None:
            item("yerr", _num_list(g.err), "誤差棒の大きさ（「誤差」の列の値．± この値）", always=True)
        elif st.error in ("sd", "se"):
            item("error", _str(st.error), f"誤差棒: {ERROR_NAMES[st.error]}", always=True)
        elif st.error == "fixed":
            item("yerr", _num(st.error_value), "誤差棒: すべての点で ± この値", always=True)
        elif st.error == "percent":
            item("error_percent", _num(st.error_value), "誤差棒: 値の ± この % ", always=True)
        item("color", _str(st.color), "色（#RRGGBB 形式）")
        if ct in ("scatter_line", "line"):
            item("linestyle", _str(st.linestyle),
                 f"線の種類: {LINESTYLE_NAMES[st.linestyle]}（\"-\" 実線 / \"--\" 破線 / \":\" 点線 / \"-.\" 一点鎖線）")
            item("linewidth", _num(st.line_width), "線の太さ [pt]")
        if ct != "bar":
            item("marker", _str(st.marker),
                 f"点の形: {MARKER_NAMES[st.marker]}（\"o\" 丸 / \"s\" 四角 / \"^\" 三角 / \"D\" ひし形 / \"none\" なし）")
            item("markersize", _num(st.marker_size), "点の大きさ [pt]")
            face = st.color if st.marker_fill else "white"
            item("markerfacecolor", _str(face), "点の中の色（\"white\" にすると白抜き）")
        if trend != "none":
            item("trend", _str(trend), f"近似曲線: {TREND_NAMES[trend]}", always=True)
            item("show_equation", str(st.trend_equation), "近似曲線の式を表示する", always=True)
            item("show_r2", str(st.trend_r2), "決定係数 R² を表示する", always=True)
        w("    },")
    w("]")
    w()
    if has_trials or has_percent:
        _write_error_calc(w, styles, d)
    if any(t != "none" for t in trends):
        _write_fit_function(w, sorted({t for t in trends if t != "none"}, key=list(TREND_NAMES).index))

    # ======================================================== 2. 保存の設定
    w("# ===== 2. 保存の設定 =====")
    w(_pad(f'SAVE_FILE = "graph.{out.format}"', 30) + "# 保存するファイル名")
    w(_pad(f'SAVE_FORMAT = "{out.format}"', 30) + '# 形式（"png" / "svg" / "pdf"）')
    w(_pad(f"SAVE_DPI = {out.dpi}", 30) + "# 解像度 [dpi]（PNG のときに効く．大きいほど細かい）")
    w(_pad(f"TRANSPARENT = {out.transparent}", 30) + "# True にすると背景が透明になる")
    w()
    w("MM = 1 / 25.4  # 1 mm をインチに直す係数（matplotlib の大きさの単位はインチ）")
    w()
    w()

    # ======================================================== 3. draw_graph
    w("def draw_graph():")
    w.indent += 1
    w('"""グラフを描いて Figure（図全体）を返す"""')
    _write_fonts(w, s, d)
    w()
    w(f"# ----- 図の大きさ: 幅 {_mm(s.size.width_mm)} mm × 高さ {_mm(s.size.height_mm)} mm -----")
    w('# layout="constrained" は，文字がはみ出さないように余白を自動で調整する設定')
    w(f"fig, ax = plt.subplots(figsize=({_mm(s.size.width_mm)} * MM, {_mm(s.size.height_mm)} * MM), "
      'layout="constrained")')
    w()
    _write_plot(w, s, n_points, any_error=any(st.error != "none" for st in styles))
    if any(t != "none" for t in trends):
        _write_trend_plot(w, s)
    _write_axes(w, s, d, is_scatter, any_error=any(st.error != "none" for st in styles))
    _write_legend(w, s, d)
    _write_frame(w, s)
    w("return fig")
    w.indent -= 1
    w()
    w()

    # ======================================================== 4. save_graph
    w("def save_graph(fig, file):")
    w('    """図をファイルに保存する（file はファイル名，またはメモリ上のファイル）"""')
    w("    # bbox_inches は指定しない → 画像の大きさが指定した mm ぴったりになる")
    w("    fig.savefig(file, format=SAVE_FORMAT, dpi=SAVE_DPI, transparent=TRANSPARENT)")
    w()
    w()
    w('if __name__ == "__main__":')
    w("    fig = draw_graph()")
    w("    save_graph(fig, SAVE_FILE)")
    w('    print(SAVE_FILE, "に保存しました")')
    return w.text()


# ------------------------------------------------------------------ 部品

def _is_math_text(text: str) -> bool:
    """matplotlib が数式として扱う文字列か（$ が偶数個．\\$ は数えない）．"""
    n = text.count("$") - text.count("\\$")
    return n > 0 and n % 2 == 0


def _mixes_math_and_japanese(text: str) -> bool:
    return _is_math_text(text) and any(ord(ch) > 127 for ch in text)


def _needs_jp_font_variable(s: GraphSettings, d: ParsedData) -> bool:
    candidates = [s.data.columns[0].strip(), s.x_axis.label, s.y_axis.label]
    if s.title.show:
        candidates.append(s.title.text)
    if s.legend.show or len(d.names) == 1:  # 凡例か，Y 軸ラベル（系列が 1 つのとき）に使われる
        candidates += d.names
    return any(_mixes_math_and_japanese(t.strip()) for t in candidates)


def _write_error_calc(w: _Code, styles, d: ParsedData) -> None:
    """繰り返し測定の平均・標準偏差と，割合で指定した誤差棒を計算するコード．"""
    used = {st.error for g, st in zip(d.groups, styles) if len(g.trials) > 1}
    has_trials = any(len(g.trials) > 1 for g in d.groups)
    w("# ===== 繰り返し測定の平均・標準偏差と，誤差棒の大きさを計算する =====")
    w("for s in series:")
    if has_trials:
        w('    if "trials" in s:')
        w('        trials = np.array(s["trials"], dtype=float)  # 行: 何回目の測定か，列: 各点')
        w("        with warnings.catch_warnings():")
        w('            warnings.simplefilter("ignore", RuntimeWarning)  # 測定が 1 回しかない点などの警告を出さない')
        w('            s["y"] = np.nanmean(trials, axis=0)  # 平均')
        if used & {"sd", "se"}:
            w("            sd = np.nanstd(trials, axis=0, ddof=1)  # 標準偏差（不偏標準偏差: n - 1 で割る）")
        if "sd" in used:
            w('        if s.get("error") == "sd":')
            w('            s["yerr"] = sd')
        if "se" in used:
            w("        n = np.sum(~np.isnan(trials), axis=0)  # 点ごとの測定回数")
            w('        if s.get("error") == "se":')
            w('            s["yerr"] = sd / np.sqrt(n)  # 標準誤差 = 標準偏差 / √n')
    if any(st.error == "percent" for st in styles):
        w('    if "error_percent" in s:')
        w('        s["yerr"] = np.abs(np.array(s["y"], dtype=float)) * s["error_percent"] / 100')
    w()


# 近似曲線の種類ごとの計算（生成するコードにそのまま書く）
_FIT_BRANCHES = {
    "linear": [
        "# y = ax + b",
        "a, b = np.polyfit(x, y, 1)",
        "f = lambda t: a * t + b",
        'equation = f"$y = {a:.4g}x {b:+.4g}$"',
    ],
    "poly2": [
        "# y = ax² + bx + c",
        "a, b, c = np.polyfit(x, y, 2)",
        "f = lambda t: a * t**2 + b * t + c",
        'equation = f"$y = {a:.4g}x^2 {b:+.4g}x {c:+.4g}$"',
    ],
    "poly3": [
        "# y = ax³ + bx² + cx + d",
        "a, b, c, d = np.polyfit(x, y, 3)",
        "f = lambda t: a * t**3 + b * t**2 + c * t + d",
        'equation = f"$y = {a:.4g}x^3 {b:+.4g}x^2 {c:+.4g}x {d:+.4g}$"',
    ],
    "exp": [
        "# y = a e^(bx)．両辺の対数をとると ln y = ln a + bx の直線になるので，それを当てはめる",
        "b, log_a = np.polyfit(x, np.log(y), 1)",
        "a = np.exp(log_a)",
        "f = lambda t: a * np.exp(b * t)",
        'equation = rf"$y = {a:.4g}\\,e^{{{b:.4g}x}}$"',
    ],
    "log": [
        "# y = a ln(x) + b",
        "a, b = np.polyfit(np.log(x), y, 1)",
        "f = lambda t: a * np.log(t) + b",
        'equation = rf"$y = {a:.4g}\\,\\ln x {b:+.4g}$"',
    ],
    "power": [
        "# y = a x^b．両辺の対数をとると ln y = ln a + b ln x の直線になるので，それを当てはめる",
        "b, log_a = np.polyfit(np.log(x), np.log(y), 1)",
        "a = np.exp(log_a)",
        "f = lambda t: a * t**b",
        'equation = rf"$y = {a:.4g}\\,x^{{{b:.4g}}}$"',
    ],
}


def _write_fit_function(w: _Code, kinds: list[str]) -> None:
    w()
    w("def fit_trend(kind, x, y):")
    w('    """近似曲線を最小二乗法で求める．')
    w("    戻り値: (曲線を描くための x, 曲線の y, 式の文字列, 決定係数 R²)")
    w('    """')
    w("    x = np.asarray(x, dtype=float)")
    w("    y = np.asarray(y, dtype=float)")
    w("    ok = ~(np.isnan(x) | np.isnan(y))  # 空欄の点は使わない")
    w("    x, y = x[ok], y[ok]")
    for i, kind in enumerate(kinds):
        w(f'    {"if" if i == 0 else "elif"} kind == {_str(kind)}:')
        for line in _FIT_BRANCHES[kind]:
            w("        " + line)
    w("    # 決定係数 R²（1 に近いほど，近似曲線がデータによく合っている）")
    w("    ss_res = np.sum((y - f(x)) ** 2)  # 残差の二乗和")
    w("    ss_tot = np.sum((y - np.mean(y)) ** 2)  # 平均からのずれの二乗和")
    w("    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0")
    w("    fit_x = np.linspace(x.min(), x.max(), 200)  # 曲線を滑らかに描くための x")
    w("    return fit_x, f(fit_x), equation, r2")
    w()


def _write_trend_plot(w: _Code, s: GraphSettings) -> None:
    w("# ----- 近似曲線（破線） -----")
    w("count = 0  # 式を書いた数（グラフの中に書くときの位置をずらすため）")
    w("for s in series:")
    w('    if "trend" not in s:')
    w("        continue")
    w('    fit_x, fit_y, equation, r2 = fit_trend(s["trend"], x, s["y"])')
    w("    parts = []")
    w('    if s["show_equation"]:')
    w("        parts.append(equation)")
    w('    if s["show_r2"]:')
    w('        parts.append(f"$R^2$ = {r2:.4f}")')
    w('    text = "\\n".join(parts)  # 式と R² は 2 行に分けて書く')
    if s.legend.show:
        w(f'    ax.plot(fit_x, fit_y, linestyle="--", linewidth={ERRORBAR_LINEWIDTH}, color=s["color"],')
        w("            label=text or None)  # 式と R² は凡例に表示する")
    else:
        w(f'    ax.plot(fit_x, fit_y, linestyle="--", linewidth={ERRORBAR_LINEWIDTH}, color=s["color"])')
        w("    if text:  # 凡例が無いので，式と R² はグラフの左上に書く")
        w('        ax.text(0.03, 0.97 - 0.16 * count, text, transform=ax.transAxes,')
        w('                ha="left", va="top", color=s["color"],')
        w("                in_layout=False)  # 余白の自動調整では無視する（グラフの中に書く文字なので）")
        w("        count += 1")
    w()


def _integer_ticks(s: GraphSettings, axis: str) -> bool:
    """小数点以下 0 桁で表示し，目盛り間隔が自動のときは，整数の位置にだけ目盛りを打つ．"""
    a = s.x_axis if axis == "x" else s.y_axis
    if axis == "x" and s.chart_type not in ("scatter", "scatter_line"):
        return False
    return a.tick_decimals == 0 and a.step is None and not a.log


def _write_fonts(w: _Code, s: GraphSettings, d: ParsedData) -> None:
    f = s.font
    families = [f.latin, f.jp] if f.latin else [f.jp]
    serif = (f.latin in SERIF_FONTS) if f.latin else (f.jp in SERIF_FONTS)
    w("# ----- フォントと文字の大きさ -----")
    if f.latin:
        w(f"# 英数字は {f.latin}，日本語は {f.jp} で表示する（左のフォントから順に文字を探す）")
    w(f'plt.rcParams["font.family"] = {_str_list(families)}')
    w(f'plt.rcParams["mathtext.fontset"] = {_str("stix" if serif else "dejavusans")}  '
      "# 数式（$...$）の書体を本文に合わせる")
    if _needs_jp_font_variable(s, d):
        w("# 数式（$...$）と日本語が混ざった文字は，フォントの併用が効かず日本語が □ になるので，")
        w("# その文字だけ日本語フォントで書く（数式の部分は上の数式用の書体になる）")
        w(f"jp_font = {_str(f.jp)}")
    w(f'plt.rcParams["font.size"] = {_num(f.size)}  # 文字の大きさ [pt]')
    w('plt.rcParams["pdf.fonttype"] = 42  # PDF にフォントを埋め込む（文字化け防止）')
    d = s.tick_direction
    w(f'plt.rcParams["xtick.direction"] = {_str(d)}  # 目盛りの向き（"in" 内側 / "out" 外側）')
    w(f'plt.rcParams["ytick.direction"] = {_str(d)}')


def _write_plot(w: _Code, s: GraphSettings, n_points: int, any_error: bool) -> None:
    ct = s.chart_type
    labels = s.data_labels
    fmt = f"{{:.{labels.decimals}f}}"
    w(f"# ----- データを描く（{CHART_NAMES[ct]}） -----")
    cap = _num(s.error_capsize)
    if any_error:
        w(f"# 誤差棒の端の横線の長さ {cap} pt，誤差棒の線の太さ {ERRORBAR_LINEWIDTH} pt")

    if ct in ("line", "bar"):
        w("positions = np.arange(len(x_labels))  # 項目を 0, 1, 2, ... の位置に等間隔で並べる")

    plot = "ax.errorbar(" if any_error else "ax.plot("
    yerr = '        yerr=s.get("yerr"),  # 誤差棒の大きさ（無い系列は None → 誤差棒なし）'
    errstyle = f"        capsize={cap}, elinewidth={ERRORBAR_LINEWIDTH}, capthick={ERRORBAR_LINEWIDTH},"
    if ct == "scatter":
        w("for s in series:")
        w("    " + plot)
        w('        x, s["y"],')
        if any_error:
            w(yerr)
            w(errstyle)
        w('        linestyle="none",  # 線は引かない（点のみ）')
        w('        marker=s["marker"], markersize=s["markersize"],')
        w('        color=s["color"], markerfacecolor=s["markerfacecolor"],')
        w('        label=s["name"],')
        w("    )")
    elif ct in ("scatter_line", "line"):
        xs = "x" if ct == "scatter_line" else "positions"
        w("for s in series:")
        w("    " + plot)
        w(f'        {xs}, s["y"],')
        if any_error:
            w(yerr)
            w(errstyle)
        w('        linestyle=s["linestyle"], linewidth=s["linewidth"],')
        w('        marker=s["marker"], markersize=s["markersize"],')
        w('        color=s["color"], markerfacecolor=s["markerfacecolor"],')
        w('        label=s["name"],')
        w("    )")
    else:  # bar
        w("n = len(series)")
        w("width = 0.8 / n  # 棒 1 本の幅（1 項目ぶんの幅 0.8 を系列の数で分ける）")
        w("for i, s in enumerate(series):")
        w("    offset = (i - (n - 1) / 2) * width  # 系列ごとに棒を左右にずらす")
        w("    bars = ax.bar(")
        w('        positions + offset, s["y"], width,')
        if any_error:
            w(yerr)
            w(f'        capsize={cap}, error_kw={{"elinewidth": {ERRORBAR_LINEWIDTH}, "capthick": {ERRORBAR_LINEWIDTH}}},')
        w('        color=s["color"], edgecolor="black", linewidth=0.5,  # 棒の色と黒い縁取り')
        w('        label=s["name"],')
        w("    )")
        if labels.show:
            w(f"    # データラベル（棒の上に値を表示．小数点以下 {labels.decimals} 桁）")
            w(f'    texts = ["" if np.isnan(v) else {_str(fmt)}.format(v) for v in s["y"]]')
            w("    ax.bar_label(bars, labels=texts, padding=2)")
    w()

    if labels.show and ct != "bar":
        xs = "x" if ct in ("scatter", "scatter_line") else "positions"
        w(f"# ----- データラベル（各点に値を表示．小数点以下 {labels.decimals} 桁） -----")
        w("for s in series:")
        w(f'    for xi, yi in zip({xs}, s["y"]):')
        w("        if np.isnan(xi) or np.isnan(yi):")
        w("            continue  # 空欄の点は飛ばす")
        w(f"        ax.annotate({_str(fmt)}.format(yi), (xi, yi),")
        w('                    textcoords="offset points", xytext=(0, 4),  # 点の 4pt 上に書く')
        w('                    ha="center", va="bottom")')
        w()
    if ct in ("line", "bar"):
        step = max(1, math.ceil(n_points / 12))
        w("# ----- X 軸の項目名 -----")
        if step > 1:
            w(f"# 項目が多いので {step} 個おきに表示する")
            w(f"ax.set_xticks(positions[::{step}], labels=x_labels[::{step}])")
        else:
            w("ax.set_xticks(positions, labels=x_labels)")
        w("ax.set_xlim(-0.5, len(x_labels) - 0.5)  # 両端に半項目ぶんの余白")
        w()


def _write_axes(w: _Code, s: GraphSettings, d: ParsedData, is_scatter: bool, any_error: bool) -> None:
    w("# ----- 軸の範囲と目盛り -----")
    wrote = False
    if is_scatter:
        wrote |= _axis_range(w, "x", s.x_axis, bottom_zero=False)
    ys = [v for y in d.ys for v in y if v is not None]
    y = s.y_axis
    zero_ok = y.start_zero and not y.log and all(v >= 0 for v in ys)
    if y.start_zero and not zero_ok and y.min is None:
        reason = "対数目盛りなので" if y.log else "Y に負の値があるので"
        w(f"# （{reason}「Y 軸を 0 から始める」は使っていません）")
    if zero_ok and y.min is None and y.max is None and ys and max(ys) > 0:
        # 0 から始めるとき，上端は「データの最大値 + 余白」にする
        # （自動の余白はデータの範囲だけを見て決まるので，0 を含めると上の点が枠にかかる）
        factor = 1.15 if s.data_labels.show else 1.05
        note = "15%（データラベルの分も）" if s.data_labels.show else "5%"
        if any_error:
            w(f"# Y 軸を 0 から始める．上端は（誤差棒の上の端も含めた）データの最大値より {note} 上にする")
            w("y_tops = np.concatenate([")
            w('    np.asarray(s["y"], dtype=float) + np.nan_to_num(np.asarray(s.get("yerr", 0), dtype=float))')
            w("    for s in series")
            w("])")
            w("y_max = np.nanmax(y_tops)")
        else:
            w(f"# Y 軸を 0 から始める．上端はデータの最大値より {note} 上にする")
            w('y_max = np.nanmax([v for s in series for v in s["y"]])')
        w(f"ax.set_ylim(0, y_max * {factor})")
        if y.step:
            w(f"ax.yaxis.set_major_locator(MultipleLocator({_num(y.step)}))  # 目盛りの間隔")
        wrote = True
    else:
        wrote |= _axis_range(w, "y", y, bottom_zero=zero_ok)
    if s.data_labels.show and y.max is None and not y.log and not (zero_ok and y.min is None):
        w("# データラベルが枠からはみ出さないよう，上に 1 割ほど余白を足す")
        w("y_bottom, y_top = ax.get_ylim()")
        w("ax.set_ylim(top=y_top + (y_top - y_bottom) * 0.1)")
        wrote = True
    if not wrote:
        w("# （範囲・目盛り間隔は自動）")
    w()

    # (関数, 表示する文字, コードに書く式, コメント)
    texts = []
    if s.title.show and s.title.text.strip():
        t = s.title.text.strip()
        texts.append(("set_title", t, _str(t), ""))
    if s.x_axis.show_label:
        t = s.x_axis.label.strip()
        texts.append(("set_xlabel", t, _str(t), "") if t else
                     ("set_xlabel", d.x_name, "x_title", "1列目の見出しを X 軸ラベルにする"))
    if s.y_axis.show_label:
        t = s.y_axis.label.strip()
        if t:
            texts.append(("set_ylabel", t, _str(t), ""))
        elif len(d.names) == 1:
            texts.append(("set_ylabel", d.names[0], 'series[0]["name"]',
                          "系列が 1 つなので，その見出しを Y 軸ラベルにする"))
    w("# ----- タイトルと軸ラベル -----")
    for func, text, expr, comment in texts:
        extra = ", fontfamily=jp_font" if _mixes_math_and_japanese(text) else ""
        line = f"ax.{func}({expr}{extra})"
        w(f"{line}  # {comment}" if comment else line)
    w()


def _axis_range(w: _Code, axis: str, a, bottom_zero: bool) -> bool:
    lo_name, hi_name = ("left", "right") if axis == "x" else ("bottom", "top")
    wrote = False
    if a.log:
        w(f'ax.set_{axis}scale("log")  # {axis.upper()} 軸を対数目盛りにする')
        wrote = True
    lo = a.min if a.min is not None else (0.0 if bottom_zero else None)
    args = []
    if lo is not None:
        args.append(f"{lo_name}={_num(lo)}")
    if a.max is not None:
        args.append(f"{hi_name}={_num(a.max)}")
    if args:
        comment = "  # Y 軸を 0 から始める" if bottom_zero and a.min is None else "  # 軸の範囲"
        w(f"ax.set_{axis}lim({', '.join(args)}){comment}")
        wrote = True
    if a.step and not a.log:
        w(f"ax.{axis}axis.set_major_locator(MultipleLocator({_num(a.step)}))  # 目盛りの間隔")
        wrote = True
    return wrote


def _write_legend(w: _Code, s: GraphSettings, d: ParsedData) -> None:
    n_series = len(d.names)
    lg = s.legend
    if not lg.show:
        return
    w("# ----- 凡例 -----")
    if lg.frame:
        frame = f'frameon=True, fancybox=False, edgecolor={_str(s.axis_color)}, framealpha=1'
    else:
        frame = "frameon=False"
    if any(_mixes_math_and_japanese(n) for n in d.names):
        frame += ', prop={"family": jp_font}'
    if lg.loc == "outside bottom":
        w("# グラフの外（下）に横並びで置く")
        w(f'fig.legend(loc="outside lower center", ncols={min(n_series, 4)}, {frame})')
    elif lg.loc == "outside right":
        w("# グラフの外（右）に置く")
        w(f'fig.legend(loc="outside right upper", {frame})')
    else:
        w(f"ax.legend(loc={_str(lg.loc)}, {frame})  # 位置: {LEGEND_NAMES[lg.loc]}")
    w()


def _write_frame(w: _Code, s: GraphSettings) -> None:
    if s.grid != "none":
        w("# ----- 目盛り線 -----")
        axis = "y" if s.grid == "y" else "both"
        note = "横線のみ" if s.grid == "y" else "縦横"
        w(f'ax.grid(axis="{axis}", color="{GRID_COLOR}", linewidth=0.5)  # {note}')
        w("ax.set_axisbelow(True)  # 目盛り線をデータの後ろに描く")
        w()

    is_scatter = s.chart_type in ("scatter", "scatter_line")
    tick_lines = []
    for axis, a in (("x", s.x_axis), ("y", s.y_axis)):
        if _integer_ticks(s, axis):
            tick_lines.append(f"ax.{axis}axis.set_major_locator(MaxNLocator(integer=True))"
                              "  # 整数の位置にだけ目盛りを打つ（同じ数字が並ばないように）")
        if a.tick_decimals is not None and (axis == "y" or is_scatter):
            tick_lines.append(f'ax.{axis}axis.set_major_formatter(FormatStrFormatter("%.{a.tick_decimals}f"))'
                              f"  # {axis.upper()} 軸の数値を小数点以下 {a.tick_decimals} 桁で表示")
    if s.minor_ticks:
        if is_scatter:
            tick_lines.append("ax.minorticks_on()  # 補助目盛り（主目盛りの間の小さい目盛り）")
        else:
            tick_lines.append("ax.yaxis.set_minor_locator(AutoMinorLocator())  # Y 軸に補助目盛り")
    if s.ticks_all_sides:
        tick_lines.append('ax.tick_params(which="both", top=True, right=True)  # 目盛りを上と右にも付ける')
    if tick_lines:
        w("# ----- 目盛り -----")
        for line in tick_lines:
            w(line)
        w()

    w("# ----- 枠線 -----")
    if s.frame == "box":
        w("# 四方を枠で囲む（matplotlib の標準）")
    elif s.frame == "L":
        w('ax.spines[["top", "right"]].set_visible(False)  # 上と右の枠線を消す')
    else:
        w('ax.spines[["top", "right", "left"]].set_visible(False)  # 下の軸線だけ残す')
        w('ax.tick_params(axis="y", length=0)  # Y 軸の目盛りの線も消す')
    if s.axis_color.lower() != "#000000":
        w(f"ax.spines[:].set_color({_str(s.axis_color)})  # 軸線の色")
        w(f"ax.tick_params(color={_str(s.axis_color)})  # 目盛りの色")
    if s.outer_border:
        w("# 図全体を外枠で囲む")
        w(f'fig.patch.set_edgecolor("{OUTER_BORDER_COLOR}")')
        w("fig.patch.set_linewidth(1.0)")
    w()
