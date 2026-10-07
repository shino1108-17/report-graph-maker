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
    need_locator = (is_scatter and s.x_axis.step and not s.x_axis.log) or (s.y_axis.step and not s.y_axis.log)

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
    if need_locator:
        w("from matplotlib.ticker import MultipleLocator  # 目盛りを一定の間隔で打つための道具")
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
    for i, (name, ys, st) in enumerate(zip(d.names, d.ys, s.series)):
        first = i == 0  # 説明コメントは最初の系列にだけ付ける

        def item(key: str, value: str, comment: str) -> None:
            pad = f'        "{key}": {value},'
            w(_pad(pad, 40) + f" # {comment}" if first and comment else pad)

        w("    {")
        item("name", _str(name), "凡例に表示される名前")
        item("y", _num_list(ys), "")
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
        w("    },")
    w("]")
    w()

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
    _write_fonts(w, s)
    w()
    w(f"# ----- 図の大きさ: 幅 {_mm(s.size.width_mm)} mm × 高さ {_mm(s.size.height_mm)} mm -----")
    w('# layout="constrained" は，文字がはみ出さないように余白を自動で調整する設定')
    w(f"fig, ax = plt.subplots(figsize=({_mm(s.size.width_mm)} * MM, {_mm(s.size.height_mm)} * MM), "
      'layout="constrained")')
    w()
    _write_plot(w, s, n_points)
    _write_axes(w, s, d, is_scatter)
    _write_legend(w, s, len(d.names))
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


def _series_names(s: GraphSettings) -> list[str]:
    return [name.strip() or f"系列{i}" for i, name in enumerate(s.data.columns[1:], start=1)]


def _needs_jp_font_variable(s: GraphSettings) -> bool:
    candidates = [s.data.columns[0].strip(), s.x_axis.label, s.y_axis.label]
    if s.title.show:
        candidates.append(s.title.text)
    if s.legend.show:
        candidates += _series_names(s)
    elif len(s.data.columns) == 2:
        candidates += _series_names(s)  # Y 軸ラベルに使われる
    return any(_mixes_math_and_japanese(t.strip()) for t in candidates)


def _write_fonts(w: _Code, s: GraphSettings) -> None:
    f = s.font
    families = [f.latin, f.jp] if f.latin else [f.jp]
    serif = (f.latin in SERIF_FONTS) if f.latin else (f.jp in SERIF_FONTS)
    w("# ----- フォントと文字の大きさ -----")
    if f.latin:
        w(f"# 英数字は {f.latin}，日本語は {f.jp} で表示する（左のフォントから順に文字を探す）")
    w(f'plt.rcParams["font.family"] = {_str_list(families)}')
    w(f'plt.rcParams["mathtext.fontset"] = {_str("stix" if serif else "dejavusans")}  '
      "# 数式（$...$）の書体を本文に合わせる")
    if _needs_jp_font_variable(s):
        w("# 数式（$...$）と日本語が混ざった文字は，フォントの併用が効かず日本語が □ になるので，")
        w("# その文字だけ日本語フォントで書く（数式の部分は上の数式用の書体になる）")
        w(f"jp_font = {_str(f.jp)}")
    w(f'plt.rcParams["font.size"] = {_num(f.size)}  # 文字の大きさ [pt]')
    w('plt.rcParams["pdf.fonttype"] = 42  # PDF にフォントを埋め込む（文字化け防止）')
    d = s.tick_direction
    w(f'plt.rcParams["xtick.direction"] = {_str(d)}  # 目盛りの向き（"in" 内側 / "out" 外側）')
    w(f'plt.rcParams["ytick.direction"] = {_str(d)}')


def _write_plot(w: _Code, s: GraphSettings, n_points: int) -> None:
    ct = s.chart_type
    labels = s.data_labels
    fmt = f"{{:.{labels.decimals}f}}"
    w(f"# ----- データを描く（{CHART_NAMES[ct]}） -----")

    if ct in ("line", "bar"):
        w("positions = np.arange(len(x_labels))  # 項目を 0, 1, 2, ... の位置に等間隔で並べる")

    if ct == "scatter":
        w("for s in series:")
        w("    ax.plot(")
        w('        x, s["y"],')
        w('        linestyle="none",  # 線は引かない（点のみ）')
        w('        marker=s["marker"], markersize=s["markersize"],')
        w('        color=s["color"], markerfacecolor=s["markerfacecolor"],')
        w('        label=s["name"],')
        w("    )")
    elif ct in ("scatter_line", "line"):
        xs = "x" if ct == "scatter_line" else "positions"
        w("for s in series:")
        w("    ax.plot(")
        w(f'        {xs}, s["y"],')
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


def _write_axes(w: _Code, s: GraphSettings, d: ParsedData, is_scatter: bool) -> None:
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


def _write_legend(w: _Code, s: GraphSettings, n_series: int) -> None:
    lg = s.legend
    if not lg.show:
        return
    w("# ----- 凡例 -----")
    if lg.frame:
        frame = f'frameon=True, fancybox=False, edgecolor={_str(s.axis_color)}, framealpha=1'
    else:
        frame = "frameon=False"
    if any(_mixes_math_and_japanese(n) for n in _series_names(s)):
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
