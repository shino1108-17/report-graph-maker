"""実験レポート用グラフ作成アプリ（FastAPI）

起動:  uvicorn main:app --reload

処理の中身は api_core.py にあり，ブラウザ版（GitHub Pages）と共通．
"""
from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from api_core import MEDIA_TYPES, ApiError, available_fonts, export_file, japanese_error, render_preview

BASE = Path(__file__).parent
app = FastAPI(title="実験レポート用グラフ作成")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    errors = [japanese_error(e) for e in exc.errors()]
    return JSONResponse(status_code=422, content={"errors": errors})


@app.exception_handler(ApiError)
async def _api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(status_code=exc.status, content=exc.body())


@app.get("/")
def index():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/fonts")
def api_fonts():
    """選べるフォントのうち，この PC に実際に入っているものを返す．"""
    return available_fonts()


@app.post("/api/render")
def api_render(payload: dict = Body(...)):
    """プレビュー画像（PNG）と，それを作ったコードを一緒に返す．"""
    return render_preview(payload)


@app.post("/api/export")
def api_export(payload: dict = Body(...)):
    """ダウンロード用のファイル（PNG / SVG / PDF）を返す．"""
    data, fmt = export_file(payload)
    return Response(
        content=data,
        media_type=MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="graph.{fmt}"'},
    )
