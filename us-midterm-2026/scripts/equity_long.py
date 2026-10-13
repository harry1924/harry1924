"""美股长样本专题：1926—2022 年全部 25 次中期选举，统一使用 Ken French 数据库（基于 CRSP）日度收益。

用法：
    python3 scripts/equity_long.py --fetch   # 下载 Ken French 日度数据到 data/ff/
    python3 scripts/equity_long.py           # 计算并输出 data/equity_long.json

所有指标均为市值加权、含股息的日度收益，1926 年 7 月 1 日起，样本期完全一致。
窗口以选举日（或其前最近一个交易日；1984 年以前选举日休市）为 T，偏移为交易日：
T-21→T（选前一个月）、T→T+1（选举次日）、T→T+21（选后一个月）、T→T+42（选后两个月）。
1952 年以前纽交所周六开市，同样交易日数对应的日历天数略短。
"""
import argparse
import bisect
import io
import json
import os
import random
import statistics as st
import urllib.request
import zipfile
import datetime as dt

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FF_DIR = os.path.join(ROOT, "data", "ff")
BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {
    "factors": ("F-F_Research_Data_Factors_daily_CSV.zip", ",Mkt-RF"),
    "size": ("Portfolios_Formed_on_ME_daily_CSV.zip", ",<= 0"),
    "value": ("Portfolios_Formed_on_BE-ME_daily_CSV.zip", ",<= 0"),
    "ind": ("49_Industry_Portfolios_daily_CSV.zip", ",Agric"),
}
# 指标：(代码, 中文名, 来源文件, 列名)；MKT 为 Mkt-RF + RF
INDICATORS = [
    ("MKT", "全市场", "factors", None),
    ("BIG", "大盘股（市值前 30%）", "size", "Hi 30"),
    ("SMALL", "小盘股（市值后 30%）", "size", "Lo 30"),
    ("VALUE", "价值股（账面市值比前 30%）", "value", "Hi 30"),
    ("GROWTH", "成长股（账面市值比后 30%）", "value", "Lo 30"),
    ("SMB", "小盘相对大盘（规模因子）", "factors", "SMB"),
    ("HML", "价值相对成长（价值因子）", "factors", "HML"),
    ("Banks", "银行", "ind", "Banks"),
    ("Oil", "石油天然气", "ind", "Oil"),
    ("Drugs", "医药", "ind", "Drugs"),
    ("Util", "公用事业", "ind", "Util"),
    ("Aero", "航空航天（国防代理）", "ind", "Aero"),
    ("Chips", "电子设备（科技代理）", "ind", "Chips"),
    ("Rtail", "零售", "ind", "Rtail"),
]

# 1926—2022 年中期选举日及两层分类
ELECTIONS = {
    "1926-11-02": ("统一保持", "两院皆保"), "1930-11-04": ("统一保持", "两院皆保"),
    "1934-11-06": ("统一保持", "两院皆保"), "1938-11-08": ("统一保持", "两院皆保"),
    "1942-11-03": ("统一保持", "两院皆保"), "1946-11-05": ("统一→分治", "两院皆失"),
    "1950-11-07": ("统一保持", "两院皆保"), "1954-11-02": ("统一→分治", "两院皆失"),
    "1958-11-04": ("分治保持", ""), "1962-11-06": ("统一保持", "两院皆保"),
    "1966-11-08": ("统一保持", "两院皆保"), "1970-11-03": ("分治保持", ""),
    "1974-11-05": ("分治保持", ""), "1978-11-07": ("统一保持", "两院皆保"),
    "1982-11-02": ("分治保持", ""), "1986-11-04": ("分治保持", ""),
    "1990-11-06": ("分治保持", ""), "1994-11-08": ("统一→分治", "两院皆失"),
    "1998-11-03": ("分治保持", ""), "2002-11-05": ("分治→统一", ""),
    "2006-11-07": ("统一→分治", "两院皆失"), "2010-11-02": ("统一→分治", "只丢众议院"),
    "2014-11-04": ("分治保持", ""), "2018-11-06": ("统一→分治", "只丢众议院"),
    "2022-11-08": ("统一→分治", "只丢众议院"),
}
PREWAR = {"1926", "1930", "1934", "1938", "1942"}
SPAN = range(-63, 64)
COLS = {"pre_1m": (-21, 0), "day_after": (0, 1), "post_1m": (0, 21), "post_2m": (0, 42)}


def fetch():
    os.makedirs(FF_DIR, exist_ok=True)
    for name, _ in FILES.values():
        req = urllib.request.Request(BASE + name, headers={"User-Agent": "Mozilla/5.0"})
        with open(os.path.join(FF_DIR, name), "wb") as f:
            f.write(urllib.request.urlopen(req).read())


def read_table(key):
    """读取文件中第一个表格（市值加权），返回 {日期: {列: 日收益%}}。"""
    name, prefix = FILES[key]
    z = zipfile.ZipFile(os.path.join(FF_DIR, name))
    lines = z.read(z.namelist()[0]).decode("latin1").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith(prefix))
    cols = [c.strip() for c in lines[start].split(",")[1:]]
    out = {}
    for l in lines[start + 1:]:
        parts = l.split(",")
        if len(parts) < 2 or not parts[0].strip().isdigit():
            break
        d = parts[0].strip()
        out[dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))] = {c: float(v) for c, v in zip(cols, parts[1:])}
    return out


def build_levels():
    """把日收益累乘为指数（起点 100）。"""
    tables = {k: read_table(k) for k in FILES}
    days = sorted(tables["factors"])
    levels = {}
    for code, _, src, col in INDICATORS:
        lv, s = 100.0, {}
        for d in days:
            row = tables[src].get(d)
            if row is None:
                continue
            r = row["Mkt-RF"] + row["RF"] if code == "MKT" else row[col]
            if r <= -99:
                continue
            lv *= 1 + r / 100
            s[d] = lv
        levels[code] = s
    return levels


def window(s, keys, day, a, b):
    i = bisect.bisect_right(keys, day) - 1
    if i + a < 0 or i + b >= len(keys):
        return None
    return round((s[keys[i + b]] / s[keys[i + a]] - 1) * 100, 2)


def path(s, keys, day):
    i = bisect.bisect_right(keys, day) - 1
    if i + SPAN[0] < 0 or i + SPAN[-1] >= len(keys):
        return None
    base = s[keys[i]]
    return [s[keys[i + k]] / base * 100 for k in SPAN]


def election_day(y):
    d = dt.date(y, 11, 1)
    while d.weekday() != 0:
        d += dt.timedelta(1)
    return d + dt.timedelta(1)


def perm(a, b, rnd, n=20000):
    obs = st.mean(a) - st.mean(b)
    vals, hit = a + b, 0
    for _ in range(n):
        rnd.shuffle(vals)
        hit += abs(st.mean(vals[:len(a)]) - st.mean(vals[len(a):])) >= abs(obs)
    return round(obs, 2), round(hit / n, 3)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fetch", action="store_true")
    if p.parse_args().fetch:
        fetch()
    L = build_levels()
    keys = {c: sorted(s) for c, s in L.items()}
    rows = []
    for e, (regime, strict) in ELECTIONS.items():
        day = dt.date.fromisoformat(e)
        for code, *_ in INDICATORS:
            row = {"year": e[:4], "regime": regime, "strict": strict, "prewar": e[:4] in PREWAR, "asset": code}
            for c, (a, b) in COLS.items():
                row[c] = window(L[code], keys[code], day, a, b)
            rows.append(row)

    groups = {
        "regime": ["统一→分治", "统一保持", "分治保持", "分治→统一"],
        "strict": ["只丢众议院", "两院皆失", "两院皆保"],
    }
    paths = {}
    for layer, gs in groups.items():
        paths[layer] = {}
        for code, *_ in INDICATORS:
            paths[layer][code] = {}
            variants = [(g, False) for g in gs] + ([("两院皆保（仅战后）", True)] if layer == "strict" else [("统一保持（仅战后）", True)])
            for g, postwar_only in variants:
                base_g = g.replace("（仅战后）", "")
                ps = [p for e, (r, s) in ELECTIONS.items()
                      if (r if layer == "regime" else s) == base_g and not (postwar_only and e[:4] in PREWAR)
                      for p in [path(L[code], keys[code], dt.date.fromisoformat(e))] if p]
                paths[layer][code][g] = {"n": len(ps), "values": [round(st.mean(c), 3) for c in zip(*ps)] if ps else []}

    # 检验：统一→分治 vs 统一保持（全样本与仅战后）；对照：中期选举年 vs 其他年份
    rnd = random.Random(2026)
    tests = []
    for code, name, *_ in INDICATORS:
        for c in ("post_1m", "post_2m"):
            a = [r[c] for r in rows if r["asset"] == code and r["regime"] == "统一→分治"]
            b = [r[c] for r in rows if r["asset"] == code and r["regime"] == "统一保持"]
            b2 = [r[c] for r in rows if r["asset"] == code and r["regime"] == "统一保持" and not r["prewar"]]
            d1, p1 = perm(a, b, rnd)
            d2, p2 = perm(a, b2, rnd)
            tests.append({"asset": code, "col": c, "diff": d1, "p": p1, "n": [len(a), len(b)],
                          "diff_postwar": d2, "p_postwar": p2, "n_postwar": [len(a), len(b2)]})
    control = {}
    for code, *_ in INDICATORS:
        res = {"中期选举年": [], "大选年": [], "其他年份": []}
        for y in range(1926, 2026):
            day = election_day(y)
            v = window(L[code], keys[code], day, 0, 42)
            if v is None:
                continue
            k = "中期选举年" if y % 4 == 2 else ("大选年" if y % 4 == 0 else "其他年份")
            res[k].append(v)
        control[code] = {k: {"n": len(v), "mean": round(st.mean(v), 2), "up": sum(x > 0 for x in v)} for k, v in res.items()}

    out = {"indicators": [{"code": c, "name": n} for c, n, *_ in INDICATORS],
           "elections": {e: {"regime": r, "strict": s} for e, (r, s) in ELECTIONS.items()},
           "rows": rows, "offsets": list(SPAN), "paths": paths, "tests": tests, "control": control,
           "range": [str(min(keys["MKT"])), str(max(keys["MKT"]))]}
    with open(os.path.join(ROOT, "data", "equity_long.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    print("样本区间", out["range"])
    for code, name, *_ in INDICATORS:
        line = []
        for layer, gs in groups.items():
            for g in gs:
                v = [r["post_2m"] for r in rows if r["asset"] == code and r[layer] == g and r["post_2m"] is not None]
                if v:
                    line.append(f"{g}{st.mean(v):+.1f}({sum(x > 0 for x in v)}/{len(v)})")
        print(name, " ".join(line))
    for t in tests:
        print(t["asset"], t["col"], "全样本 p", t["p"], t["n"], "仅战后 p", t["p_postwar"], t["n_postwar"])
    print({k: v for k, v in control["MKT"].items()})


if __name__ == "__main__":
    main()
