// 実験レポート用グラフ作成 — 画面の動き（素の JavaScript．ビルド不要）
"use strict";

const $ = (id) => document.getElementById(id);
const STORAGE_KEY = "graph-app-v1";
const UI_KEY = "graph-app-ui";
const MAX_COLS = 11;   // X ＋ Y 10 列
const MAX_ROWS = 2000;

// ============================================================
//  1. 状態（データ表と設定）
// ============================================================
const SAMPLE = {
  columns: ["電源電圧Vcc [V]", "LEDの電流 [mA]"],
  rows: [["5.03", "13.7"], ["10.0", "13.1"]],
};

const table = {
  columns: [...SAMPLE.columns],
  rows: SAMPLE.rows.map((r) => [...r]),
  roles: ["series"],       // 2 列目以降の役割: "series"（系列）/ "error"（±誤差）/ "repeat"（繰り返し測定）
  current: { r: 0, c: 0 }, // 選択中のセル（r = -1 は見出し行）
};

// 設定（サーバーの GraphSettings と同じ形．data 以外）
function defaultSettings() {
  return {
    chart_type: "scatter_line",
    title: { show: false, text: "" },
    x_axis: { show_label: true, label: "", min: null, max: null, step: null, tick_decimals: null, log: false, start_zero: false },
    y_axis: { show_label: true, label: "", min: null, max: null, step: null, tick_decimals: null, log: false, start_zero: true },
    legend: { show: true, loc: "best", frame: true },
    grid: "none",
    data_labels: { show: false, decimals: 2 },
    frame: "box",
    axis_color: "#000000",
    tick_direction: "in",
    outer_border: false,
    minor_ticks: false,
    ticks_all_sides: false,
    error_capsize: 3,
    font: { latin: "", jp: "IPAexGothic", size: 7 },
    size: { width_mm: 58, height_mm: 45 },
    output: { format: "png", dpi: 300, transparent: false },
    series: [],
    preset: "report",
  };
}
// 系列の「見た目以外」の設定（誤差棒・近似曲線）の初期値
const SERIES_EXTRA = { error: "none", error_value: 0, trend: "none", trend_equation: true, trend_r2: true };

let S = defaultSettings();
let fonts = { latin: [""], jp: ["IPAexGothic"] }; // 使えるフォント（起動時に取得）

// ============================================================
//  2. プリセット
// ============================================================
const EXCEL_COLORS = ["#4472c4", "#ed7d31", "#a5a5a5", "#ffc000", "#5b9bd5", "#70ad47", "#264478", "#9e480e", "#636363", "#997300"];
const TAB_COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"];
const BW_COLORS = ["#000000", "#808080", "#b0b0b0", "#404040"];
const BW_MARKERS = ["o", "s", "^", "D", "v"];
const BW_LINES = ["-", "--", ":", "-."];

function firstAvailable(list, preferred) {
  return preferred.find((f) => list.includes(f)) ?? list[0];
}

// i 番目の系列の見た目（プリセットごと）
function seriesStyleFor(preset, i) {
  if (preset === "report") {
    return {
      color: BW_COLORS[i % BW_COLORS.length], linestyle: BW_LINES[i % BW_LINES.length], line_width: 0.8,
      marker: BW_MARKERS[i % BW_MARKERS.length], marker_size: 3.5, marker_fill: i % 2 === 0,
    };
  }
  if (preset === "excel") {
    return { color: EXCEL_COLORS[i % 10], linestyle: "-", line_width: 2.25, marker: "o", marker_size: 5, marker_fill: true };
  }
  return { color: TAB_COLORS[i % 10], linestyle: "-", line_width: 1.2, marker: "o", marker_size: 4, marker_fill: true };
}

const PRESETS = {
  report: () => ({
    // 系列が 1 つなら凡例は不要（軸ラベルで分かる）
    title: { show: false }, legend: { show: seriesGroups().length > 1, loc: "best", frame: true }, grid: "none", frame: "box",
    axis_color: "#000000", tick_direction: "in", outer_border: false, minor_ticks: false, ticks_all_sides: true,
    font: {
      latin: firstAvailable(fonts.latin, ["Times New Roman", "STIXGeneral", ""]),
      jp: firstAvailable(fonts.jp, ["Hiragino Mincho ProN", "YuMincho", "BIZ UDMincho", "MS Mincho", "IPAexGothic"]),
      size: 7,
    },
    size: { width_mm: 58, height_mm: 45 },
  }),
  excel: () => ({
    title: { show: true }, legend: { show: true, loc: "outside bottom", frame: false }, grid: "y", frame: "bottom",
    axis_color: "#bfbfbf", tick_direction: "out", outer_border: true, minor_ticks: false, ticks_all_sides: false,
    font: { latin: "", jp: firstAvailable(fonts.jp, ["YuGothic", "Hiragino Sans", "IPAexGothic"]), size: 9 },
    size: { width_mm: 127, height_mm: 76 },
  }),
  simple: () => ({
    legend: { show: true, loc: "best", frame: false }, grid: "none", frame: "L",
    axis_color: "#000000", tick_direction: "out", outer_border: false, minor_ticks: false, ticks_all_sides: false,
    font: { latin: "", jp: firstAvailable(fonts.jp, ["Hiragino Sans", "IPAexGothic"]), size: 9 },
    size: { width_mm: 100, height_mm: 75 },
  }),
};

function applyPreset(name) {
  deepMerge(S, PRESETS[name]());
  S.preset = name;
  restyle();
  stateToUI();
  scheduleUpdate(0);
}

// 系列の見た目を，今のプリセットで「何番目の系列か」に合わせて付け直す（誤差棒・近似曲線の設定は残す）
function restyle() {
  syncSeries();
  seriesGroups().forEach((g, gi) => {
    S.series[g.col - 1] = { ...S.series[g.col - 1], ...seriesStyleFor(S.preset, gi) };
  });
}

function deepMerge(target, src) {
  for (const [k, v] of Object.entries(src)) {
    if (v && typeof v === "object" && !Array.isArray(v) && target[k]) deepMerge(target[k], v);
    else target[k] = v;
  }
}

// 系列スタイル・列の役割の数を，表の Y 列の数に合わせる
function syncSeries() {
  const n = table.columns.length - 1;
  while (S.series.length < n) S.series.push(seriesStyleFor(S.preset, S.series.length));
  S.series.length = n;
  S.series = S.series.map((st) => ({ ...SERIES_EXTRA, ...st }));
  while (table.roles.length < n) table.roles.push("series");
  table.roles.length = n;
  if (n > 0) table.roles[0] = "series"; // 最初の Y 列は必ず系列
}

// 系列のまとまり: 「系列」の列と，その右に続く「誤差」「繰り返し」の列
function seriesGroups() {
  const groups = [];
  table.roles.forEach((role, i) => {
    const c = i + 1;
    if (role === "series" || groups.length === 0) {
      groups.push({ col: c, name: table.columns[c] || `系列${groups.length + 1}`, repeats: [], errorCol: null });
    } else if (role === "repeat") {
      groups[groups.length - 1].repeats.push(c);
    } else {
      groups[groups.length - 1].errorCol = c;
    }
  });
  return groups;
}

// 使えなくなった誤差棒の設定を直す．autoSelect なら，使えるようになった誤差棒を自動で選ぶ
// （自動で選ぶのは，列の役割を変えた・貼り付けた・CSV を読んだときだけ）
function fixSeriesErrors(autoSelect = false) {
  for (const g of seriesGroups()) {
    const st = S.series[g.col - 1];
    if (!st) continue;
    if (st.error === "column" && g.errorCol === null) st.error = "none";
    if ((st.error === "sd" || st.error === "se") && g.repeats.length === 0) st.error = "none";
    if (!autoSelect) continue;
    if (st.error === "none" && g.errorCol !== null) st.error = "column";
    else if (st.error === "none" && g.repeats.length > 0) st.error = "sd";
  }
}

// 見出しの名前から役割を推測する（CSV・貼り付けのとき）
function guessRole(name, index) {
  if (index === 0) return "series";
  if (/標準偏差|偏差|誤差|不確か|SD\b|σ|std|err/i.test(name)) return "error";
  if (/(^|[^0-9])([2-9]|1[0-9])\s*回目|試行\s*[2-9]|trial\s*[2-9]/i.test(name)) return "repeat";
  return "series";
}

// ============================================================
//  3. データ表（Excel 風の入力欄）
// ============================================================
function isNumberLike(text) {
  const s = String(text).normalize("NFKC").trim().replace(/[−ー]/g, "-");
  return s === "" || isFinite(Number(s));
}

function xIsCategory() {
  return S.chart_type === "line" || S.chart_type === "bar";
}

function cellIsValid(r, c, v) {
  return (c === 0 && xIsCategory()) || isNumberLike(v);
}

const ROLE_OPTIONS = [["series", "系列"], ["error", "± 誤差"], ["repeat", "繰り返し"]];

function columnCaption(c, groups) {
  if (c === 0) return "X";
  const gi = groups.findIndex((g) => g.col === c || g.errorCol === c || g.repeats.includes(c));
  const g = groups[gi];
  if (g.col === c) return `Y${gi + 1}`;
  if (g.errorCol === c) return `Y${gi + 1} の誤差`;
  return `Y${gi + 1} の ${g.repeats.indexOf(c) + 2} 回目`;
}

function renderGrid() {
  const nCols = table.columns.length;
  const groups = seriesGroups();
  let html = "<thead><tr><th class='rownum'></th>";
  table.columns.forEach((name, c) => {
    const role = c === 0 ? "x" : table.roles[c - 1];
    let roleSelect = "";
    if (c > 0) {
      const opts = ROLE_OPTIONS.map(([v, label]) => `<option value="${v}"${v === role ? " selected" : ""}>${label}</option>`).join("");
      roleSelect = `<select class="role" data-c="${c}" aria-label="${c + 1}列目の役割" ${c === 1 ? "disabled title='最初の Y の列は系列です'" : ""}>${opts}</select>`;
    }
    html += `<th class="role-${role}"><span class="colname">${columnCaption(c, groups)}</span>`
      + `<input data-r="-1" data-c="${c}" value="${escapeHtml(name)}" maxlength="100" aria-label="${c + 1}列目の見出し">${roleSelect}</th>`;
  });
  html += "</tr></thead><tbody>";
  table.rows.forEach((row, r) => {
    html += `<tr data-row="${r}"><th class="rownum">${r + 1}</th>`;
    for (let c = 0; c < nCols; c++) {
      const v = row[c] ?? "";
      const bad = cellIsValid(r, c, v) ? "" : "invalid";
      const role = c === 0 ? "x" : table.roles[c - 1];
      html += `<td class="role-${role}"><input class="${bad}" data-r="${r}" data-c="${c}" value="${escapeHtml(v)}" maxlength="50"></td>`;
    }
    html += "</tr>";
  });
  $("grid").innerHTML = html + "</tbody>";
  markCurrentRow();
}

function cellInput(r, c) {
  return $("grid").querySelector(`input[data-r="${r}"][data-c="${c}"]`);
}

function focusCell(r, c) {
  const el = cellInput(r, c);
  if (el) { el.focus(); el.select(); }
}

function markCurrentRow() {
  $("grid").querySelectorAll("tr.current").forEach((tr) => tr.classList.remove("current"));
  $("grid").querySelector(`tr[data-row="${table.current.r}"]`)?.classList.add("current");
}

function setCell(r, c, value) {
  if (r < 0) table.columns[c] = value;
  else table.rows[r][c] = value;
}

$("grid").addEventListener("input", (e) => {
  const el = e.target;
  if (el.matches("select.role")) return;
  const r = Number(el.dataset.r), c = Number(el.dataset.c);
  setCell(r, c, el.value);
  if (r >= 0) el.classList.toggle("invalid", !cellIsValid(r, c, el.value));
  if (r < 0) renderSeriesList(); // 見出しが変わったら系列パネルの名前も更新
  onDataChanged();
});

// 列の役割を変える
$("grid").addEventListener("change", (e) => {
  const el = e.target;
  if (!el.matches("select.role")) return;
  table.roles[Number(el.dataset.c) - 1] = el.value;
  fixSeriesErrors(true);
  renderAllData();
});

$("grid").addEventListener("focusin", (e) => {
  const el = e.target;
  if (el.dataset.r === undefined) return;
  table.current = { r: Number(el.dataset.r), c: Number(el.dataset.c) };
  markCurrentRow();
});

// Enter / ↑ / ↓ で上下のセルへ移動（最後の行で Enter を押すと行を追加）
$("grid").addEventListener("keydown", (e) => {
  const el = e.target;
  if (el.dataset.r === undefined || el.tagName !== "INPUT" || e.isComposing) return;
  const r = Number(el.dataset.r), c = Number(el.dataset.c);
  let next = null;
  if (e.key === "Enter") next = e.shiftKey ? r - 1 : r + 1;
  else if (e.key === "ArrowDown") next = r + 1;
  else if (e.key === "ArrowUp") next = r - 1;
  if (next === null) return;
  e.preventDefault();
  if (next >= table.rows.length && e.key === "Enter" && table.rows.length < MAX_ROWS) {
    table.rows.push(new Array(table.columns.length).fill(""));
    renderGrid();
    onDataChanged();
  }
  if (next >= -1 && next < table.rows.length) focusCell(next, c);
});

// Excel からのコピー（タブ区切り・改行区切り）を貼り付け
$("grid").addEventListener("paste", (e) => {
  const el = e.target;
  if (el.dataset.r === undefined || el.tagName !== "INPUT") return;
  const text = (e.clipboardData || window.clipboardData).getData("text");
  if (!/[\t\n]/.test(text.replace(/[\r\n]+$/, ""))) return; // 値 1 つだけなら普通に貼り付け
  e.preventDefault();
  const lines = text.replace(/\r\n?/g, "\n").replace(/\n+$/, "").split("\n").map((l) => l.split("\t"));
  pasteBlock(Number(el.dataset.r), Number(el.dataset.c), lines);
});

function pasteBlock(r0, c0, lines) {
  const width = Math.max(...lines.map((l) => l.length));
  if (c0 + width > MAX_COLS) showMessages([`列は ${MAX_COLS} 列（Y 10 列）までなので，はみ出した分は捨てました`], "warn");
  const oldCols = table.columns.length;
  while (table.columns.length < Math.min(c0 + width, MAX_COLS)) addColumnRaw();
  // 見出し行（r0 = -1）から貼ると，1 行目は見出しになる
  const needRows = Math.min(r0 + lines.length, MAX_ROWS);
  while (table.rows.length < needRows) table.rows.push(new Array(table.columns.length).fill(""));
  lines.forEach((cells, i) => {
    if (r0 + i >= MAX_ROWS) return;
    cells.forEach((v, j) => { if (c0 + j < MAX_COLS) setCell(r0 + i, c0 + j, v.trim()); });
  });
  syncSeries();
  if (r0 < 0) { // 見出しごと貼ったときは，見出しから列の役割を推測する
    for (let c = Math.max(1, c0); c < table.columns.length; c++) {
      if (c >= oldCols || c < c0 + width) table.roles[c - 1] = guessRole(table.columns[c], c - 1);
    }
    fixSeriesErrors(true);
    restyle();
  }
  renderAllData();
}

function insertRow(at) {
  if (table.rows.length >= MAX_ROWS) return showMessages([`データは ${MAX_ROWS} 行までです`], "error");
  table.rows.splice(at, 0, new Array(table.columns.length).fill(""));
  table.current.r = at;
  renderAllData();
  focusCell(at, Math.max(0, table.current.c));
}

function addRow() {
  insertRow(table.current.r >= 0 ? table.current.r + 1 : table.rows.length);
}

function deleteRow(r = null) {
  if (table.rows.length <= 1) return;
  if (r === null) r = table.current.r >= 0 && table.current.r < table.rows.length ? table.current.r : table.rows.length - 1;
  table.rows.splice(r, 1);
  table.current.r = Math.min(r, table.rows.length - 1);
  renderAllData();
  focusCell(table.current.r, Math.max(0, table.current.c));
}

function addColumnRaw() {
  table.columns.push(`系列${table.columns.length}`);
  table.rows.forEach((row) => row.push(""));
}

function insertColumn(at) {
  if (table.columns.length >= MAX_COLS) return showMessages(["Y の列は 10 列までです"], "error");
  at = Math.max(1, Math.min(at, table.columns.length));
  table.columns.splice(at, 0, `系列${table.columns.length}`);
  table.rows.forEach((row) => row.splice(at, 0, ""));
  table.roles.splice(at - 1, 0, "series");
  S.series.splice(at - 1, 0, seriesStyleFor(S.preset, at - 1));
  syncSeries();
  fixSeriesErrors();
  renderAllData();
}

function addColumn() {
  insertColumn(table.current.c >= 0 ? table.current.c + 1 : table.columns.length);
}

function deleteColumn(c = null) {
  if (table.columns.length <= 2) return showMessages(["X と Y の 2 列は必要です"], "warn");
  if (c === null) c = table.current.c >= 1 ? table.current.c : table.columns.length - 1;
  if (c < 1) return showMessages(["X の列は削除できません"], "warn");
  table.columns.splice(c, 1);
  table.rows.forEach((row) => row.splice(c, 1));
  table.roles.splice(c - 1, 1);
  S.series.splice(c - 1, 1);
  table.current.c = Math.min(c, table.columns.length - 1);
  syncSeries();
  fixSeriesErrors();
  renderAllData();
}

function clearData() {
  if (!confirm("表の値をすべて消します．よろしいですか？（見出しは残ります）")) return;
  table.rows = Array.from({ length: 5 }, () => new Array(table.columns.length).fill(""));
  renderAllData();
}

function renderAllData() {
  renderGrid();
  renderSeriesList();
  onDataChanged();
}

// ----- 右クリックメニュー（行・列の挿入と削除） -----
let ctxCell = null;
$("grid").addEventListener("contextmenu", (e) => {
  const el = e.target.closest("[data-r]");
  if (!el || el.tagName !== "INPUT") return;
  e.preventDefault();
  ctxCell = { r: Number(el.dataset.r), c: Number(el.dataset.c) };
  table.current = { ...ctxCell };
  markCurrentRow();
  const menu = $("ctx-menu");
  menu.querySelectorAll("[data-act^='row']").forEach((b) => (b.disabled = ctxCell.r < 0 && b.dataset.act !== "row-below"));
  menu.querySelector("[data-act='row-delete']").disabled = ctxCell.r < 0 || table.rows.length <= 1;
  menu.querySelector("[data-act='col-delete']").disabled = ctxCell.c < 1 || table.columns.length <= 2;
  menu.querySelector("[data-act='col-right']").disabled = table.columns.length >= MAX_COLS;
  openMenu(menu, null);
  const w = menu.offsetWidth, h = menu.offsetHeight;
  menu.style.left = `${Math.min(e.clientX, innerWidth - w - 8)}px`;
  menu.style.top = `${Math.min(e.clientY, innerHeight - h - 8)}px`;
});

$("ctx-menu").addEventListener("click", (e) => {
  const act = e.target.dataset.act;
  if (!act || !ctxCell) return;
  closeMenus();
  const { r, c } = ctxCell;
  if (act === "row-above") insertRow(Math.max(0, r));
  else if (act === "row-below") insertRow(r + 1);
  else if (act === "row-delete") deleteRow(r);
  else if (act === "col-right") insertColumn(c + 1);
  else if (act === "col-delete") deleteColumn(c);
});

// ----- CSV の読み込み（UTF-8 と Shift_JIS に対応） -----
$("csv-file").addEventListener("change", async (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (!file) return;
  if (file.size > 2 * 1024 * 1024) return showMessages(["ファイルが大きすぎます（2MB まで）"], "error");
  const buf = await file.arrayBuffer();
  let text;
  try {
    text = new TextDecoder("utf-8", { fatal: true }).decode(buf);
  } catch {
    text = new TextDecoder("shift_jis").decode(buf); // Excel の「CSV（コンマ区切り）」は Shift_JIS のことが多い
  }
  loadDelimitedText(text.replace(/^﻿/, ""), file.name);
});

function parseCSV(text, delim) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quoted) {
      if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === delim) { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

function loadDelimitedText(text, name) {
  const firstLine = text.split(/\r?\n/)[0] || "";
  const delim = firstLine.includes("\t") ? "\t" : firstLine.includes(",") ? "," : ";";
  const rows = parseCSV(text, delim).map((r) => r.map((c) => c.trim()));
  if (rows.length === 0) return showMessages(["ファイルにデータがありません"], "error");
  const width = Math.min(MAX_COLS, Math.max(2, ...rows.map((r) => r.length)));
  // 1 行目に数値でないセルがあれば，見出し行とみなす
  const hasHeader = rows[0].slice(1).some((c) => !isNumberLike(c)) || !isNumberLike(rows[0][0] ?? "");
  const header = hasHeader ? rows.shift() : [];
  table.columns = Array.from({ length: width }, (_, c) => header[c] || (c === 0 ? "X" : `系列${c}`));
  table.rows = rows.slice(0, MAX_ROWS).map((r) => Array.from({ length: width }, (_, c) => r[c] ?? ""));
  if (table.rows.length === 0) table.rows.push(new Array(width).fill(""));
  table.roles = table.columns.slice(1).map((n, i) => guessRole(n, i));
  table.current = { r: 0, c: 0 };
  syncSeries();
  fixSeriesErrors(true);
  restyle();
  renderAllData();
  const notes = [`${name} を読み込みました（${table.rows.length} 行 × ${width} 列）`];
  if (rows.length > MAX_ROWS) notes.push(`${MAX_ROWS} 行を超えた分は読み込んでいません`);
  showMessages(notes, "info");
}

// ============================================================
//  4. 設定パネル ⇔ 設定オブジェクト S（data-bind 属性でつなぐ）
// ============================================================
function getPath(obj, path) { return path.split(".").reduce((o, k) => o[k], obj); }
function setPath(obj, path, v) {
  const keys = path.split(".");
  const last = keys.pop();
  keys.reduce((o, k) => o[k], obj)[last] = v;
}

// 文字列 → 設定の値（data-kind で種類を決める）
function parseValue(raw, kind) {
  if (kind === "bool") return raw === true || raw === "true";
  if (kind === "num") return raw === "" ? null : Number(raw);
  if (kind === "optnum") return String(raw).trim() === "" ? null : Number(raw);
  if (kind === "int") return raw === "" ? null : parseInt(raw, 10);
  if (kind === "optint") return raw === "" ? null : parseInt(raw, 10);
  return raw;
}

function boundControls() {
  return document.querySelectorAll("[data-bind]");
}

function stateToUI() {
  for (const el of boundControls()) {
    const v = getPath(S, el.dataset.bind);
    if (el.tagName === "DIV") { // 切り替えボタンの組
      el.querySelectorAll("button[data-value]").forEach((b) => b.classList.toggle("active", b.dataset.value === String(v)));
    } else if (el.type === "checkbox") {
      el.checked = !!v;
    } else {
      el.value = v ?? "";
    }
  }
  renderSeriesList();
  updateEnabled();
}

function onControlChange(el) {
  const kind = el.dataset.kind || (el.type === "checkbox" ? "bool" : "text");
  const raw = el.type === "checkbox" ? el.checked : el.value;
  setPath(S, el.dataset.bind, parseValue(raw, kind));
  afterSettingChange(el.dataset.bind);
}

function afterSettingChange(path) {
  if (path === "chart_type") {
    renderGrid();        // 折れ線・棒では X に文字を使えるので，赤い表示を付け直す
    renderSeriesList();  // 線・マーカー・近似曲線の使える／使えないが変わる
  }
  updateEnabled();
  scheduleUpdate(path === "chart_type" ? 0 : 400);
}

// 今の設定では使えない項目を薄くする
function updateEnabled() {
  const setOff = (el, off) => {
    if (!el) return;
    el.classList.toggle("is-off", off);
    el.querySelectorAll?.("input, select, button").forEach((c) => (c.disabled = off));
    if (el.matches("input, select")) el.disabled = off;
  };
  const xNum = !xIsCategory();
  document.querySelectorAll(".x-num").forEach((el) => setOff(el, !xNum));
  if (xNum) $("x-step").disabled = S.x_axis.log;
  $("y-step").disabled = S.y_axis.log;
  setOff($("y-zero").closest("label"), S.y_axis.log);
  setOff($("title-text"), !S.title.show);
  setOff(document.querySelector(".legend-opts"), !S.legend.show);
  setOff(document.querySelector(".labels-opts"), !S.data_labels.show);
  setOff($("x-label"), !S.x_axis.show_label);
  setOff($("y-label"), !S.y_axis.show_label);
  $("x-cat-note").textContent = xNum ? "" : "折れ線・棒グラフでは X は項目名なので，範囲や目盛りの設定は使いません．";
  $("chart-note").textContent = {
    scatter: "X を数値として扱い，点だけを打ちます．",
    scatter_line: "X を数値として扱い，点を線で結びます．実験データの基本です．",
    line: "X を「項目」として等間隔に並べます（Excel の折れ線と同じ）．X に文字も使えます．",
    bar: "X を「項目」として等間隔に並べます．X に文字も使えます．",
  }[S.chart_type];
  setOff($("dpi-field"), S.output.format !== "png");
  $("save-note").textContent = S.output.format === "png"
    ? "Word に貼るなら 300 dpi 以上がおすすめです．"
    : "SVG・PDF は拡大しても荒れません（解像度の設定は使いません）．";
  $("save-main").textContent = `${S.output.format.toUpperCase()} を保存`;
  updateLabelHints();
  updatePreviewInfo();
}

// 軸ラベルの単位の書き方をそっと案内する
function updateLabelHints() {
  const hint = (id, effective, show) => {
    const el = $(id);
    if (!show || !effective) { el.textContent = ""; el.classList.remove("warn"); return; }
    const ok = /\[[^\]]+\]/.test(effective);
    el.textContent = ok ? `表示: ${effective}` : `表示: ${effective} — 単位は「電圧 [V]」のように [ ] で書くのがおすすめです`;
    el.classList.toggle("warn", !ok);
  };
  const groups = seriesGroups();
  const xAuto = table.columns[0] || "";
  const yAuto = groups.length === 1 ? groups[0].name : "";
  hint("x-label-hint", S.x_axis.label.trim() || xAuto, S.x_axis.show_label);
  hint("y-label-hint", S.y_axis.label.trim() || yAuto, S.y_axis.show_label);
}

function updatePreviewInfo() {
  const { width_mm: w, height_mm: h } = S.size;
  const px = (mm) => Math.round((mm / 25.4) * S.output.dpi);
  let text = "";
  if (w && h) {
    text = `${w} × ${h} mm`;
    if (S.output.format === "png") text += `・${S.output.dpi} dpi で ${px(w)} × ${px(h)} px`;
  }
  $("preview-info").textContent = text;
  $("preview-box").classList.toggle("transparent", S.output.transparent);
}

// ----- 系列ごとの設定カード -----
const LINESTYLES = [["-", "実線"], ["--", "破線"], [":", "点線"], ["-.", "一点鎖線"], ["none", "なし"]];
const MARKERS = [["o", "● 丸"], ["s", "■ 四角"], ["^", "▲ 上三角"], ["v", "▼ 下三角"], ["D", "◆ ひし形"],
  ["x", "× バツ"], ["+", "＋ プラス"], ["*", "★ 星"], ["none", "なし"]];
const TRENDS = [["none", "なし"], ["linear", "直線（1 次式）"], ["poly2", "2 次式"], ["poly3", "3 次式"],
  ["exp", "指数 y = a·e^(bx)"], ["log", "対数 y = a·ln x + b"], ["power", "累乗 y = a·x^b"]];

function options(list, selected) {
  return list.map(([v, label]) => `<option value="${v}"${v === selected ? " selected" : ""}>${label}</option>`).join("");
}

function renderSeriesList() {
  syncSeries();
  const ct = S.chart_type;
  const noLine = ct === "scatter" || ct === "bar";
  const noMarker = ct === "bar";
  const noTrend = ct === "line" || ct === "bar";
  const dis = (off) => (off ? "disabled" : "");
  $("series-list").innerHTML = seriesGroups().map((g) => {
    const i = g.col - 1;
    const st = S.series[i];
    const errors = [["none", "なし"], ["fixed", "固定値 ±"], ["percent", "割合 ±%"]];
    if (g.errorCol !== null) errors.splice(1, 0, ["column", `誤差の列（${table.columns[g.errorCol] || "誤差"}）`]);
    if (g.repeats.length) errors.splice(1, 0, ["sd", `標準偏差（${g.repeats.length + 1} 回の測定）`], ["se", "標準誤差（標準偏差 / √n）"]);
    const meta = [g.repeats.length ? `${g.repeats.length + 1} 回の平均` : "", g.errorCol !== null ? "誤差の列あり" : ""]
      .filter(Boolean).join("・");
    const needValue = st.error === "fixed" || st.error === "percent";
    return `
    <div class="series-card" data-i="${i}">
      <div class="series-head">
        <input type="color" data-k="color" value="${st.color}" aria-label="色">
        <span class="series-title">${escapeHtml(g.name)}</span>
        <span class="series-meta">${escapeHtml(meta)}</span>
      </div>
      <div class="grid2">
        <label>線<select data-k="linestyle" ${dis(noLine)}>${options(LINESTYLES, st.linestyle)}</select></label>
        <label>太さ [pt]<input type="number" data-k="line_width" value="${st.line_width}" min="0" max="10" step="0.25" ${dis(noLine)}></label>
        <label>マーカー<select data-k="marker" ${dis(noMarker)}>${options(MARKERS, st.marker)}</select></label>
        <label>大きさ [pt]<input type="number" data-k="marker_size" value="${st.marker_size}" min="0" max="30" step="0.5" ${dis(noMarker)}></label>
      </div>
      <label class="switch-row">マーカーを塗りつぶす<input type="checkbox" class="switch" data-k="marker_fill" ${st.marker_fill ? "checked" : ""} ${dis(noMarker)}></label>
      <p class="sub-title">誤差棒</p>
      <div class="grid2">
        <label>種類<select data-k="error">${options(errors, st.error)}</select></label>
        <label class="${needValue ? "" : "is-off"}">${st.error === "percent" ? "割合 [%]" : "大きさ ±"}
          <input type="number" data-k="error_value" value="${st.error_value}" min="0" step="any" ${dis(!needValue)}></label>
      </div>
      <p class="sub-title">近似曲線${noTrend ? "（散布図のときだけ）" : ""}</p>
      <label>種類<select data-k="trend" ${dis(noTrend)}>${options(TRENDS, st.trend)}</select></label>
      <div class="grid2 ${st.trend === "none" || noTrend ? "is-off" : ""}">
        <label class="inline-switch">式<input type="checkbox" class="switch" data-k="trend_equation" ${st.trend_equation ? "checked" : ""} ${dis(st.trend === "none" || noTrend)}></label>
        <label class="inline-switch">R²<input type="checkbox" class="switch" data-k="trend_r2" ${st.trend_r2 ? "checked" : ""} ${dis(st.trend === "none" || noTrend)}></label>
      </div>
    </div>`;
  }).join("");
}

$("series-list").addEventListener("input", (e) => {
  const card = e.target.closest(".series-card");
  if (!card || !e.target.dataset.k) return;
  const st = S.series[Number(card.dataset.i)];
  const k = e.target.dataset.k;
  if (e.target.type === "checkbox") st[k] = e.target.checked;
  else if (e.target.type === "number") st[k] = e.target.value === "" ? 0 : Number(e.target.value);
  else st[k] = e.target.value;
  // 誤差棒・近似曲線の種類を変えたら，関係する入力欄の使える／使えないを更新する
  if (k === "error" || k === "trend") {
    const focusKey = k;
    renderSeriesList();
    $("series-list").querySelector(`.series-card[data-i="${card.dataset.i}"] [data-k="${focusKey}"]`)?.focus();
  }
  scheduleUpdate();
});

// ============================================================
//  5. プレビューの自動更新
// ============================================================
let timer = null;
let requestId = 0;

function onDataChanged() {
  updateLabelHints();
  scheduleUpdate();
}

function scheduleUpdate(delay = 400) {
  clearTimeout(timer);
  timer = setTimeout(updatePreview, delay); // 入力が止まってから少し待って更新
}

function collectSettings() {
  const { preset, ...rest } = S;
  return { ...rest, data: { columns: table.columns, rows: table.rows, roles: table.roles } };
}

// ============================================================
//  描画エンジン（サーバー版 / ブラウザ版）
// ============================================================
// uvicorn で起動したときはサーバー（FastAPI）で，GitHub Pages ではブラウザの中の Python（Pyodide）で描く．
// どちらも同じ api_core.py を実行するので，できあがるグラフとコードは同じ．
const BROWSER_FONTS = { latin: ["", "DejaVu Sans", "DejaVu Serif", "STIXGeneral"], jp: ["IPAexGothic"] };

const engine = {
  mode: "server",
  worker: null,
  nextId: 0,
  waiting: new Map(),

  // どちらで動かすかを決めて，使えるフォントの一覧を返す
  async start() {
    try {
      const res = await fetch("api/fonts");
      if (res.ok && (res.headers.get("content-type") || "").includes("json")) {
        this.mode = "server";
        return await res.json();
      }
    } catch { /* サーバーが無い（GitHub Pages など） */ }
    this.mode = "browser";
    this.worker = new Worker("static/engine-worker.js", { type: "module" });
    this.worker.onmessage = (e) => this.onMessage(e.data);
    this.worker.onerror = (e) => this.onMessage({ type: "failed", text: e.message || "読み込みエラー" });
    return BROWSER_FONTS;
  },

  onMessage(msg) {
    if (msg.type === "progress") {
      setStatus(msg.text, "busy");
    } else if (msg.type === "failed") {
      showMessages([`Python の準備に失敗しました: ${msg.text}`,
        "インターネットにつながっているか確認して，ページを再読み込みしてください．"], "error");
      setStatus("準備に失敗しました", "error");
    } else if (msg.type === "result") {
      this.waiting.get(msg.id)?.(msg.result);
      this.waiting.delete(msg.id);
    }
  },

  // kind: "render" / "export"．結果は { status, body }（サーバー版の HTTP の応答と同じ形）
  async call(kind, payload) {
    if (this.mode === "server") {
      const res = await fetch(`api/${kind}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      });
      if (kind === "export" && res.ok) return { status: res.status, body: { blob: await res.blob() } };
      return { status: res.status, body: await res.json().catch(() => ({})) };
    }
    const id = ++this.nextId;
    return new Promise((resolve) => {
      this.waiting.set(id, resolve);
      this.worker.postMessage({ id, kind, payload });
    });
  },
};

// 動きを減らす設定（OS の「視差効果を減らす」）のときはアニメーションを省く
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

let rendering = false; // 描画中か
let rerender = false;  // 描画中にまた変更があったか（終わったらもう一度だけ描く）

async function updatePreview() {
  if (rendering) { rerender = true; return; }
  rendering = true;
  const id = ++requestId;
  saveToStorage();
  if (!engine.booting) setStatus("描画しています", "busy");
  // すぐ終わるときはチラつかないよう，少し待ってから「描画中」の光を出す
  const loadingTimer = setTimeout(() => $("preview-box").classList.add("loading"), 150);
  try {
    const { status, body } = await engine.call("render", collectSettings());
    engine.booting = false;
    if (id !== requestId) return; // もっと新しい更新が走っている
    if (status !== 200) {
      showMessages(body.errors || ["エラーが発生しました"], "error");
      if (body.code) showCode(body.code);
      setStatus("エラー（直すと自動で更新されます）", "error");
      return;
    }
    await showPreview("data:image/png;base64," + body.image);
    showCode(body.code);
    showMessages(body.warnings || [], "warn");
    setStatus("プレビューは最新です", "done");
  } catch (err) {
    if (id !== requestId) return;
    showMessages(["サーバーに接続できません．ターミナルで uvicorn が動いているか確認してください．"], "error");
    setStatus("接続エラー", "error");
  } finally {
    clearTimeout(loadingTimer);
    rendering = false;
    if (rerender) {
      rerender = false;
      updatePreview();
    } else {
      $("preview-box").classList.remove("loading");
    }
  }
}

// 新しい画像を読み込んでから，ぼかし → くっきり で切り替える
function showPreview(src) {
  const img = $("preview");
  return new Promise((resolve) => {
    img.onload = () => {
      img.classList.add("shown");
      if (!reduceMotion.matches) {
        img.classList.remove("reveal-img");
        void img.offsetWidth; // アニメーションを最初からやり直すため
        img.classList.add("reveal-img");
      }
      resolve();
    };
    img.onerror = () => resolve();
    img.src = src;
  });
}

// state: "busy"（処理中・光る文字）/ "done" / "error" / ""
function setStatus(text, state = "") {
  $("status-text").textContent = text;
  for (const c of ["busy", "done", "error"]) $("status").classList.toggle(c, c === state);
}

function showMessages(list, kind) {
  $("messages").innerHTML = list.map((m) => `<div class="${kind}">${escapeHtml(m)}</div>`).join("");
}

function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// ============================================================
//  6. 保存
// ============================================================
async function download() {
  const settings = collectSettings();
  const format = settings.output.format;
  setStatus(`${format.toUpperCase()} を作成しています`, "busy");
  let result;
  try {
    result = await engine.call("export", settings);
  } catch {
    result = { status: 0, body: { errors: ["サーバーに接続できません"] } };
  }
  const { status, body } = result;
  if (status !== 200) {
    setStatus("保存できませんでした", "error");
    return showMessages(body.errors || ["保存に失敗しました"], "error");
  }
  // サーバー版はファイルそのもの，ブラウザ版は base64 の文字列で届く
  const blob = body.blob || new Blob([Uint8Array.from(atob(body.data), (c) => c.charCodeAt(0))], { type: body.media_type });
  saveBlob(blob, `graph.${format}`);
  setStatus(`graph.${format} を保存しました`, "done");
}

function saveBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function savePython() {
  saveBlob(new Blob([currentCode], { type: "text/x-python;charset=utf-8" }), "graph.py");
}

// ============================================================
//  7. Python コードの表示（簡易シンタックスハイライト）
// ============================================================
let currentCode = "";
const PY_KEYWORDS = new Set(["import", "from", "as", "def", "return", "for", "in", "if", "else", "elif", "not",
  "and", "or", "continue", "break", "while", "True", "False", "None", "with", "lambda", "class", "pass"]);
const PY_BUILTINS = new Set(["print", "len", "range", "enumerate", "zip", "min", "max", "list", "dict", "str", "int", "float"]);

function highlightPython(code) {
  const re = /("""[\s\S]*?"""|'''[\s\S]*?''')|(#[^\n]*)|((?:rf|fr|f|r)?"(?:\\.|[^"\\\n])*"|(?:rf|fr|f|r)?'(?:\\.|[^'\\\n])*')|\b(\d+(?:\.\d*)?(?:[eE][-+]?\d+)?)\b|\b([A-Za-z_]\w*)\b/g;
  let out = "", last = 0, m, prevWord = "";
  while ((m = re.exec(code))) {
    out += escapeHtml(code.slice(last, m.index));
    const t = escapeHtml(m[0]);
    if (m[1] || m[3]) out += `<span class="tok-str">${t}</span>`;
    else if (m[2]) out += `<span class="tok-com">${t}</span>`;
    else if (m[4]) out += `<span class="tok-num">${t}</span>`;
    else if (PY_KEYWORDS.has(m[0])) out += `<span class="tok-kw">${t}</span>`;
    else if (prevWord === "def") out += `<span class="tok-def">${t}</span>`;
    else if (PY_BUILTINS.has(m[0])) out += `<span class="tok-bi">${t}</span>`;
    else out += t;
    if (m[5]) prevWord = m[0];
    last = re.lastIndex;
  }
  return out + escapeHtml(code.slice(last));
}

let streamFrame = null; // コードを流れるように表示している途中なら requestAnimationFrame の番号

function showCode(code) {
  if (code === currentCode) return;
  currentCode = code;
  if (streamFrame) return; // 表示の途中なら，次のフレームで新しいコードが使われる
  $("code").innerHTML = highlightPython(code);
  if ($("code-panel").classList.contains("open") && !reduceMotion.matches) {
    const el = $("code");
    el.classList.remove("refresh");
    void el.offsetWidth;
    el.classList.add("refresh"); // 更新されたことが分かるよう，軽くフェードする
  }
}

// コードが上から流れるように現れる（末尾で丸が明滅する）
function streamCode() {
  cancelAnimationFrame(streamFrame);
  streamFrame = null;
  if (reduceMotion.matches || !currentCode) {
    $("code").innerHTML = highlightPython(currentCode);
    return;
  }
  const start = performance.now();
  const duration = Math.min(1100, 300 + currentCode.length * 0.12);
  const step = (now) => {
    const t = Math.min(1, (now - start) / duration);
    const eased = 1 - Math.pow(1 - t, 2); // 最初は速く，最後はゆっくり
    const code = currentCode;
    if (t < 1) {
      const n = Math.floor(code.length * eased);
      $("code").innerHTML = highlightPython(code.slice(0, n)) + '<span class="stream-cursor"></span>';
      streamFrame = requestAnimationFrame(step);
    } else {
      $("code").innerHTML = highlightPython(code);
      streamFrame = null;
    }
  };
  streamFrame = requestAnimationFrame(step);
}

function setCodeOpen(open) {
  $("code-panel").classList.toggle("open", open);
  $("code-toggle").setAttribute("aria-expanded", String(open));
  if (open) {
    streamCode();
    if (innerWidth <= 860) setTimeout(() => $("code-panel").scrollIntoView({ behavior: "smooth", block: "end" }), 50);
  }
}

$("code-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(currentCode);
    flash($("code-copy"), "コピーしました");
  } catch {
    flash($("code-copy"), "コピーできませんでした");
  }
});

function flash(button, text) {
  const old = button.textContent;
  button.textContent = text;
  setTimeout(() => (button.textContent = old), 1500);
}

// ============================================================
//  8. メニュー（保存の設定・その他）とタブ
// ============================================================
function closeMenus(except = null) {
  document.querySelectorAll(".popover").forEach((p) => { if (p !== except) p.hidden = true; });
  document.querySelectorAll("[data-menu]").forEach((b) => {
    if (!except || b.dataset.menu !== except.id) b.setAttribute("aria-expanded", "false");
  });
}

function openMenu(menu, button) {
  closeMenus(menu);
  menu.hidden = false;
  button?.setAttribute("aria-expanded", "true");
}

document.addEventListener("click", (e) => {
  const opener = e.target.closest("[data-menu]");
  if (opener) {
    const menu = $(opener.dataset.menu);
    if (menu.hidden) openMenu(menu, opener);
    else closeMenus();
    return;
  }
  // メニューの外を押したら閉じる（保存の設定の中の操作では閉じない）
  if (!e.target.closest(".popover")) closeMenus();
  else if (e.target.closest(".menu-item")) closeMenus();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  closeMenus();
  if ($("code-panel").classList.contains("open")) setCodeOpen(false);
});

function showTab(name) {
  document.querySelectorAll(".tabs [data-tab]").forEach((b) => {
    const on = b.dataset.tab === name;
    b.classList.toggle("active", on);
    b.setAttribute("aria-selected", String(on));
  });
  document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.dataset.panel !== name));
  try { localStorage.setItem(UI_KEY, JSON.stringify({ tab: name })); } catch { /* 無視 */ }
}

// ============================================================
//  9. 前回の内容を覚えておく（このブラウザの中だけ）
// ============================================================
function saveToStorage() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      columns: table.columns, rows: table.rows, roles: table.roles, settings: S,
    }));
  } catch { /* 保存できなくても動作には影響しない */ }
}

function loadFromStorage() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (!saved || !Array.isArray(saved.columns) || !Array.isArray(saved.rows)) return false;
    table.columns = saved.columns;
    table.rows = saved.rows;
    table.roles = Array.isArray(saved.roles) ? saved.roles : [];
    const base = defaultSettings();
    deepMerge(base, saved.settings || {});
    base.series = Array.isArray(saved.settings?.series) ? saved.settings.series : [];
    S = base;
    return true;
  } catch {
    return false;
  }
}

function resetAll() {
  if (!confirm("データと設定をすべて最初の状態に戻します．よろしいですか？")) return;
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* 無視 */ }
  table.columns = [...SAMPLE.columns];
  table.rows = SAMPLE.rows.map((r) => [...r]);
  table.roles = ["series"];
  S = defaultSettings();
  applyPreset("report");
  renderAllData();
}

// ============================================================
//  10. 起動
// ============================================================
async function loadFonts() {
  const JP_NAMES = {
    "IPAexGothic": "IPAexゴシック（同梱）", "Hiragino Sans": "ヒラギノ角ゴシック", "Hiragino Mincho ProN": "ヒラギノ明朝",
    "Hiragino Maru Gothic ProN": "ヒラギノ丸ゴ", "YuGothic": "游ゴシック", "YuMincho": "游明朝",
    "BIZ UDGothic": "BIZ UDゴシック", "BIZ UDMincho": "BIZ UD明朝", "Noto Sans CJK JP": "Noto Sans CJK JP",
    "Noto Serif CJK JP": "Noto Serif CJK JP", "MS Gothic": "MS ゴシック", "MS Mincho": "MS 明朝",
  };
  const LATIN_NAMES = { "": "（日本語と同じ）", "STIXGeneral": "STIX（Times 風）" };
  fonts = await engine.start();
  $("font-latin").innerHTML = fonts.latin.map((f) => `<option value="${f}">${LATIN_NAMES[f] ?? f}</option>`).join("");
  $("font-jp").innerHTML = fonts.jp.map((f) => `<option value="${f}">${JP_NAMES[f] || f}</option>`).join("");
}

function wireEvents() {
  for (const el of boundControls()) {
    if (el.tagName === "DIV") { // 切り替えボタンの組
      el.addEventListener("click", (e) => {
        const b = e.target.closest("button[data-value]");
        if (!b || b.disabled) return;
        setPath(S, el.dataset.bind, parseValue(b.dataset.value, el.dataset.kind));
        el.querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
        afterSettingChange(el.dataset.bind);
      });
    } else {
      el.addEventListener("input", () => onControlChange(el));
      el.addEventListener("change", () => onControlChange(el));
    }
  }
  document.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
  document.querySelectorAll("[data-size]").forEach((b) => b.addEventListener("click", () => {
    const [w, h] = b.dataset.size.split("x").map(Number);
    S.size = { width_mm: w, height_mm: h };
    stateToUI();
    scheduleUpdate(0);
  }));
  document.querySelectorAll(".tabs [data-tab]").forEach((b) => b.addEventListener("click", () => showTab(b.dataset.tab)));
  $("save-main").addEventListener("click", download);
  $("save-py").addEventListener("click", savePython);
  $("code-save").addEventListener("click", savePython);
  $("code-toggle").addEventListener("click", () => setCodeOpen(!$("code-panel").classList.contains("open")));
  $("more-code").addEventListener("click", () => setCodeOpen(true));
  $("code-close").addEventListener("click", () => setCodeOpen(false));
  $("reset-all").addEventListener("click", resetAll);
  $("row-add").addEventListener("click", addRow);
  $("row-del").addEventListener("click", () => deleteRow());
  $("col-add").addEventListener("click", addColumn);
  $("col-del").addEventListener("click", () => deleteColumn());
  $("csv-open").addEventListener("click", () => $("csv-file").click());
  $("clear-data").addEventListener("click", clearData);
}

async function init() {
  await loadFonts();
  if (engine.mode === "browser") {
    engine.booting = true; // 最初の描画が終わるまでは，準備の進み具合を表示する
    setStatus("Python を準備しています", "busy");
  }
  wireEvents();
  let tab = "chart";
  try { tab = JSON.parse(localStorage.getItem(UI_KEY))?.tab || "chart"; } catch { /* 無視 */ }
  showTab(tab);
  const restored = loadFromStorage();
  if (restored) {
    // 保存されていたフォントがこの PC に無ければ置き換える
    if (!fonts.jp.includes(S.font.jp)) S.font.jp = fonts.jp[0];
    if (!fonts.latin.includes(S.font.latin)) S.font.latin = "";
    syncSeries();
    fixSeriesErrors();
    stateToUI();
    renderAllData();
  } else {
    syncSeries();
    renderGrid();
    applyPreset("report"); // 初期状態はレポート用
  }
}

init();
