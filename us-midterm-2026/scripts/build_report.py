"""把 data/chart_data.json 注入 report_template.html，生成 report.html。"""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
with open(os.path.join(ROOT, "report_template.html")) as f:
    html = f.read()
with open(os.path.join(ROOT, "data", "chart_data.json")) as f:
    data = f.read()
assert "/*__DATA__*/null" in html
with open(os.path.join(ROOT, "report.html"), "w") as f:
    f.write(html.replace("/*__DATA__*/null", data))
print("report.html written")
