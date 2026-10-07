// ブラウザ版（GitHub Pages）で使う「Python 係」．
// Pyodide（ブラウザの中で動く Python）に matplotlib を読み込み，
// サーバー版と同じ api_core.py を実行する．
// 画面が固まらないように，Web Worker（裏側の別スレッド）で動かす．
// （モジュール形式の Worker．importScripts を使えない環境でも読み込めるように import を使う）
import { loadPyodide } from "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/pyodide.mjs";

const INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";
const PY_FILES = ["schemas.py", "codegen.py", "renderer.py", "api_core.py"];

function progress(text) {
  postMessage({ type: "progress", text });
}

async function setup() {
  progress("Python を読み込んでいます（初回は少し時間がかかります）");
  const pyodide = await loadPyodide({ indexURL: INDEX_URL });

  progress("matplotlib を読み込んでいます");
  await pyodide.loadPackage(["numpy", "matplotlib", "pydantic", "micropip"]);

  progress("日本語フォントを読み込んでいます");
  await pyodide.pyimport("micropip").install("matplotlib-fontja");

  progress("アプリを準備しています");
  pyodide.FS.mkdirTree("/app");
  for (const name of PY_FILES) {
    const res = await fetch(new URL(`py/${name}`, self.location.href), { cache: "no-cache" });
    if (!res.ok) throw new Error(`${name} を読み込めませんでした（${res.status}）`);
    pyodide.FS.writeFile(`/app/${name}`, await res.text());
  }
  pyodide.runPython(`
import sys
sys.path.insert(0, "/app")
import matplotlib
matplotlib.use("Agg")
import api_core
`);
  return pyodide.pyimport("api_core");
}

const ready = setup();
ready.then(
  () => postMessage({ type: "ready" }),
  (err) => postMessage({ type: "failed", text: String(err && err.message ? err.message : err) }),
);

// 画面から {id, kind, payload} が届いたら，api_core.handle_json を呼んで結果を返す
self.onmessage = async (event) => {
  const { id, kind, payload } = event.data;
  try {
    const api = await ready;
    const out = api.handle_json(kind, JSON.stringify(payload ?? null));
    postMessage({ type: "result", id, result: JSON.parse(out) });
  } catch (err) {
    const text = String(err && err.message ? err.message : err);
    postMessage({ type: "result", id, result: { status: 500, body: { errors: [`Python の準備に失敗しました: ${text}`] } } });
  }
};
