"""テスト:  pytest   （プロジェクトのフォルダで実行）"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import matplotlib.image as mpimg
import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from codegen import generate_code  # noqa: E402
from main import app  # noqa: E402
from schemas import GraphSettings  # noqa: E402

client = TestClient(app)

CHART_TYPES = ["scatter", "scatter_line", "line", "bar"]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def sample(**overrides) -> dict:
    """初期値のサンプルデータ（LED の実験）に設定を上書きした辞書を作る．"""
    settings = {
        "data": {
            "columns": ["電源電圧Vcc [V]", "LEDの電流 [mA]"],
            "rows": [["5.03", "13.7"], ["10.0", "13.1"]],
        },
    }
    settings.update(overrides)
    return settings


MULTI = {
    "columns": ["電圧 [V]", "赤 [mA]", "緑 [mA]", "青 [mA]"],
    "rows": [["1", "1.5", "0.2", ""], ["2", "4.0", "1.1", "0.5"], ["3", "7.2", "3.0", "2.0"], ["", "", "", ""]],
}


# ------------------------------------------------------------ 生成コードを単体で実行

@pytest.mark.parametrize("chart_type", CHART_TYPES)
def test_generated_code_runs_and_saves_png(tmp_path: Path, chart_type: str):
    """生成したコードを python で単体実行すると，指定した mm・dpi の PNG ができる．"""
    settings = GraphSettings(**sample(chart_type=chart_type, size={"width_mm": 58, "height_mm": 45},
                                      output={"format": "png", "dpi": 300, "transparent": False}))
    (tmp_path / "graph.py").write_text(generate_code(settings), encoding="utf-8")

    result = subprocess.run([sys.executable, "graph.py"], cwd=tmp_path, capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stderr
    png = tmp_path / "graph.png"
    assert png.exists()
    assert png.read_bytes()[:8] == PNG_SIGNATURE
    height, width = mpimg.imread(png).shape[:2]
    assert (width, height) == (round(58 / 25.4 * 300), round(45 / 25.4 * 300))  # 実寸どおり


def test_standalone_result_matches_server_image(tmp_path: Path):
    """単体実行で保存した画像と，サーバーが作った画像が同じ（表示コードと実際の処理がずれていない）．"""
    body = sample(chart_type="scatter_line", data=MULTI, data_labels={"show": True, "decimals": 1})
    settings = GraphSettings(**body)
    (tmp_path / "graph.py").write_text(generate_code(settings), encoding="utf-8")
    subprocess.run([sys.executable, "graph.py"], cwd=tmp_path, check=True, capture_output=True, timeout=120)

    res = client.post("/api/export", json=body)
    assert res.status_code == 200
    (tmp_path / "server.png").write_bytes(res.content)

    standalone = mpimg.imread(tmp_path / "graph.png")
    server = mpimg.imread(tmp_path / "server.png")
    assert standalone.shape == server.shape
    assert np.array_equal(standalone, server)


def test_render_returns_the_same_code_as_generator():
    body = sample(chart_type="bar", data=MULTI)
    res = client.post("/api/render", json=body)
    assert res.status_code == 200
    assert res.json()["code"] == generate_code(GraphSettings(**body))


# ------------------------------------------------------------ 各グラフ種類・各設定でエラーが出ない

OPTION_SETS = [
    {},
    {"data_labels": {"show": True, "decimals": 3}},
    {"legend": {"show": True, "loc": "outside bottom", "frame": False}},
    {"legend": {"show": True, "loc": "outside right", "frame": True}},
    {"legend": {"show": False}},
    {"grid": "y", "frame": "bottom", "axis_color": "#bfbfbf", "outer_border": True, "tick_direction": "out"},
    {"grid": "both", "frame": "L"},
    {"y_axis": {"min": -1, "max": 10, "step": 2, "start_zero": False}},
    {"y_axis": {"log": True, "start_zero": True}},
    {"title": {"show": True, "text": "LED の特性 $V_{cc}$"}},
    {"font": {"latin": "DejaVu Sans", "jp": "IPAexGothic", "size": 12}},
    {"size": {"width_mm": 20, "height_mm": 20}},
    {"output": {"format": "png", "dpi": 150, "transparent": True}},
]


@pytest.mark.parametrize("chart_type", CHART_TYPES)
@pytest.mark.parametrize("options", OPTION_SETS, ids=lambda o: ",".join(o) or "default")
def test_every_chart_type_renders(chart_type: str, options: dict):
    res = client.post("/api/render", json=sample(chart_type=chart_type, data=MULTI, **options))
    assert res.status_code == 200, res.json()
    body = res.json()
    assert body["image"]
    assert "def draw_graph" in body["code"]


@pytest.mark.parametrize("chart_type", ["scatter", "scatter_line"])
def test_x_axis_settings_for_scatter(chart_type: str):
    options = {"x_axis": {"min": 0, "max": 4, "step": 0.5}}
    res = client.post("/api/render", json=sample(chart_type=chart_type, data=MULTI, **options))
    assert res.status_code == 200
    assert "MultipleLocator(0.5)" in res.json()["code"]
    res = client.post("/api/render", json=sample(chart_type=chart_type, data=MULTI, x_axis={"log": True}))
    assert res.status_code == 200


def test_category_x_can_be_text():
    """折れ線・棒では X に文字（項目名）を使える．"""
    data = {"columns": ["条件", "電流 [mA]"], "rows": [["赤色", "13.7"], ["緑色", "12.0"]]}
    for chart_type in ["line", "bar"]:
        assert client.post("/api/render", json=sample(chart_type=chart_type, data=data)).status_code == 200
    res = client.post("/api/render", json=sample(chart_type="scatter", data=data))
    assert res.status_code == 422
    assert "数値ではありません" in res.json()["errors"][0]


@pytest.mark.parametrize("fmt, head", [("png", PNG_SIGNATURE), ("pdf", b"%PDF"), ("svg", b"<?xml")])
def test_export_formats(fmt: str, head: bytes):
    res = client.post("/api/export", json=sample(output={"format": fmt, "dpi": 300, "transparent": False}))
    assert res.status_code == 200
    assert res.content.startswith(head)
    assert f"graph.{fmt}" in res.headers["content-disposition"]


def test_fullwidth_numbers_and_blank_cells_are_accepted():
    data = {"columns": ["X", "Y"], "rows": [["１．５", "２"], ["2", ""], ["", ""], ["3", "−1"]]}
    res = client.post("/api/render", json=sample(data=data))
    assert res.status_code == 200
    assert "x = [1.5, 2, 3]" in res.json()["code"]


# ------------------------------------------------------------ 入力チェック（サーバー側）

@pytest.mark.parametrize(
    "body, message",
    [
        (sample(data={"columns": ["X", "Y"], "rows": [["1", "abc"]]}), "1行目 2列目「abc」は数値ではありません"),
        (sample(data={"columns": ["X", "Y"], "rows": [["1", "2"]] * 2001}), "2000"),
        (sample(data={"columns": ["X"] + [f"Y{i}" for i in range(11)], "rows": []}), "11"),
        (sample(size={"width_mm": 1000, "height_mm": 45}), "300 以下"),
        (sample(output={"format": "png", "dpi": 72, "transparent": False}), "150"),
        (sample(y_axis={"min": 5, "max": 1}), "最小値は最大値より小さく"),
        (sample(y_axis={"step": 1e-9, "start_zero": True}), "目盛り間隔が小さすぎます"),
        (sample(series=[{"color": "red; import os"}]), "形式が正しくありません"),
        (sample(chart_type="exec"), "選べる値"),
        (sample(font={"jp": "../../etc/passwd"}), "選べる値"),
    ],
)
def test_invalid_input_is_rejected(body: dict, message: str):
    res = client.post("/api/render", json=body)
    assert res.status_code == 422
    assert any(message in e for e in res.json()["errors"]), res.json()


def test_user_text_cannot_inject_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """タイトルや見出しに Python コードを書いても，ただの文字として扱われる．"""
    monkeypatch.chdir(tmp_path)  # 万一実行されたら tmp_path に pwned ができる
    marker = tmp_path / "pwned"
    evil = "\"\"\"'''\nimport pathlib; pathlib.Path('pwned').touch()\n# \\"
    body = sample(title={"show": True, "text": evil},
                  data={"columns": [evil, evil], "rows": [["1", "2"]]})
    res = client.post("/api/render", json=body)
    assert res.status_code == 200
    assert not marker.exists()
    # 生成コードを単体で実行しても同じ
    (tmp_path / "graph.py").write_text(res.json()["code"], encoding="utf-8")
    subprocess.run([sys.executable, "graph.py"], cwd=tmp_path, check=True, capture_output=True, timeout=120)
    assert not marker.exists()


@pytest.mark.parametrize("legend", [True, False])
def test_math_and_japanese_in_same_text_has_no_missing_glyphs(legend: bool):
    """「電流 $I_F$ [mA]」のように数式と日本語が混ざっても □（豆腐）にならない．"""
    data = {"columns": ["周波数 $f$ [Hz]", "電流 $I_F$ [mA]"], "rows": [["1", "2"], ["10", "3"]]}
    for font in ({"latin": "", "jp": "IPAexGothic"}, {"latin": "DejaVu Sans", "jp": "IPAexGothic"}):
        body = sample(data=data, font=font, legend={"show": legend},
                      title={"show": True, "text": "LEDの特性 $I_F = V/R$"})
        res = client.post("/api/render", json=body)
        assert res.status_code == 200
        assert "fontfamily=jp_font" in res.json()["code"]
        assert not [w for w in res.json()["warnings"] if "glyph" in w.lower()], res.json()["warnings"]


def test_broken_math_text_gives_friendly_error():
    res = client.post("/api/render", json=sample(title={"show": True, "text": "電流 $I_{$"}))  # 閉じていない数式
    assert res.status_code == 400
    assert any("\\$" in e for e in res.json()["errors"])


def test_fonts_api_lists_bundled_font():
    res = client.get("/api/fonts")
    assert res.status_code == 200
    assert "IPAexGothic" in res.json()["jp"]


# ------------------------------------------------------------ 誤差棒・繰り返し測定・近似曲線

STATS = {
    "columns": ["電圧 [V]", "電流 [mA]", "2回目", "3回目", "抵抗 [Ω]", "標準偏差"],
    "roles": ["series", "repeat", "repeat", "series", "error"],
    "rows": [["1", "1.0", "1.2", "0.9", "10", "0.5"], ["2", "2.1", "1.9", "2.2", "12", "0.6"],
             ["3", "2.9", "3.2", "", "13", "0.4"], ["4", "4.2", "3.8", "4.1", "15", "0.8"]],
}


@pytest.mark.parametrize("chart_type", CHART_TYPES)
@pytest.mark.parametrize("error", ["sd", "se"])
def test_repeated_measurements_mean_and_error(tmp_path: Path, chart_type: str, error: str):
    """繰り返し測定の平均と標準偏差（標準誤差）が，生成コードの中で正しく計算される．"""
    body = sample(chart_type=chart_type, data=STATS,
                  series=[{"error": error}, {}, {}, {"error": "column"}, {}])
    res = client.post("/api/render", json=body)
    assert res.status_code == 200, res.json()
    code = res.json()["code"]
    assert '"trials": [' in code and "ax.errorbar(" in code or "ax.bar(" in code

    # 生成コードを実行して，計算結果を numpy で確かめる
    ns: dict = {"__name__": "check"}
    exec(compile(code, "graph.py", "exec"), ns)
    s0 = ns["series"][0]
    trials = np.array([[1.0, 2.1, 2.9, 4.2], [1.2, 1.9, 3.2, 3.8], [0.9, 2.2, np.nan, 4.1]])
    assert np.allclose(s0["y"], np.nanmean(trials, axis=0))
    sd = np.nanstd(trials, axis=0, ddof=1)
    expected = sd if error == "sd" else sd / np.sqrt([3, 3, 2, 3])
    assert np.allclose(s0["yerr"], expected)
    assert ns["series"][1]["yerr"] == [0.5, 0.6, 0.4, 0.8]  # 「誤差」の列の値そのまま
    ns["plt"].close("all")
    # 単体で実行しても動く
    (tmp_path / "graph.py").write_text(code, encoding="utf-8")
    subprocess.run([sys.executable, "-W", "error::SyntaxWarning", "graph.py"], cwd=tmp_path, check=True,
                   capture_output=True, timeout=120)


@pytest.mark.parametrize("error, value", [("fixed", 0.3), ("percent", 10)])
def test_fixed_and_percent_error_bars(error: str, value: float):
    res = client.post("/api/render", json=sample(series=[{"error": error, "error_value": value}]))
    assert res.status_code == 200, res.json()
    assert "ax.errorbar(" in res.json()["code"]


@pytest.mark.parametrize("trend", ["linear", "poly2", "poly3", "exp", "log", "power"])
@pytest.mark.parametrize("legend", [True, False])
def test_trendlines(tmp_path: Path, trend: str, legend: bool):
    data = {"columns": ["X", "Y"], "rows": [[str(x), str(2.0 * x ** 1.5 + 1)] for x in range(1, 8)]}
    body = sample(chart_type="scatter", data=data, legend={"show": legend},
                  series=[{"trend": trend, "trend_equation": True, "trend_r2": True}])
    res = client.post("/api/render", json=body)
    assert res.status_code == 200, res.json()
    code = res.json()["code"]
    assert "def fit_trend" in code
    assert not res.json()["warnings"]
    (tmp_path / "graph.py").write_text(code, encoding="utf-8")
    subprocess.run([sys.executable, "-W", "error::SyntaxWarning", "graph.py"], cwd=tmp_path, check=True,
                   capture_output=True, timeout=120)


def test_linear_trend_is_correct():
    """直線近似の係数と R² が正しい（y = 2x + 1 にぴったり乗るデータ）．"""
    data = {"columns": ["X", "Y"], "rows": [[str(x), str(2 * x + 1)] for x in range(5)]}
    code = generate_code(GraphSettings(**sample(data=data, series=[{"trend": "linear"}])))
    ns: dict = {"__name__": "check"}
    exec(compile(code, "graph.py", "exec"), ns)
    _, _, equation, r2 = ns["fit_trend"]("linear", ns["x"], ns["series"][0]["y"])
    assert equation == "$y = 2x +1$"
    assert r2 == pytest.approx(1.0)


def test_trendline_is_ignored_for_category_charts():
    res = client.post("/api/render", json=sample(chart_type="bar", series=[{"trend": "linear"}]))
    assert res.status_code == 200
    assert "fit_trend" not in res.json()["code"]


def test_tick_options():
    body = sample(minor_ticks=True, ticks_all_sides=True,
                  x_axis={"tick_decimals": 0}, y_axis={"tick_decimals": 2, "start_zero": True})
    code = client.post("/api/render", json=body).json()["code"]
    assert "ax.minorticks_on()" in code
    assert 'top=True, right=True' in code
    assert "MaxNLocator(integer=True)" in code
    assert 'FormatStrFormatter("%.2f")' in code


@pytest.mark.parametrize(
    "body, message",
    [
        (sample(series=[{"error": "column"}]), "誤差棒に使う列がありません"),
        (sample(series=[{"error": "sd"}]), "繰り返し測定の列が必要です"),
        (sample(data={**STATS, "roles": ["error"]}), "最初の Y の列"),
        (sample(data={"columns": ["X", "Y", "e1", "e2"], "roles": ["series", "error", "error"],
                      "rows": [["1", "2", "3", "4"]]}), "誤差」の列は1つまで"),
        (sample(chart_type="scatter", series=[{"trend": "poly3"}]), "4 点以上"),
        (sample(chart_type="scatter", data={"columns": ["X", "Y"], "rows": [["1", "-1"], ["2", "3"]]},
                series=[{"trend": "exp"}]), "Y がすべて 0 より大きい"),
        (sample(series=[{"error": "fixed", "error_value": -1}]), "0 以上"),
    ],
)
def test_invalid_statistics_settings(body: dict, message: str):
    res = client.post("/api/render", json=body)
    assert res.status_code == 422
    assert any(message in e for e in res.json()["errors"]), res.json()
