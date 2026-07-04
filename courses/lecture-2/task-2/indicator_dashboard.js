const DATA_PATHS = {
  indicators: "data/indicator_values.csv",
  selected: "data/selected_targets.csv",
  latest: "data/latest_indicator_summary.csv",
};

const state = {
  code: null,
  range: "120",
  rowsByCode: new Map(),
  selectedByCode: new Map(),
  latestByCode: new Map(),
  orderedCodes: [],
};

const color = {
  text: "#1e2732",
  muted: "#66717e",
  grid: "#e2e7eb",
  blue: "#2f6f9f",
  red: "#c9443f",
  green: "#23845d",
  amber: "#bd7a22",
  violet: "#7357a6",
  gray: "#89939e",
};

function parseCsv(text) {
  const clean = text.replace(/^\uFEFF/, "");
  const rows = [];
  let row = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < clean.length; i += 1) {
    const ch = clean[i];
    const next = clean[i + 1];
    if (inQuotes) {
      if (ch === '"' && next === '"') {
        field += '"';
        i += 1;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        field += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else if (ch !== "\r") {
      field += ch;
    }
  }

  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }

  const headers = rows.shift() || [];
  return rows
    .filter((items) => items.some((item) => item !== ""))
    .map((items) => Object.fromEntries(headers.map((header, index) => [header, items[index] ?? ""])));
}

function toNumber(value) {
  if (value === "" || value == null) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function normalizeRow(row) {
  const numericFields = [
    "open", "high", "low", "close", "volume", "amount", "pre_close",
    "qfq_open", "qfq_high", "qfq_low", "qfq_close", "qfq_pre_close", "ret_1d",
    "rsi14", "macd_dif", "macd_dea", "macd_hist", "boll_mid", "boll_upper",
    "boll_lower", "boll_percent_b", "boll_bandwidth", "kdj_rsv9", "kdj_k",
    "kdj_d", "kdj_j",
  ];
  const out = { ...row };
  numericFields.forEach((field) => {
    out[field] = toNumber(out[field]);
  });
  return out;
}

function normalizeSelected(row) {
  const out = { ...row };
  [
    "selection_rank", "selection_score", "return_20260401_to_20260703",
    "pct_chg_20260703", "pe_ttm_snapshot", "snapshot_turnover_yuan",
    "main_net_inflow_yuan",
  ].forEach((field) => {
    out[field] = toNumber(out[field]);
  });
  return out;
}

function fmtNumber(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return "--";
  return value.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function fmtPct(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return "--";
  return `${(value * 100).toFixed(digits)}%`;
}

function fmtDate(value) {
  if (!value) return "--";
  const s = String(value);
  return `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6, 8)}`;
}

function fmtMoney(value) {
  if (value == null || Number.isNaN(value)) return "--";
  const abs = Math.abs(value);
  if (abs >= 100000000) return `${(value / 100000000).toFixed(2)} 亿`;
  if (abs >= 10000) return `${(value / 10000).toFixed(2)} 万`;
  return fmtNumber(value, 0);
}

function classForSigned(value) {
  if (value == null) return "neutral";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "neutral";
}

function statusCn(text) {
  if (!text) return "--";
  if (text.includes("limit-up")) return "涨停后等待换手与回踩确认";
  if (text.includes("Core momentum")) return "强势核心，等待分歧后承接";
  if (text.includes("Trend candidate")) return "趋势候选，观察短期平台支撑";
  if (text.includes("Relatively balanced")) return "相对均衡，观察补涨与趋势延续";
  if (text.includes("High-volatility")) return "高弹性高波动，等待二次确认";
  return text;
}

function getVisibleRows() {
  const rows = state.rowsByCode.get(state.code) || [];
  if (state.range === "all") return rows;
  const count = Number(state.range);
  return rows.slice(Math.max(0, rows.length - count));
}

function setupCanvas(canvas) {
  const dpr = window.devicePixelRatio || 1;
  const baseHeight = Number(canvas.dataset.height || canvas.getAttribute("height") || 220);
  canvas.style.height = `${baseHeight}px`;
  const rect = canvas.getBoundingClientRect();
  const cssWidth = Math.max(320, rect.width || canvas.parentElement?.clientWidth || 640);
  canvas.width = Math.floor(cssWidth * dpr);
  canvas.height = Math.floor(baseHeight * dpr);
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width: cssWidth, height: baseHeight };
}

function drawAxes(ctx, area, yMin, yMax, labels) {
  ctx.clearRect(0, 0, area.outerWidth, area.outerHeight);
  ctx.strokeStyle = color.grid;
  ctx.lineWidth = 1;
  ctx.font = "11px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillStyle = color.muted;

  for (let i = 0; i <= 4; i += 1) {
    const y = area.top + (area.height * i) / 4;
    ctx.beginPath();
    ctx.moveTo(area.left, y);
    ctx.lineTo(area.left + area.width, y);
    ctx.stroke();
    const value = yMax - ((yMax - yMin) * i) / 4;
    ctx.fillText(fmtNumber(value, 2), area.left + area.width + 8, y + 4);
  }

  ctx.strokeStyle = "#cdd4da";
  ctx.beginPath();
  ctx.moveTo(area.left, area.top);
  ctx.lineTo(area.left, area.top + area.height);
  ctx.lineTo(area.left + area.width, area.top + area.height);
  ctx.stroke();

  if (labels.length) {
    const positions = [0, Math.floor((labels.length - 1) / 2), labels.length - 1];
    positions.forEach((idx, order) => {
      const x = area.left + (labels.length === 1 ? 0 : (area.width * idx) / (labels.length - 1));
      const label = fmtDate(labels[idx]);
      const offset = order === 2 ? -66 : order === 1 ? -32 : 0;
      ctx.fillText(label, x + offset, area.top + area.height + 18);
    });
  }
}

function scaledPoints(rows, field, area, yMin, yMax) {
  const denom = yMax - yMin || 1;
  return rows.map((row, index) => {
    const value = row[field];
    if (value == null) return null;
    const x = area.left + (rows.length === 1 ? 0 : (area.width * index) / (rows.length - 1));
    const y = area.top + area.height - ((value - yMin) / denom) * area.height;
    return { x, y, value };
  });
}

function drawLine(ctx, points, stroke, width = 1.5) {
  ctx.strokeStyle = stroke;
  ctx.lineWidth = width;
  ctx.beginPath();
  let started = false;
  points.forEach((point) => {
    if (!point) {
      started = false;
      return;
    }
    if (!started) {
      ctx.moveTo(point.x, point.y);
      started = true;
    } else {
      ctx.lineTo(point.x, point.y);
    }
  });
  ctx.stroke();
}

function drawThreshold(ctx, area, value, yMin, yMax, stroke) {
  const y = area.top + area.height - ((value - yMin) / (yMax - yMin || 1)) * area.height;
  ctx.save();
  ctx.strokeStyle = stroke;
  ctx.setLineDash([4, 4]);
  ctx.beginPath();
  ctx.moveTo(area.left, y);
  ctx.lineTo(area.left + area.width, y);
  ctx.stroke();
  ctx.restore();
}

function minMax(rows, fields, fallback = [0, 1]) {
  const values = [];
  rows.forEach((row) => {
    fields.forEach((field) => {
      if (row[field] != null && Number.isFinite(row[field])) values.push(row[field]);
    });
  });
  if (!values.length) return fallback;
  let min = Math.min(...values);
  let max = Math.max(...values);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * 0.08;
  return [min - pad, max + pad];
}

function drawPrice(rows) {
  const canvas = document.getElementById("priceCanvas");
  const { ctx, width, height } = setupCanvas(canvas);
  const area = { left: 54, top: 18, width: width - 122, height: height - 52, outerWidth: width, outerHeight: height };
  const [yMin, yMax] = minMax(rows, ["qfq_close", "boll_upper", "boll_lower"]);
  drawAxes(ctx, area, yMin, yMax, rows.map((row) => row.trade_date));
  drawLine(ctx, scaledPoints(rows, "boll_upper", area, yMin, yMax), color.red, 1.2);
  drawLine(ctx, scaledPoints(rows, "boll_mid", area, yMin, yMax), color.gray, 1.1);
  drawLine(ctx, scaledPoints(rows, "boll_lower", area, yMin, yMax), color.green, 1.2);
  drawLine(ctx, scaledPoints(rows, "qfq_close", area, yMin, yMax), color.blue, 2);
}

function drawRsi(rows) {
  const canvas = document.getElementById("rsiCanvas");
  const { ctx, width, height } = setupCanvas(canvas);
  const area = { left: 42, top: 14, width: width - 92, height: height - 44, outerWidth: width, outerHeight: height };
  drawAxes(ctx, area, 0, 100, rows.map((row) => row.trade_date));
  drawThreshold(ctx, area, 70, 0, 100, color.red);
  drawThreshold(ctx, area, 30, 0, 100, color.green);
  drawLine(ctx, scaledPoints(rows, "rsi14", area, 0, 100), color.violet, 1.8);
}

function drawMacd(rows) {
  const canvas = document.getElementById("macdCanvas");
  const { ctx, width, height } = setupCanvas(canvas);
  const area = { left: 42, top: 14, width: width - 92, height: height - 44, outerWidth: width, outerHeight: height };
  const [yMin, yMax] = minMax(rows, ["macd_dif", "macd_dea", "macd_hist"]);
  drawAxes(ctx, area, yMin, yMax, rows.map((row) => row.trade_date));
  drawThreshold(ctx, area, 0, yMin, yMax, "#8f99a3");
  const zeroY = area.top + area.height - ((0 - yMin) / (yMax - yMin || 1)) * area.height;
  const barWidth = Math.max(1, area.width / Math.max(rows.length, 1) - 1);
  rows.forEach((row, index) => {
    if (row.macd_hist == null) return;
    const x = area.left + (rows.length === 1 ? 0 : (area.width * index) / (rows.length - 1)) - barWidth / 2;
    const y = area.top + area.height - ((row.macd_hist - yMin) / (yMax - yMin || 1)) * area.height;
    ctx.fillStyle = row.macd_hist >= 0 ? "rgba(201, 68, 63, 0.62)" : "rgba(35, 132, 93, 0.62)";
    ctx.fillRect(x, Math.min(y, zeroY), barWidth, Math.max(1, Math.abs(zeroY - y)));
  });
  drawLine(ctx, scaledPoints(rows, "macd_dif", area, yMin, yMax), color.blue, 1.5);
  drawLine(ctx, scaledPoints(rows, "macd_dea", area, yMin, yMax), color.amber, 1.5);
}

function drawKdj(rows) {
  const canvas = document.getElementById("kdjCanvas");
  const { ctx, width, height } = setupCanvas(canvas);
  const area = { left: 42, top: 14, width: width - 92, height: height - 44, outerWidth: width, outerHeight: height };
  const [rawMin, rawMax] = minMax(rows, ["kdj_k", "kdj_d", "kdj_j"], [0, 100]);
  const yMin = Math.min(0, rawMin);
  const yMax = Math.max(100, rawMax);
  drawAxes(ctx, area, yMin, yMax, rows.map((row) => row.trade_date));
  drawThreshold(ctx, area, 80, yMin, yMax, color.red);
  drawThreshold(ctx, area, 20, yMin, yMax, color.green);
  drawLine(ctx, scaledPoints(rows, "kdj_k", area, yMin, yMax), color.blue, 1.5);
  drawLine(ctx, scaledPoints(rows, "kdj_d", area, yMin, yMax), color.amber, 1.5);
  drawLine(ctx, scaledPoints(rows, "kdj_j", area, yMin, yMax), color.violet, 1.4);
}

function metricRow(label, value, className = "") {
  return `<div class="metric-row"><dt>${label}</dt><dd class="${className}">${value}</dd></div>`;
}

function renderTabs() {
  const tabs = document.getElementById("stockTabs");
  tabs.innerHTML = state.orderedCodes.map((code) => {
    const info = state.selectedByCode.get(code);
    return `<button type="button" data-code="${code}" class="${code === state.code ? "active" : ""}">
      <span class="tab-name">${info?.name || code}</span>
      <span class="tab-code">${code}</span>
    </button>`;
  }).join("");
  tabs.querySelectorAll("button").forEach((button) => {
    button.addEventListener("click", () => {
      state.code = button.dataset.code;
      render();
    });
  });
}

function renderSummary(latest, selected) {
  const summary = document.getElementById("summaryGrid");
  const ret = latest?.ret_1d;
  summary.innerHTML = [
    ["收盘价", fmtNumber(latest?.qfq_close, 2), fmtDate(latest?.trade_date), ""],
    ["日涨跌", fmtPct(ret, 2), "基于 Fuyao 未复权日线", classForSigned(ret)],
    ["RSI14", fmtNumber(latest?.rsi14, 2), latest?.rsi_note || "--", latest?.rsi14 >= 70 ? "positive" : latest?.rsi14 <= 30 ? "negative" : "neutral"],
    ["区间涨幅", fmtPct(selected?.return_20260401_to_20260703, 2), "2026-04-01 至 2026-07-03", classForSigned(selected?.return_20260401_to_20260703)],
    ["成交额", fmtMoney(latest?.amount), "最新交易日", ""],
  ].map(([label, value, sub, className]) => `
    <div class="summary-tile">
      <div class="label">${label}</div>
      <div class="value ${className}">${value}</div>
      <div class="sub">${sub}</div>
    </div>
  `).join("");
}

function renderDetails(latest, selected) {
  document.getElementById("latestDate").textContent = fmtDate(latest?.trade_date);
  document.getElementById("latestMetrics").innerHTML = [
    metricRow("开盘 / 最高 / 最低", `${fmtNumber(latest?.open, 2)} / ${fmtNumber(latest?.high, 2)} / ${fmtNumber(latest?.low, 2)}`),
    metricRow("成交量", fmtNumber(latest?.volume, 0)),
    metricRow("成交额", fmtMoney(latest?.amount)),
    metricRow("MACD DIF / DEA / Hist", `${fmtNumber(latest?.macd_dif, 4)} / ${fmtNumber(latest?.macd_dea, 4)} / ${fmtNumber(latest?.macd_hist, 4)}`),
    metricRow("BOLL %B / 带宽", `${fmtNumber(latest?.boll_percent_b, 4)} / ${fmtNumber(latest?.boll_bandwidth, 4)}`),
    metricRow("KDJ K / D / J", `${fmtNumber(latest?.kdj_k, 2)} / ${fmtNumber(latest?.kdj_d, 2)} / ${fmtNumber(latest?.kdj_j, 2)}`),
  ].join("");

  document.getElementById("selectionInfo").innerHTML = [
    metricRow("行业", selected?.industry_level1 || "--"),
    metricRow("排名", selected?.selection_rank ? `第 ${selected.selection_rank} 位` : "--"),
    metricRow("PE TTM", fmtNumber(selected?.pe_ttm_snapshot, 2)),
    metricRow("主力净流入", fmtMoney(selected?.main_net_inflow_yuan), classForSigned(selected?.main_net_inflow_yuan)),
    metricRow("快照成交额", fmtMoney(selected?.snapshot_turnover_yuan)),
    metricRow("观察状态", statusCn(selected?.status)),
  ].join("");
}

function renderCharts(rows) {
  drawPrice(rows);
  drawRsi(rows);
  drawMacd(rows);
  drawKdj(rows);
}

function render() {
  const rows = getVisibleRows();
  const fullRows = state.rowsByCode.get(state.code) || [];
  const latest = state.latestByCode.get(state.code) || fullRows[fullRows.length - 1];
  const selected = state.selectedByCode.get(state.code);

  renderTabs();
  renderSummary(latest, selected);
  renderDetails(latest, selected);

  document.getElementById("stockTitle").textContent = `${selected?.name || state.code} ${state.code}`;
  document.getElementById("stockSubtitle").textContent = `${selected?.industry_level1 || "--"} · ${rows.length} 个交易日 · ${fmtDate(rows[0]?.trade_date)} 至 ${fmtDate(rows[rows.length - 1]?.trade_date)}`;
  document.getElementById("rsiNote").textContent = latest?.rsi_note || "--";
  document.getElementById("macdNote").textContent = latest?.macd_note || "--";
  document.getElementById("kdjNote").textContent = latest?.kdj_note || "--";

  renderCharts(rows);
}

async function loadData() {
  const [indicatorText, selectedText, latestText] = await Promise.all([
    fetch(DATA_PATHS.indicators).then((res) => res.text()),
    fetch(DATA_PATHS.selected).then((res) => res.text()),
    fetch(DATA_PATHS.latest).then((res) => res.text()),
  ]);

  const indicators = parseCsv(indicatorText).map(normalizeRow);
  const selected = parseCsv(selectedText).map(normalizeSelected);
  const latest = parseCsv(latestText).map(normalizeRow);

  selected.sort((a, b) => (a.selection_rank ?? 999) - (b.selection_rank ?? 999));
  state.orderedCodes = selected.map((row) => row.code);
  state.code = state.orderedCodes[0];

  selected.forEach((row) => state.selectedByCode.set(row.code, row));
  latest.forEach((row) => state.latestByCode.set(row.code, row));

  state.orderedCodes.forEach((code) => {
    const rows = indicators
      .filter((row) => row.code === code)
      .sort((a, b) => String(a.trade_date).localeCompare(String(b.trade_date)));
    state.rowsByCode.set(code, rows);
  });

  const allRows = [...state.rowsByCode.values()].flat();
  const minDate = allRows.reduce((min, row) => !min || row.trade_date < min ? row.trade_date : min, null);
  const maxDate = allRows.reduce((max, row) => !max || row.trade_date > max ? row.trade_date : max, null);
  document.getElementById("dataMeta").textContent = `Fuyao 日线缓存 · ${fmtDate(minDate)} 至 ${fmtDate(maxDate)} · ${allRows.length} 行`;

  document.querySelectorAll(".range-control button").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".range-control button").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      state.range = button.dataset.range;
      render();
    });
  });

  render();
}

window.addEventListener("resize", () => {
  if (state.code) renderCharts(getVisibleRows());
});

loadData().catch((error) => {
  document.body.innerHTML = `<main class="app"><div class="empty-state">数据加载失败：${error.message}</div></main>`;
});
