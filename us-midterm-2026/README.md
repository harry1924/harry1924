# 中期选举前后，大类资产如何定价？

"2026美国中期选举"专题报告（2026 年 9 月 25 日）。

- **报告正文**：`report.html`（深度报告，含目录与 16 张图表，浏览器直接打开）
- **模板**：`report_template.html`，数据由 `scripts/build_report.py` 注入
- **数据**：`data/`，FRED、Yahoo Finance、datasets/gold-prices 原始数据及统计结果
- **脚本**：
  - `scripts/midterm_windows.py`：1946—2022 年 20 次中选的窗口统计（`--fetch` 重新下载数据）
  - `scripts/build_chart_data.py`：平均路径、2026 对比路径、赤字率、置换检验，输出 `data/chart_data.json`
  - `scripts/build_report.py`：生成 `report.html`

复算：

```
python3 scripts/midterm_windows.py --fetch
cd scripts && python3 build_chart_data.py && python3 build_report.py
```
