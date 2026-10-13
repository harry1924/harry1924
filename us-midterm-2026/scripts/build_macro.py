"""把 data/macro_long.json 注入 macro_template.html，沿用主报告样式，生成 macro.html。"""
import html
import json
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
page = open(os.path.join(ROOT, "macro_template.html")).read()
style = re.search(r"<style>.*?</style>", open(os.path.join(ROOT, "report_template.html")).read(), re.S).group(0)
data = json.dumps(json.load(open(os.path.join(ROOT, "data", "macro_long.json"))), ensure_ascii=False, separators=(",", ":"))
page = page.replace("/*__STYLE__*/", style).replace("<h2>摘要</h2>", '<h2 id="abstract-h">摘要</h2>')
page = page.replace("<h2>数据与方法说明</h2>", '<h2 id="notes-h">数据与方法说明</h2>')
counter = iter(range(1, 1000))
page = re.sub(r'(<p class="ft"|<caption)>图表#', lambda m: f'{m.group(1)} id="fig-{(n := next(counter))}">图表{n}', page)
heads = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', page)
figs = re.findall(r'id="fig-(\d+)">(图表\d+：.*?)</(?:p|caption)>', page)
esc = lambda x: html.escape(html.unescape(re.sub(r"<[^>]+>", "", x)))
toc = ['<nav class="toc-block" aria-label="目录">', '<div class="toc-card"><h2>目录</h2><ol>']
toc += [f'<li class="l{l}"><a href="#{a}">{esc(t)}</a></li>' for l, a, t in heads]
toc += ['</ol></div>', '<div class="toc-card"><h2>图表目录</h2><ol>']
toc += [f'<li class="fig"><a href="#fig-{n}">{esc(t)}</a></li>' for n, t in figs]
toc += ['</ol></div>', '</nav>']
page = page.replace("<!--TOC-->", "\n".join(toc)).replace("/*__DATA__*/null", data)
open(os.path.join(ROOT, "macro.html"), "w").write(page)
print(f"macro.html written: {len(heads)} headings, {len(figs)} figures")
