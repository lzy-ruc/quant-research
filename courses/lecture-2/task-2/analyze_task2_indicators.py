from __future__ import annotations

import contextlib
import io
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

TASK_DIR = Path(__file__).resolve().parent
ROOT_DIR = TASK_DIR.parents[2]
PROJECT_DIR = ROOT_DIR / "quant_a_share_daily"
OUT_DATA_DIR = TASK_DIR / "data"
FIG_DIR = TASK_DIR / "figures"
MPL_DIR = TASK_DIR / ".mplconfig"
WATCHLIST_PATH = OUT_DATA_DIR / "real_top_down_watchlist.json"
FUYAO_RAW_DIR = PROJECT_DIR / "data" / "raw" / "fuyao"
SH_TZ = ZoneInfo("Asia/Shanghai")

for directory in [OUT_DATA_DIR, FIG_DIR, MPL_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("MPLCONFIGDIR", str(MPL_DIR))

_import_stderr = io.StringIO()
with contextlib.redirect_stderr(_import_stderr):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

IMPORT_WARNINGS = _import_stderr.getvalue()

SELECTED_COUNT = 5
RSI_WINDOW = 14
BOLL_WINDOW = 20
BOLL_STD = 2
KDJ_WINDOW = 9
KDJ_SMOOTH = 3
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

SOURCE_LINKS = [
    ("Investopedia - RSI", "https://www.investopedia.com/terms/r/rsi.asp"),
    ("Investopedia - MACD", "https://www.investopedia.com/terms/m/macd.asp"),
    ("Investopedia - Bollinger Bands", "https://www.investopedia.com/trading/using-bollinger-bands-to-gauge-trends/"),
    ("Investopedia - Stochastic Oscillator", "https://www.investopedia.com/articles/technical/073001.asp"),
]


def load_processed_table(name: str) -> pd.DataFrame:
    processed_dir = PROJECT_DIR / "data" / "processed"
    pkl_path = processed_dir / f"{name}.pkl"
    parquet_path = processed_dir / f"{name}.parquet"
    if pkl_path.exists():
        return pd.read_pickle(pkl_path)
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    raise FileNotFoundError(f"Missing processed table: {name}")


def latest_signal_file() -> Path:
    signal_dir = PROJECT_DIR / "outputs" / "signals"
    files = sorted(signal_dir.glob("signal_*.csv"))
    if not files:
        raise FileNotFoundError(f"No signal_*.csv found under {signal_dir}")
    return files[-1]


def load_json_items(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload.get("data", {}) if isinstance(payload, dict) else {}
    items = data.get("item", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def infer_board(code: str) -> str:
    symbol = code.split(".")[0]
    if symbol.startswith("688"):
        return "STAR"
    if symbol.startswith("300"):
        return "ChiNext"
    if symbol.startswith(("8", "9")):
        return "BSE"
    return "Main"


def ms_to_trade_date(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, unit="ms", utc=True).dt.tz_convert(SH_TZ).dt.strftime("%Y%m%d")


def load_real_watchlist_context() -> dict | None:
    price_path = FUYAO_RAW_DIR / "price_historical.json"
    snapshot_path = FUYAO_RAW_DIR / "price_snapshot.json"
    if not WATCHLIST_PATH.exists() or not price_path.exists():
        return None

    watchlist = json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
    targets = watchlist.get("final_watchlist", [])
    if not targets:
        return None

    target_codes = [item["ts_code"] for item in targets]
    target_names = {item["ts_code"]: item.get("name", "") for item in targets}
    target_industries = {item["ts_code"]: item.get("industry", "") for item in targets}

    hist_items = load_json_items(price_path)
    if not hist_items:
        return None

    rows = []
    for item in hist_items:
        code = item.get("_request_thscode") or item.get("_data_thscode") or item.get("thscode")
        if code not in target_codes:
            continue
        rows.append(
            {
                "code": code,
                "trade_date": datetime.fromtimestamp(item["date_ms"] / 1000, SH_TZ).strftime("%Y%m%d"),
                "open": item.get("open_price"),
                "high": item.get("high_price"),
                "low": item.get("low_price"),
                "close": item.get("close_price"),
                "volume": item.get("volume"),
                "amount": item.get("turnover"),
                "adj_factor": 1.0,
                "limit_up": np.nan,
                "limit_down": np.nan,
                "is_paused": False,
            }
        )

    price = pd.DataFrame(rows)
    if price.empty:
        return None

    analysis_date = str(watchlist.get("analysis_date", "")).replace("-", "")
    if snapshot_path.exists() and analysis_date:
        snapshot_rows = []
        existing = set(zip(price["code"], price["trade_date"]))
        for item in load_json_items(snapshot_path):
            code = item.get("thscode")
            if code not in target_codes or (code, analysis_date) in existing:
                continue
            snapshot_rows.append(
                {
                    "code": code,
                    "trade_date": analysis_date,
                    "open": item.get("open_price"),
                    "high": item.get("high_price"),
                    "low": item.get("low_price"),
                    "close": item.get("last_price"),
                    "volume": item.get("volume"),
                    "amount": item.get("turnover"),
                    "adj_factor": 1.0,
                    "limit_up": np.nan,
                    "limit_down": np.nan,
                    "is_paused": False,
                }
            )
        if snapshot_rows:
            price = pd.concat([price, pd.DataFrame(snapshot_rows)], ignore_index=True)

    price = price.sort_values(["code", "trade_date"]).drop_duplicates(["code", "trade_date"], keep="last")
    price["pre_close"] = price.groupby("code")["close"].shift(1)
    price["pre_close"] = price["pre_close"].fillna(price["close"])
    price = add_adjusted_prices(price)

    selected_rows = []
    for rank, item in enumerate(targets, start=1):
        code = item["ts_code"]
        selected_rows.append(
            {
                "code": code,
                "name": item.get("name", target_names.get(code, "")),
                "board": infer_board(code),
                "industry_level1": item.get("industry", ""),
                "industry_level2": "自上而下观察名单",
                "selection_rank": rank,
                "selection_score": SELECTED_COUNT + 1 - rank,
                "return_20260401_to_20260703": item.get("return_20260401_to_20260703"),
                "pct_chg_20260703": item.get("pct_chg_20260703"),
                "pe_ttm_snapshot": item.get("pe_ttm_snapshot"),
                "snapshot_turnover_yuan": item.get("snapshot_turnover_yuan"),
                "main_net_inflow_yuan": item.get("main_net_inflow_yuan"),
                "selection_reason": item.get("selection_reason", ""),
                "status": item.get("status", ""),
            }
        )
    selected = pd.DataFrame(selected_rows)

    calendar = pd.DataFrame({"trade_date": sorted(price["trade_date"].unique()), "is_open": True})
    return {
        "mode": "real_watchlist",
        "source_ref": price_path,
        "selected": selected,
        "price": price,
        "calendar": calendar,
        "report_context": {
            "data_source": (
                f"`{price_path.relative_to(ROOT_DIR)}`、`{snapshot_path.relative_to(ROOT_DIR)}`，"
                f"并使用真实自上而下名单 `{WATCHLIST_PATH.relative_to(ROOT_DIR)}`"
            ),
            "data_window_prefix": "Fuyao 真实行情缓存覆盖",
            "selection_scope": (
                "按自上而下流程先筛行业，再从 129 只去重成分股中剔除 ST/退市风险、低市值和低成交额标的，"
                "得到 75 只候选股，重点评分检查前 30 名，并用 Tushare 日线复核 10 只重点股票，最终保留 5 只观察标的。"
                "该结果是课程练习与研究样本，不构成投资建议。"
            ),
            "selection_explanation": (
                "本表中的 `selection_rank` 来自真实自上而下选股报告，核心依据是行业相对强度、个股成交活跃度、"
                "资金流、区间趋势和估值异常过滤。`selection_score` 仅用于绘图展示排名，不是回测因子得分。"
            ),
            "price_note": "本次真实行情来自 Fuyao 未复权日线缓存；技术指标直接基于未复权 OHLC 价格计算。",
            "price_panel_desc": "每张个股图包含四个面板：收盘价与布林带、RSI14、MACD、KDJ。",
        },
    }


def add_adjusted_prices(price: pd.DataFrame) -> pd.DataFrame:
    df = price.sort_values(["code", "trade_date"]).copy()
    if "adj_factor" not in df.columns or df["adj_factor"].isna().all():
        factor = pd.Series(1.0, index=df.index)
    else:
        latest_factor = df.groupby("code")["adj_factor"].transform("last")
        factor = (df["adj_factor"] / latest_factor).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    for col in ["open", "high", "low", "close", "pre_close"]:
        df[f"qfq_{col}"] = df[col] * factor
    return df


def compute_rsi(close: pd.Series, window: int = RSI_WINDOW) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / window, min_periods=window, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain > 0)), 100)
    rsi = rsi.where(~((avg_loss == 0) & (avg_gain == 0)), 50)
    return rsi


def smooth_kdj_line(values: pd.Series, seed: float = 50.0, alpha: float = 1 / KDJ_SMOOTH) -> pd.Series:
    result = []
    prev = seed
    for value in values:
        if pd.isna(value):
            result.append(np.nan)
            continue
        prev = (1 - alpha) * prev + alpha * value
        result.append(prev)
    return pd.Series(result, index=values.index)


def compute_indicators_one_stock(group: pd.DataFrame) -> pd.DataFrame:
    df = group.sort_values("trade_date").copy()
    close = df["qfq_close"]
    high = df["qfq_high"]
    low = df["qfq_low"]

    df["ret_1d"] = close.pct_change()
    df["rsi14"] = compute_rsi(close, RSI_WINDOW)

    df["ema12"] = close.ewm(span=MACD_FAST, min_periods=MACD_FAST, adjust=False).mean()
    df["ema26"] = close.ewm(span=MACD_SLOW, min_periods=MACD_SLOW, adjust=False).mean()
    df["macd_dif"] = df["ema12"] - df["ema26"]
    df["macd_dea"] = df["macd_dif"].ewm(span=MACD_SIGNAL, min_periods=MACD_SIGNAL, adjust=False).mean()
    df["macd_hist"] = df["macd_dif"] - df["macd_dea"]

    df["boll_mid"] = close.rolling(BOLL_WINDOW, min_periods=BOLL_WINDOW).mean()
    df["boll_std"] = close.rolling(BOLL_WINDOW, min_periods=BOLL_WINDOW).std(ddof=0)
    df["boll_upper"] = df["boll_mid"] + BOLL_STD * df["boll_std"]
    df["boll_lower"] = df["boll_mid"] - BOLL_STD * df["boll_std"]
    band_width = df["boll_upper"] - df["boll_lower"]
    df["boll_percent_b"] = (close - df["boll_lower"]) / band_width.replace(0, np.nan)
    df["boll_bandwidth"] = band_width / df["boll_mid"].replace(0, np.nan)

    lowest_low = low.rolling(KDJ_WINDOW, min_periods=KDJ_WINDOW).min()
    highest_high = high.rolling(KDJ_WINDOW, min_periods=KDJ_WINDOW).max()
    range_width = (highest_high - lowest_low).replace(0, np.nan)
    df["kdj_rsv9"] = 100 * (close - lowest_low) / range_width
    df["kdj_k"] = smooth_kdj_line(df["kdj_rsv9"])
    df["kdj_d"] = smooth_kdj_line(df["kdj_k"])
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df


def compute_all_indicators(price: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for _, group in price.groupby("code", sort=False):
        frames.append(compute_indicators_one_stock(group))
    return pd.concat(frames, ignore_index=True)


def classify_latest(row: pd.Series) -> dict[str, str]:
    rsi = row["rsi14"]
    hist = row["macd_hist"]
    pct_b = row["boll_percent_b"]
    k_value = row["kdj_k"]
    d_value = row["kdj_d"]
    j_value = row["kdj_j"]

    if pd.isna(rsi):
        rsi_note = "样本不足"
    elif rsi >= 70:
        rsi_note = "偏强/可能超买"
    elif rsi <= 30:
        rsi_note = "偏弱/可能超卖"
    else:
        rsi_note = "中性区间"

    if pd.isna(hist):
        macd_note = "样本不足"
    elif hist > 0:
        macd_note = "DIF在DEA上方，动量偏正"
    elif hist < 0:
        macd_note = "DIF在DEA下方，动量偏弱"
    else:
        macd_note = "DIF与DEA接近"

    if pd.isna(pct_b):
        boll_note = "样本不足"
    elif pct_b > 1:
        boll_note = "突破上轨"
    elif pct_b < 0:
        boll_note = "跌破下轨"
    elif pct_b >= 0.8:
        boll_note = "靠近上轨"
    elif pct_b <= 0.2:
        boll_note = "靠近下轨"
    else:
        boll_note = "位于通道中部"

    if pd.isna(k_value) or pd.isna(d_value) or pd.isna(j_value):
        kdj_note = "样本不足"
    elif j_value >= 100:
        kdj_note = "J值过高，短线偏热"
    elif j_value <= 0:
        kdj_note = "J值过低，短线偏冷"
    elif k_value > d_value:
        kdj_note = "K在D上方，短线动量偏强"
    else:
        kdj_note = "K在D下方，短线动量偏弱"

    return {
        "rsi_note": rsi_note,
        "macd_note": macd_note,
        "boll_note": boll_note,
        "kdj_note": kdj_note,
    }


def data_quality_summary(price: pd.DataFrame, calendar: pd.DataFrame, names: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    open_dates = set(calendar.loc[calendar["is_open"].astype(bool), "trade_date"].astype(str))
    all_numeric_price = ["open", "high", "low", "close", "pre_close"]
    raw_columns = [
        "code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "adj_factor",
        "limit_up",
        "limit_down",
        "is_paused",
        "qfq_open",
        "qfq_high",
        "qfq_low",
        "qfq_close",
        "qfq_pre_close",
    ]

    for code, group in price.groupby("code"):
        group = group.sort_values("trade_date")
        dates = set(group["trade_date"].astype(str))
        expected = {d for d in open_dates if group["trade_date"].min() <= d <= group["trade_date"].max()}
        ohlc_bad = (
            (group["high"] < group[["open", "close"]].max(axis=1))
            | (group["low"] > group[["open", "close"]].min(axis=1))
            | (group["high"] < group["low"])
            | (group[all_numeric_price] <= 0).any(axis=1)
        )
        latest_name = names.loc[names["code"] == code, "name"]
        summaries.append(
            {
                "code": code,
                "name": latest_name.iloc[0] if not latest_name.empty else "",
                "rows": len(group),
                "start_date": group["trade_date"].min(),
                "end_date": group["trade_date"].max(),
                "raw_missing_cells": int(group[raw_columns].isna().sum().sum()),
                "duplicate_code_date_rows": int(group.duplicated(["code", "trade_date"]).sum()),
                "missing_trade_dates": len(expected - dates),
                "ohlc_violation_rows": int(ohlc_bad.sum()),
                "nonpositive_price_rows": int((group[all_numeric_price] <= 0).any(axis=1).sum()),
                "negative_volume_rows": int((group["volume"] < 0).sum()),
                "negative_amount_rows": int((group["amount"] < 0).sum()),
                "paused_days": int(group["is_paused"].fillna(False).astype(bool).sum()),
                "extreme_abs_ret_gt_20pct_rows": int((group["ret_1d"].abs() > 0.20).sum()),
            }
        )

    return pd.DataFrame(summaries)


def df_to_markdown(df: pd.DataFrame, max_rows: int | None = None, float_digits: int = 4) -> str:
    view = df.copy()
    if max_rows is not None:
        view = view.head(max_rows)
    for col in view.columns:
        if pd.api.types.is_float_dtype(view[col]):
            view[col] = view[col].map(lambda x: "" if pd.isna(x) else f"{x:.{float_digits}f}")
        else:
            view[col] = view[col].map(lambda x: "" if pd.isna(x) else str(x))
    header = "| " + " | ".join(view.columns) + " |"
    sep = "| " + " | ".join(["---"] * len(view.columns)) + " |"
    rows = ["| " + " | ".join(row) + " |" for row in view.astype(str).values.tolist()]
    return "\n".join([header, sep, *rows])


def plot_factor_scores(selected: pd.DataFrame) -> Path:
    fig_path = FIG_DIR / "selected_factor_scores.png"
    fig, ax = plt.subplots(figsize=(10, 5))
    labels = selected["code"] + "\n" + selected["name"].fillna("")
    score_col = "factor_score" if "factor_score" in selected.columns else "selection_score"
    score_label = "factor_score" if score_col == "factor_score" else "selection score (rank display)"
    ax.bar(labels, selected[score_col], color="#4C78A8")
    ax.axhline(0, color="#444444", linewidth=0.8)
    ax.set_title("Top 5 Selected Targets")
    ax.set_ylabel(score_label)
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(fig_path, dpi=180)
    plt.close(fig)
    return fig_path


def plot_stock_indicators(indicators: pd.DataFrame, code: str, name: str) -> Path:
    df = indicators.loc[indicators["code"] == code].sort_values("trade_date").copy()
    df["date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d")
    fig_path = FIG_DIR / f"{code.replace('.', '_')}_indicators.png"

    fig, axes = plt.subplots(
        4,
        1,
        figsize=(14, 10),
        sharex=True,
        gridspec_kw={"height_ratios": [2.2, 1, 1.2, 1]},
    )
    fig.suptitle(f"{code} {name} Technical Indicators", fontsize=14)

    axes[0].plot(df["date"], df["qfq_close"], label="qfq_close", color="#1F77B4", linewidth=1.5)
    axes[0].plot(df["date"], df["boll_mid"], label="BOLL mid", color="#7F7F7F", linewidth=1)
    axes[0].plot(df["date"], df["boll_upper"], label="BOLL upper", color="#D62728", linewidth=1)
    axes[0].plot(df["date"], df["boll_lower"], label="BOLL lower", color="#2CA02C", linewidth=1)
    valid = df[["boll_lower", "boll_upper"]].notna().all(axis=1)
    axes[0].fill_between(
        df.loc[valid, "date"],
        df.loc[valid, "boll_lower"].to_numpy(dtype=float),
        df.loc[valid, "boll_upper"].to_numpy(dtype=float),
        color="#D9E8FB",
        alpha=0.45,
    )
    axes[0].set_ylabel("Price")
    axes[0].legend(loc="upper left", ncol=4, fontsize=8)
    axes[0].grid(alpha=0.25)

    axes[1].plot(df["date"], df["rsi14"], label="RSI14", color="#9467BD", linewidth=1.3)
    axes[1].axhline(70, color="#D62728", linestyle="--", linewidth=0.9)
    axes[1].axhline(30, color="#2CA02C", linestyle="--", linewidth=0.9)
    axes[1].set_ylim(0, 100)
    axes[1].set_ylabel("RSI")
    axes[1].grid(alpha=0.25)

    axes[2].plot(df["date"], df["macd_dif"], label="DIF", color="#1F77B4", linewidth=1.1)
    axes[2].plot(df["date"], df["macd_dea"], label="DEA", color="#FF7F0E", linewidth=1.1)
    hist_colors = np.where(df["macd_hist"].fillna(0) >= 0, "#D62728", "#2CA02C")
    axes[2].bar(df["date"], df["macd_hist"], label="Hist", color=hist_colors, alpha=0.55, width=1.0)
    axes[2].axhline(0, color="#444444", linewidth=0.8)
    axes[2].set_ylabel("MACD")
    axes[2].legend(loc="upper left", ncol=3, fontsize=8)
    axes[2].grid(alpha=0.25)

    axes[3].plot(df["date"], df["kdj_k"], label="K", color="#1F77B4", linewidth=1.1)
    axes[3].plot(df["date"], df["kdj_d"], label="D", color="#FF7F0E", linewidth=1.1)
    axes[3].plot(df["date"], df["kdj_j"], label="J", color="#8C564B", linewidth=1.0)
    axes[3].axhline(80, color="#D62728", linestyle="--", linewidth=0.9)
    axes[3].axhline(20, color="#2CA02C", linestyle="--", linewidth=0.9)
    axes[3].set_ylabel("KDJ")
    axes[3].legend(loc="upper left", ncol=3, fontsize=8)
    axes[3].set_xlabel("Date")
    axes[3].grid(alpha=0.25)

    fig.autofmt_xdate()
    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(fig_path, dpi=180)
    plt.close(fig)
    return fig_path


def build_report(
    source_ref: Path,
    selected: pd.DataFrame,
    quality: pd.DataFrame,
    desc_report: pd.DataFrame,
    latest_summary: pd.DataFrame,
    figure_paths: list[Path],
    context: dict[str, str],
) -> Path:
    report_path = TASK_DIR / "Task2_数据诊断与技术指标分析报告.md"
    source_md = "\n".join([f"- [{name}]({url})" for name, url in SOURCE_LINKS])
    figure_md = "\n".join([f"- `{path.relative_to(TASK_DIR)}`" for path in figure_paths])

    if "selection_rank" in selected.columns:
        selected_cols = [
            "code",
            "name",
            "board",
            "industry_level1",
            "selection_rank",
            "return_20260401_to_20260703",
            "pct_chg_20260703",
            "pe_ttm_snapshot",
            "snapshot_turnover_yuan",
            "main_net_inflow_yuan",
            "status",
        ]
    else:
        selected_cols = [
            "code",
            "name",
            "board",
            "industry_level1",
            "industry_level2",
            "factor_score",
            "ret_20d",
            "low_vol_20d",
            "liquidity_20d",
            "quality_roe",
            "cashflow_quality",
        ]
    selected_md = df_to_markdown(selected[selected_cols], float_digits=4)

    quality_cols = [
        "code",
        "name",
        "rows",
        "start_date",
        "end_date",
        "raw_missing_cells",
        "duplicate_code_date_rows",
        "missing_trade_dates",
        "ohlc_violation_rows",
        "paused_days",
        "extreme_abs_ret_gt_20pct_rows",
    ]
    quality_md = df_to_markdown(quality[quality_cols], float_digits=2)

    desc_cols = [
        "code",
        "name",
        "close_mean",
        "close_std",
        "close_min",
        "close_max",
        "volume_mean",
        "amount_mean",
        "ret_1d_mean",
        "ret_1d_std",
    ]
    desc_md = df_to_markdown(desc_report[desc_cols], float_digits=4)

    latest_cols = [
        "code",
        "name",
        "trade_date",
        "qfq_close",
        "rsi14",
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "boll_percent_b",
        "boll_bandwidth",
        "kdj_rsv9",
        "kdj_k",
        "kdj_d",
        "kdj_j",
        "rsi_note",
        "macd_note",
        "boll_note",
        "kdj_note",
    ]
    latest_md = df_to_markdown(latest_summary[latest_cols], float_digits=4)
    duplicate_rows = int(quality["duplicate_code_date_rows"].sum())
    missing_dates = int(quality["missing_trade_dates"].sum())
    ohlc_bad = int(quality["ohlc_violation_rows"].sum())
    paused_days = int(quality["paused_days"].sum())
    extreme_rows = int(quality["extreme_abs_ret_gt_20pct_rows"].sum())
    quality_notes = [
        f"- 五个标的在样本窗口内共有 {int(quality['rows'].sum())} 行日线记录，未发现同一股票同一交易日重复行。" if duplicate_rows == 0 else f"- 发现 {duplicate_rows} 行同一股票同一交易日重复记录，已在诊断表中列出。",
        f"- 与本次可用交易日历对齐后，缺失交易日合计 {missing_dates} 个。",
        "- OHLC 逻辑、非正价格、负成交量、负成交额检查均未发现异常。" if ohlc_bad == 0 else f"- OHLC 或价格逻辑异常合计 {ohlc_bad} 行，需要回查原始行情。",
        f"- 停牌日合计 {paused_days} 个；本次 Fuyao 快照未提供逐日停牌标记，实盘仍需按 T+1 风控重新检查停牌和涨跌停状态。",
        f"- `extreme_abs_ret_gt_20pct_rows` 合计 {extreme_rows} 行；若出现极端跳变，应结合涨跌停制度、复权事件和公告事件复核。",
        f"- {context.get('price_note', '本工作流约定：技术指标与收益使用前复权 `qfq_*` 价格，模拟成交应使用未复权价格。')}",
    ]
    quality_notes_md = "\n".join(quality_notes)

    report = f"""# Task 2 数据诊断与技术指标分析报告

生成时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 0. 任务口径

- 工作流：`quant_a_share_daily` 本地日频 A 股量化工作流。
- 数据源：{context.get("data_source", f"`{source_ref.relative_to(ROOT_DIR)}`")}。
- 数据窗口：{context.get("data_window_prefix", "本地样本覆盖")} `{quality["start_date"].min()}` 至 `{quality["end_date"].max()}`，共 {int(quality["rows"].sum())} 行五标的日线记录。
- 选股口径：{context.get("selection_scope", f"按最新信号日的 `factor_score` 从高到低选出前 {SELECTED_COUNT} 个标的，并保留 A 股工作流中的风险边界。该结果是课程练习与研究样本，不构成投资建议。")}

## 1. 五个高潜力标的

{selected_md}

简要解释：{context.get("selection_explanation", "`factor_score` 是工作流把 20 日反转、20 日低波动、流动性、质量、估值/现金流等维度合成后的截面得分。本次只在本地样本池内排序，因此不能外推为全市场结论。")}

## 2. 数据基础诊断

### 2.1 数据质量检查

{quality_md}

诊断结论：

{quality_notes_md}

### 2.2 描述性统计

{desc_md}

完整诊断文件已保存为：

- `data/selected_targets.csv`
- `data/missing_summary.csv`
- `data/indicator_missing_summary.csv`
- `data/descriptive_stats.csv`
- `data/data_quality_summary.csv`

## 3. RSI、MACD、布林带的计算方法与作用

资料来源主要来自公开搜索结果，并结合量化建模口径整理：

{source_md}

### 3.1 RSI

RSI（Relative Strength Index）衡量一段时间内上涨幅度与下跌幅度的相对强弱。常用参数为 14 日。

计算方法：

```text
delta_t = close_t - close_(t-1)
gain_t = max(delta_t, 0)
loss_t = max(-delta_t, 0)
RS_t = AvgGain_t / AvgLoss_t
RSI_t = 100 - 100 / (1 + RS_t)
```

本脚本使用 Wilder 风格的指数平滑，`alpha = 1 / 14`。常见解释是 RSI 高于 70 表示短期偏热或可能超买，低于 30 表示短期偏弱或可能超卖；强趋势中 RSI 可能长期维持高位或低位，因此不能单独作为买卖依据。

### 3.2 MACD

MACD（Moving Average Convergence Divergence）用于刻画短期均线与长期均线的收敛/发散关系，常见参数为 12、26、9。

计算方法：

```text
EMA12 = close 的 12 日指数移动平均
EMA26 = close 的 26 日指数移动平均
DIF = EMA12 - EMA26
DEA = DIF 的 9 日指数移动平均
MACD Histogram = DIF - DEA
```

作用：当 DIF 上穿 DEA 且柱状图转正时，通常表示短期动量改善；当 DIF 下穿 DEA 且柱状图转负时，通常表示动量转弱。MACD 属于滞后型趋势/动量指标，震荡市容易出现假信号。

### 3.3 布林带 Bollinger Bands

布林带用滚动均值和滚动标准差描述价格相对位置与波动区间。常用参数为 20 日均线和 2 倍标准差。

计算方法：

```text
Middle_t = SMA(close, 20)
Std_t = rolling_std(close, 20)
Upper_t = Middle_t + 2 * Std_t
Lower_t = Middle_t - 2 * Std_t
%B_t = (close_t - Lower_t) / (Upper_t - Lower_t)
Bandwidth_t = (Upper_t - Lower_t) / Middle_t
```

作用：价格靠近上轨通常代表短期强势或过热，靠近下轨通常代表短期弱势或超跌；带宽扩大代表波动上升，带宽收缩代表波动压缩。突破上下轨不必然意味着反转，需要配合趋势、成交量或其他指标确认。

## 4. 扩展指标：KDJ

除 RSI、MACD、布林带外，典型技术指标还包括 MA/EMA、KDJ/Stochastic、OBV、ADX/DMI、CCI、ROC、Williams %R、MFI、成交量均线、量比、换手率等。

本次选取 KDJ 扩展计算。KDJ 是随机指标（Stochastic Oscillator）在 A 股教学和行情软件中常见的三线版本，用来衡量收盘价在最近高低价区间中的位置，并通过 K、D、J 三条线观察短线动量变化。

计算方法：

```text
RSV_t = (close_t - lowest_low_9) / (highest_high_9 - lowest_low_9) * 100
K_t = 2/3 * K_(t-1) + 1/3 * RSV_t
D_t = 2/3 * D_(t-1) + 1/3 * K_t
J_t = 3 * K_t - 2 * D_t
```

作用：K、D 高于 80 通常表示短线偏热，低于 20 通常表示短线偏冷；K 上穿 D 常被视为短线动量改善，K 下穿 D 常被视为动量转弱。J 线放大 K 与 D 的差异，反应更灵敏，也更容易出现噪声。

## 5. 指标最新值

{latest_md}

完整指标序列已保存为 `data/indicator_values.csv`，最新截面已保存为 `data/latest_indicator_summary.csv`。

## 6. 可视化输出

{figure_md}

{context.get("price_panel_desc", "每张个股图包含四个面板：前复权收盘价与布林带、RSI14、MACD、KDJ。")}

## 7. 使用说明

复跑命令：

```bash
python3 "量化交易课程/Lecture 2/Task 2/analyze_task2_indicators.py"
```

注意：如果本地 pandas 在导入时输出 NumPy 2.x 与可选二进制包不兼容的提示，本脚本会把相关 stderr 捕获到 `data/import_warnings.txt`。这些提示来自 `pyarrow/numexpr/bottleneck/scipy` 等可选依赖，不影响本次 pickle 数据读取、指标计算和图表生成。
"""
    report_path.write_text(report, encoding="utf-8")
    return report_path


def main() -> None:
    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS",
        "Heiti TC",
        "Songti SC",
        "SimHei",
        "Noto Sans CJK SC",
        "DejaVu Sans",
    ]
    plt.rcParams["axes.unicode_minus"] = False

    if IMPORT_WARNINGS.strip():
        (OUT_DATA_DIR / "import_warnings.txt").write_text(IMPORT_WARNINGS, encoding="utf-8")

    real_context = load_real_watchlist_context()
    if real_context is not None:
        source_ref = real_context["source_ref"]
        selected = real_context["selected"].copy()
        selected_codes = selected["code"].tolist()
        calendar = real_context["calendar"]
        selected_price_raw = real_context["price"].copy()
        report_context = real_context["report_context"]
    else:
        source_ref = latest_signal_file()
        signal = pd.read_csv(source_ref)
        signal = signal.sort_values("factor_score", ascending=False).reset_index(drop=True)
        selected = signal.head(SELECTED_COUNT).copy()
        selected_codes = selected["code"].tolist()

        price = add_adjusted_prices(load_processed_table("daily_price"))
        calendar = load_processed_table("trading_calendar")
        stock_status = load_processed_table("stock_status")
        latest_names = (
            stock_status.sort_values(["code", "trade_date"])
            .groupby("code", as_index=False)
            .tail(1)[["code", "name", "board"]]
        )

        selected_price_raw = price.loc[price["code"].isin(selected_codes)].copy()
        selected = selected.merge(latest_names, on=["code", "name", "board"], how="left")
        report_context = {
            "data_source": (
                "`quant_a_share_daily/data/processed/daily_price.pkl`、`stock_status.pkl`、"
                f"`trading_calendar.pkl`，并使用最新信号文件 `{source_ref.relative_to(ROOT_DIR)}`"
            ),
        }

    selected_price = compute_all_indicators(selected_price_raw)

    raw_missing_fields = [
        "code",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "pre_close",
        "volume",
        "amount",
        "adj_factor",
        "limit_up",
        "limit_down",
        "is_paused",
        "qfq_open",
        "qfq_high",
        "qfq_low",
        "qfq_close",
        "qfq_pre_close",
    ]
    missing_summary = (
        selected_price_raw[raw_missing_fields]
        .groupby("code")
        .apply(lambda x: x.isna().sum(), include_groups=False)
        .reset_index()
        .melt(id_vars="code", var_name="field", value_name="missing_count")
    )
    missing_summary["missing_pct"] = missing_summary["missing_count"] / selected_price_raw.groupby(
        "code"
    ).size().reindex(missing_summary["code"]).to_numpy()

    indicator_fields = [
        "ret_1d",
        "rsi14",
        "ema12",
        "ema26",
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "boll_mid",
        "boll_std",
        "boll_upper",
        "boll_lower",
        "boll_percent_b",
        "boll_bandwidth",
        "kdj_rsv9",
        "kdj_k",
        "kdj_d",
        "kdj_j",
    ]
    indicator_missing_summary = (
        selected_price[["code", *indicator_fields]]
        .groupby("code")
        .apply(lambda x: x.isna().sum(), include_groups=False)
        .reset_index()
        .melt(id_vars="code", var_name="field", value_name="missing_count")
    )
    indicator_missing_summary["missing_pct"] = indicator_missing_summary["missing_count"] / selected_price.groupby(
        "code"
    ).size().reindex(indicator_missing_summary["code"]).to_numpy()

    desc_stats = (
        selected_price.groupby("code")[
            ["open", "high", "low", "close", "volume", "amount", "qfq_close", "ret_1d"]
        ]
        .describe()
        .reset_index()
    )
    desc_stats.columns = ["_".join([str(x) for x in col if x]) for col in desc_stats.columns.to_flat_index()]

    desc_report = (
        selected_price.groupby("code")
        .agg(
            close_mean=("close", "mean"),
            close_std=("close", "std"),
            close_min=("close", "min"),
            close_max=("close", "max"),
            volume_mean=("volume", "mean"),
            amount_mean=("amount", "mean"),
            ret_1d_mean=("ret_1d", "mean"),
            ret_1d_std=("ret_1d", "std"),
        )
        .reset_index()
        .merge(selected[["code", "name"]], on="code", how="left")
    )
    desc_report = desc_report[["code", "name", *[c for c in desc_report.columns if c not in ["code", "name"]]]]

    quality = data_quality_summary(selected_price, calendar, selected[["code", "name"]])

    latest_rows = selected_price.sort_values("trade_date").groupby("code", as_index=False).tail(1)
    latest_summary = latest_rows.merge(selected[["code", "name"]], on="code", how="left")
    notes = latest_summary.apply(classify_latest, axis=1, result_type="expand")
    latest_summary = pd.concat([latest_summary.reset_index(drop=True), notes.reset_index(drop=True)], axis=1)
    latest_summary = latest_summary.sort_values("code")

    selected.to_csv(OUT_DATA_DIR / "selected_targets.csv", index=False, encoding="utf-8-sig")
    missing_summary.to_csv(OUT_DATA_DIR / "missing_summary.csv", index=False, encoding="utf-8-sig")
    indicator_missing_summary.to_csv(OUT_DATA_DIR / "indicator_missing_summary.csv", index=False, encoding="utf-8-sig")
    desc_stats.to_csv(OUT_DATA_DIR / "descriptive_stats.csv", index=False, encoding="utf-8-sig")
    desc_report.to_csv(OUT_DATA_DIR / "descriptive_stats_compact.csv", index=False, encoding="utf-8-sig")
    quality.to_csv(OUT_DATA_DIR / "data_quality_summary.csv", index=False, encoding="utf-8-sig")
    selected_price.to_csv(OUT_DATA_DIR / "indicator_values.csv", index=False, encoding="utf-8-sig")
    latest_summary.to_csv(OUT_DATA_DIR / "latest_indicator_summary.csv", index=False, encoding="utf-8-sig")

    figure_paths = [plot_factor_scores(selected)]
    for _, row in selected[["code", "name"]].iterrows():
        figure_paths.append(plot_stock_indicators(selected_price, row["code"], row["name"]))

    report_path = build_report(source_ref, selected, quality, desc_report, latest_summary, figure_paths, report_context)

    print(f"Selected targets: {', '.join(selected_codes)}")
    print(f"Report: {report_path}")
    print(f"Data dir: {OUT_DATA_DIR}")
    print(f"Figures dir: {FIG_DIR}")


if __name__ == "__main__":
    main()
