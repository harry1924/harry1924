"""把 data/chart_data.json 注入 report_template.html，并按章节标题与图表标题生成目录，输出 report.html。"""
import html
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
with open(os.path.join(ROOT, "report_template.html")) as f:
    page = f.read()
with open(os.path.join(ROOT, "data", "chart_data.json")) as f:
    chart = json.load(f)
with open(os.path.join(ROOT, "data", "senate_sim.json")) as f:
    chart["senate"] = json.load(f)
data = json.dumps(chart, ensure_ascii=False, separators=(",", ":"))
assert "/*__DATA__*/null" in page and "<!--TOC-->" in page

# 给摘要与数据说明的标题补上锚点
page = page.replace("<h2>摘要</h2>", '<h2 id="abstract-h">摘要</h2>')
page = page.replace("<h2>数据与方法说明</h2>", '<h2 id="notes-h">数据与方法说明</h2>')

# 图表按出现顺序自动编号并补上锚点
counter = iter(range(1, 1000))


def tag_fig(m):
    n = next(counter)
    return f'{m.group(1)} id="fig-{n}">图表{n}'


page = re.sub(r'(<p class="ft"|<caption)>图表#', tag_fig, page)

heads = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', page)
figs = re.findall(r'id="fig-(\d+)">(图表\d+：.*?)</(?:p|caption)>', page)


def item(cls, anchor, text):
    return f'<li class="{cls}"><a href="#{anchor}">{html.escape(html.unescape(re.sub(r"<[^>]+>", "", text)))}</a></li>'


toc = ['<nav class="toc-block" aria-label="目录">',
       '<div class="toc-card"><h2>目录</h2><ol>']
toc += [item(f"l{lvl}", anchor, text) for lvl, anchor, text in heads]
toc += ['</ol></div>', '<div class="toc-card"><h2>图表目录</h2><ol>']
toc += [item("fig", f"fig-{n}", text) for n, text in figs]
toc += ['</ol></div>', '</nav>']
page = page.replace("<!--TOC-->", "\n".join(toc))

with open(os.path.join(ROOT, "report.html"), "w") as f:
    f.write(page.replace("/*__DATA__*/null", data))
print(f"report.html written: {len(heads)} headings, {len(figs)} figures")
