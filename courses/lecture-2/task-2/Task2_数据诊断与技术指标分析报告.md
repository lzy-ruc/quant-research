# Task 2 数据诊断与技术指标分析报告

生成时间：2026-07-04 15:22:34

## 0. 任务口径

- 工作流：`quant_a_share_daily` 本地日频 A 股量化工作流。
- 数据源：`quant_a_share_daily/data/raw/fuyao/price_historical.json`、`quant_a_share_daily/data/raw/fuyao/price_snapshot.json`，并使用真实自上而下名单 `量化交易课程/Lecture 2/Task 2/data/real_top_down_watchlist.json`。
- 数据窗口：Fuyao 真实行情缓存覆盖 `20250102` 至 `20260703`，共 1810 行五标的日线记录。
- 选股口径：按自上而下流程先筛行业，再从 129 只去重成分股中剔除 ST/退市风险、低市值和低成交额标的，得到 75 只候选股，重点评分检查前 30 名，并用 Tushare 日线复核 10 只重点股票，最终保留 5 只观察标的。该结果是课程练习与研究样本，不构成投资建议。

## 1. 五个高潜力标的

| code | name | board | industry_level1 | selection_rank | return_20260401_to_20260703 | pct_chg_20260703 | pe_ttm_snapshot | snapshot_turnover_yuan | main_net_inflow_yuan | status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 603466.SH | 风语筑 | Main | 其他数字媒体 | 1 | 0.2399 | 0.1003 | 40.5900 | 1014371456.0000 | 110214909.0000 | Watch after limit-up; wait for turnover and pullback confirmation. |
| 002747.SZ | 埃斯顿 | Main | 机器人 | 2 | 1.2111 | 0.1000 | 110.7200 | 5508068594.2300 | 401870432.0000 | Core momentum name; avoid chasing and wait for post-divergence support. |
| 002979.SZ | 雷赛智能 | Main | 机器人 | 3 | 0.9055 | 0.1000 | 76.1800 | 383958077.7500 | 60341927.0000 | Trend candidate; watch pullback that holds the short-term platform. |
| 603416.SH | 信捷电气 | Main | 机器人 | 4 | 0.2422 | 0.0169 | 43.9400 | 628563247.0000 | 48374822.0000 | Relatively balanced watchlist member; monitor follow-through and industry beta. |
| 300607.SZ | 拓斯达 | ChiNext | 机器人 | 5 | 1.0591 | 0.1355 | 131.3400 | 4594583901.9400 | 131914320.0000 | High-volatility candidate; wait for second confirmation and use strict risk control. |

简要解释：本表中的 `selection_rank` 来自真实自上而下选股报告，核心依据是行业相对强度、个股成交活跃度、资金流、区间趋势和估值异常过滤。`selection_score` 仅用于绘图展示排名，不是回测因子得分。

## 2. 数据基础诊断

### 2.1 数据质量检查

| code | name | rows | start_date | end_date | raw_missing_cells | duplicate_code_date_rows | missing_trade_dates | ohlc_violation_rows | paused_days | extreme_abs_ret_gt_20pct_rows |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 002747.SZ | 埃斯顿 | 362 | 20250102 | 20260703 | 724 | 0 | 0 | 0 | 0 | 0 |
| 002979.SZ | 雷赛智能 | 362 | 20250102 | 20260703 | 724 | 0 | 0 | 0 | 0 | 0 |
| 300607.SZ | 拓斯达 | 362 | 20250102 | 20260703 | 724 | 0 | 0 | 0 | 0 | 3 |
| 603416.SH | 信捷电气 | 362 | 20250102 | 20260703 | 724 | 0 | 0 | 0 | 0 | 0 |
| 603466.SH | 风语筑 | 362 | 20250102 | 20260703 | 724 | 0 | 0 | 0 | 0 | 0 |

诊断结论：

- 五个标的在样本窗口内共有 1810 行日线记录，未发现同一股票同一交易日重复行。
- 与本次可用交易日历对齐后，缺失交易日合计 0 个。
- OHLC 逻辑、非正价格、负成交量、负成交额检查均未发现异常。
- 停牌日合计 0 个；本次 Fuyao 快照未提供逐日停牌标记，实盘仍需按 T+1 风控重新检查停牌和涨跌停状态。
- `extreme_abs_ret_gt_20pct_rows` 合计 3 行；若出现极端跳变，应结合涨跌停制度、复权事件和公告事件复核。
- 本次真实行情来自 Fuyao 未复权日线缓存；技术指标直接基于未复权 OHLC 价格计算。

### 2.2 描述性统计

| code | name | close_mean | close_std | close_min | close_max | volume_mean | amount_mean | ret_1d_mean | ret_1d_std |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 002747.SZ | 埃斯顿 | 23.0533 | 4.0525 | 16.6200 | 44.7700 | 35730818.3978 | 904889445.9294 | 0.0030 | 0.0301 |
| 002979.SZ | 雷赛智能 | 44.3669 | 6.4811 | 27.4900 | 69.5500 | 11857971.7376 | 552952371.5181 | 0.0028 | 0.0312 |
| 300607.SZ | 拓斯达 | 32.3374 | 3.9834 | 23.0800 | 52.9600 | 30750450.4807 | 1045699398.1526 | 0.0024 | 0.0384 |
| 603416.SH | 信捷电气 | 55.2751 | 5.4569 | 38.7600 | 67.7600 | 3307054.0276 | 187277151.2231 | 0.0016 | 0.0311 |
| 603466.SH | 风语筑 | 9.9983 | 0.7903 | 8.0400 | 12.9700 | 29482509.6215 | 308890653.6506 | 0.0012 | 0.0312 |

完整诊断文件已保存为：

- `data/selected_targets.csv`
- `data/missing_summary.csv`
- `data/indicator_missing_summary.csv`
- `data/descriptive_stats.csv`
- `data/data_quality_summary.csv`

## 3. RSI、MACD、布林带的计算方法与作用

资料来源主要来自公开搜索结果，并结合量化建模口径整理：

- [Investopedia - RSI](https://www.investopedia.com/terms/r/rsi.asp)
- [Investopedia - MACD](https://www.investopedia.com/terms/m/macd.asp)
- [Investopedia - Bollinger Bands](https://www.investopedia.com/trading/using-bollinger-bands-to-gauge-trends/)
- [Investopedia - Stochastic Oscillator](https://www.investopedia.com/articles/technical/073001.asp)

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

| code | name | trade_date | qfq_close | rsi14 | macd_dif | macd_dea | macd_hist | boll_percent_b | boll_bandwidth | kdj_rsv9 | kdj_k | kdj_d | kdj_j | rsi_note | macd_note | boll_note | kdj_note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 002747.SZ | 埃斯顿 | 20260703 | 44.7700 | 73.5222 | 3.2147 | 2.7249 | 0.4897 | 1.1578 | 0.3618 | 100.0000 | 80.9915 | 69.2958 | 104.3827 | 偏强/可能超买 | DIF在DEA上方，动量偏正 | 突破上轨 | J值过高，短线偏热 |
| 002979.SZ | 雷赛智能 | 20260703 | 69.5500 | 76.4731 | 2.2157 | 0.8609 | 1.3548 | 1.3411 | 0.3179 | 100.0000 | 86.3624 | 71.7274 | 115.6324 | 偏强/可能超买 | DIF在DEA上方，动量偏正 | 突破上轨 | J值过高，短线偏热 |
| 300607.SZ | 拓斯达 | 20260703 | 52.9600 | 75.8482 | 3.9483 | 2.6244 | 1.3239 | 1.1678 | 0.5441 | 89.4263 | 85.9790 | 83.8994 | 90.1383 | 偏强/可能超买 | DIF在DEA上方，动量偏正 | 突破上轨 | K在D上方，短线动量偏强 |
| 603416.SH | 信捷电气 | 20260703 | 60.8800 | 62.3349 | -0.1515 | -0.8286 | 0.6771 | 0.9963 | 0.2018 | 88.7837 | 71.5094 | 52.4809 | 109.5662 | 中性区间 | DIF在DEA上方，动量偏正 | 靠近上轨 | J值过高，短线偏热 |
| 603466.SH | 风语筑 | 20260703 | 11.6300 | 59.0802 | -0.0483 | -0.0697 | 0.0213 | 0.7586 | 0.2891 | 100.0000 | 65.1365 | 48.5930 | 98.2234 | 中性区间 | DIF在DEA上方，动量偏正 | 位于通道中部 | K在D上方，短线动量偏强 |

完整指标序列已保存为 `data/indicator_values.csv`，最新截面已保存为 `data/latest_indicator_summary.csv`。

## 6. 可视化输出

- `figures/selected_factor_scores.png`
- `figures/603466_SH_indicators.png`
- `figures/002747_SZ_indicators.png`
- `figures/002979_SZ_indicators.png`
- `figures/603416_SH_indicators.png`
- `figures/300607_SZ_indicators.png`

每张个股图包含四个面板：收盘价与布林带、RSI14、MACD、KDJ。

## 7. 使用说明

复跑命令：

```bash
python3 "量化交易课程/Lecture 2/Task 2/analyze_task2_indicators.py"
```

注意：如果本地 pandas 在导入时输出 NumPy 2.x 与可选二进制包不兼容的提示，本脚本会把相关 stderr 捕获到 `data/import_warnings.txt`。这些提示来自 `pyarrow/numexpr/bottleneck/scipy` 等可选依赖，不影响本次 pickle 数据读取、指标计算和图表生成。
