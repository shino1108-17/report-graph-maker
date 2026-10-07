"""グラフ設定（JSON）の型と入力チェック．

ブラウザから届くのはこの設定だけで，Python コードは一切受け取らない．
数値以外・データ点数・サイズなどはすべてここでチェックする．
"""
from __future__ import annotations

import math
import unicodedata
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_ROWS = 2000      # データ点数（行数）の上限
MAX_SERIES = 10      # Y 系列の上限
MAX_TEXT = 100       # 見出し・タイトルなどの文字数上限
MAX_CELL = 50        # セル 1 つの文字数上限
MAX_TICKS = 200      # 目盛りの本数の上限（目盛り間隔が小さすぎると固まるのを防ぐ）

ChartType = Literal["scatter", "scatter_line", "line", "bar"]
SCATTER_TYPES = ("scatter", "scatter_line")   # X を数値として扱う種類
CATEGORY_TYPES = ("line", "bar")              # X を項目（等間隔）として扱う種類

# 選べるフォント（UI には，この中で実際にインストールされているものだけを出す）
# "" は日本語フォントに任せる．STIXGeneral（Times に似た書体）と DejaVu は matplotlib に同梱なのでどこでも使える
LATIN_FONTS = ["", "DejaVu Sans", "DejaVu Serif", "STIXGeneral", "Arial", "Helvetica", "Times New Roman"]
JP_FONTS = [
    "IPAexGothic", "Hiragino Sans", "Hiragino Mincho ProN", "Hiragino Maru Gothic ProN",
    "YuGothic", "YuMincho", "BIZ UDGothic", "BIZ UDMincho",
    "Noto Sans CJK JP", "Noto Serif CJK JP", "MS Gothic", "MS Mincho",
]
SERIF_FONTS = {"Times New Roman", "STIXGeneral", "DejaVu Serif", "Hiragino Mincho ProN", "YuMincho", "BIZ UDMincho",
               "Noto Serif CJK JP", "MS Mincho"}

def parse_number(text: str) -> float | None:
    """セルの文字列を数値にする．空欄は None，数値でなければ ValueError．"""
    s = unicodedata.normalize("NFKC", text).strip()  # 全角数字も受け付ける
    s = s.replace("−", "-").replace("ー", "-")
    if s == "":
        return None
    value = float(s)
    if not math.isfinite(value):
        raise ValueError(s)
    return value


# ---------------------------------------------------------------- 各設定

class Data(BaseModel):
    columns: list[str] = Field(min_length=2, max_length=MAX_SERIES + 1)
    rows: list[list[str]] = Field(max_length=MAX_ROWS)

    @field_validator("columns")
    @classmethod
    def _check_columns(cls, v: list[str]) -> list[str]:
        for name in v:
            if len(name) > MAX_TEXT:
                raise ValueError(f"列見出しは {MAX_TEXT} 文字以内にしてください")
        return v

    @field_validator("rows")
    @classmethod
    def _check_rows(cls, v: list[list[str]]) -> list[list[str]]:
        for row in v:
            if len(row) > MAX_SERIES + 1:
                raise ValueError(f"列は {MAX_SERIES + 1} 列までです")
            for cell in row:
                if len(cell) > MAX_CELL:
                    raise ValueError(f"セルの文字が長すぎます（{MAX_CELL} 文字まで）")
        return v


class TitleSettings(BaseModel):
    show: bool = True
    text: str = Field("", max_length=MAX_TEXT)


class AxisSettings(BaseModel):
    show_label: bool = True
    label: str = Field("", max_length=MAX_TEXT)   # 空欄なら列見出しを使う
    min: float | None = Field(None, allow_inf_nan=False)
    max: float | None = Field(None, allow_inf_nan=False)
    step: float | None = Field(None, gt=0, allow_inf_nan=False)
    log: bool = False
    start_zero: bool = False   # Y 軸だけで使う

    @model_validator(mode="after")
    def _check_range(self) -> "AxisSettings":
        if self.min is not None and self.max is not None and self.min >= self.max:
            raise ValueError("軸の最小値は最大値より小さくしてください")
        if self.log and ((self.min is not None and self.min <= 0) or (self.max is not None and self.max <= 0)):
            raise ValueError("対数目盛りの軸の範囲は 0 より大きくしてください")
        return self


class LegendSettings(BaseModel):
    show: bool = True
    loc: Literal["best", "upper right", "upper left", "lower right", "lower left",
                 "outside bottom", "outside right"] = "best"
    frame: bool = True


class SeriesStyle(BaseModel):
    color: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    linestyle: Literal["-", "--", ":", "-.", "none"] = "-"
    line_width: float = Field(1.0, ge=0, le=10)
    marker: Literal["o", "s", "^", "v", "D", "x", "+", "*", "none"] = "o"
    marker_size: float = Field(4, ge=0, le=30)
    marker_fill: bool = True


class DataLabelSettings(BaseModel):
    show: bool = False
    decimals: int = Field(2, ge=0, le=6)


class FontSettings(BaseModel):
    latin: Literal[tuple(LATIN_FONTS)] = ""        # type: ignore[valid-type]
    jp: Literal[tuple(JP_FONTS)] = "IPAexGothic"    # type: ignore[valid-type]
    size: float = Field(7, ge=4, le=30)


class SizeSettings(BaseModel):
    width_mm: float = Field(58, ge=20, le=300)
    height_mm: float = Field(45, ge=20, le=300)


class OutputSettings(BaseModel):
    format: Literal["png", "svg", "pdf"] = "png"
    dpi: Literal[150, 300, 600] = 300
    transparent: bool = False


DEFAULT_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
                  "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]


class GraphSettings(BaseModel):
    data: Data
    chart_type: ChartType = "scatter_line"
    title: TitleSettings = TitleSettings()
    x_axis: AxisSettings = AxisSettings()
    y_axis: AxisSettings = AxisSettings(start_zero=True)
    legend: LegendSettings = LegendSettings()
    grid: Literal["none", "y", "both"] = "none"
    series: list[SeriesStyle] = Field(default_factory=list, max_length=MAX_SERIES)
    data_labels: DataLabelSettings = DataLabelSettings()
    frame: Literal["box", "L", "bottom"] = "box"     # 軸の枠線：四方／左と下／下だけ
    axis_color: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    tick_direction: Literal["in", "out"] = "in"
    outer_border: bool = False                         # 図全体の外枠
    font: FontSettings = FontSettings()
    size: SizeSettings = SizeSettings()
    output: OutputSettings = OutputSettings()

    @model_validator(mode="after")
    def _check_all(self) -> "GraphSettings":
        cols = self.data.columns
        x_numeric = self.chart_type in SCATTER_TYPES
        # 数値チェック（エラーの場所を日本語で示す）．折れ線・棒の X は文字でもよい
        for r, row in enumerate(self.data.rows, start=1):
            for c, cell in enumerate(row[: len(cols)], start=1):
                if c == 1 and not x_numeric:
                    continue
                try:
                    parse_number(cell)
                except ValueError:
                    raise ValueError(f"{r}行目 {c}列目「{cell}」は数値ではありません")

        # 系列のスタイルが足りなければ既定値で補う
        while len(self.series) < len(cols) - 1:
            i = len(self.series)
            self.series.append(SeriesStyle(color=DEFAULT_COLORS[i % len(DEFAULT_COLORS)]))
        self.series = self.series[: len(cols) - 1]

        d = parse_data(self.data, self.chart_type)
        ys = [v for y in d.ys for v in y if v is not None]
        xs = [v for v in d.x if v is not None] if x_numeric else []
        if x_numeric:
            _check_axis(self.x_axis, xs, "X")
        zero = [0.0] if self.y_axis.start_zero and not self.y_axis.log else []  # 対数のときは 0 から始めない
        _check_axis(self.y_axis, ys + zero, "Y")
        return self


def _check_axis(axis: AxisSettings, values: list[float], name: str) -> None:
    if axis.log and any(v <= 0 for v in values):
        raise ValueError(f"{name}軸を対数目盛りにするには，{name} の値をすべて 0 より大きくしてください")
    if axis.step is None or axis.log:
        return
    lo = axis.min if axis.min is not None else min(values, default=0.0)
    hi = axis.max if axis.max is not None else max(values, default=1.0)
    span = abs(hi - lo) * 1.2  # 自動範囲の余白ぶりを少し見込む
    if span / axis.step > MAX_TICKS:
        raise ValueError(f"{name}軸の目盛り間隔が小さすぎます（目盛りが {MAX_TICKS} 本を超えます）")


# ---------------------------------------------------------------- データの変換

class ParsedData(BaseModel):
    """数値に変換済みのデータ（コード生成用）．"""
    x_name: str
    x: list[float | None]      # 散布図用（数値）
    x_labels: list[str]        # 折れ線・棒用（項目名）
    names: list[str]
    ys: list[list[float | None]]


def parse_data(data: Data, chart_type: str) -> ParsedData:
    n_cols = len(data.columns)
    rows = [(row + [""] * n_cols)[:n_cols] for row in data.rows]
    rows = [row for row in rows if any(c.strip() for c in row)]  # 全部空欄の行は無視
    x_numeric = chart_type in SCATTER_TYPES
    x = [parse_number(row[0]) for row in rows] if x_numeric else []
    x_labels = [] if x_numeric else [unicodedata.normalize("NFKC", row[0]).strip() for row in rows]
    ys = [[parse_number(row[c]) for row in rows] for c in range(1, n_cols)]
    names = [name.strip() or f"系列{i}" for i, name in enumerate(data.columns[1:], start=1)]
    return ParsedData(x_name=data.columns[0].strip(), x=x, x_labels=x_labels, names=names, ys=ys)
