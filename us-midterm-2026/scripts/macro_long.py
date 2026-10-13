"""美债、美元、黄金长样本专题：统一样本（1974—2022 年 13 次中选）与各资产最长样本。

用法：
    python3 scripts/macro_long.py --fetch   # 下载 FRED 月度长债与 3 个月国债数据
    python3 scripts/macro_long.py           # 计算并输出 data/macro_long.json

日度数据沿用 midterm_windows.py 已下载的 data/ 文件：10 年美债（DGS10，1962 年起）、
3 个月国债（DTB3，1954 年起）、2 年美债（DGS2，1976 年起）、美元指数（DX-Y.NYB）、
黄金（LBMA 下午定盘价，1968 年起）。
月度长样本：长期国债收益率（FRED LTGOVTBD，1925—2000 年）与 10 年美债月均值（GS10，1953 年起），
1961 年及以前用 LTGOVTBD、1962 年起用 GS10；3 个月国债月均值（TB3MS，1934 年起）。
1942 年 4 月至 1951 年 3 月美联储钉住国债收益率，期间的中期选举（1942、1946、1950）不计入利率统计。
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import os
import random
import statistics as st
import urllib.request

from equity_long import ELECTIONS, PREWAR, election_day, perm

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")
SPAN = range(-63, 64)

DAILY = {
    # 代码: (中文名, 文件, 单位, 起点年份——首个可用中选的下限)
    "UST10": ("10 年美债收益率", "DGS10.csv", "bp", 1962),
    "UST3M": ("3 个月国债收益率", "DTB3.csv", "bp", 1954),
    "UST2": ("2 年美债收益率", "DGS2.csv", "bp", 1978),
    "DXY": ("美元指数", "DXY.csv", "pct", 1974),
    "GoldL": ("黄金（LBMA）", "GoldLBMA.csv", "pct", 1970),
}
COMMON = (1974, 2022)  # 统一样本
PEG = {"1942", "1946", "1950"}  # 利率钉住期
COLS = {"pre_1m": (-21, 0), "day_after": (0, 1), "post_1m": (0, 21), "post_2m": (0, 42)}
MONTHLY = {"LTGOVTBD": "长期国债", "GS10": "10 年美债月均", "TB3MS": "3 个月国债月均"}


def fetch():
    for sid in MONTHLY:
        urllib.request.urlretrieve(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                                   os.path.join(DATA, f"{sid}.csv"))


def load(name):
    out = {}
    with open(os.path.join(DATA, name)) as f:
        for row in list(csv.reader(f))[1:]:
            try:
                d = row[0] if len(row[0]) > 7 else row[0] + "-01"
                out[dt.date.fromisoformat(d)] = float(row[1])
            except (ValueError, IndexError):
                pass
    return out


def window(s, keys, day, a, b, unit):
    i = bisect.bisect_right(keys, day) - 1
    if i < 0 or (day - keys[i]).days > 5 or i + a < 0 or i + b >= len(keys):
        return None
    x, y = s[keys[i + a]], s[keys[i + b]]
    return round((y - x) * 100, 1) if unit == "bp" else round((y / x - 1) * 100, 2)


def path(s, keys, day, unit):
    i = bisect.bisect_right(keys, day) - 1
    if i < 0 or (day - keys[i]).days > 5 or i + SPAN[0] < 0 or i + SPAN[-1] >= len(keys):
        return None
    base = s[keys[i]]
    return [(s[keys[i + k]] - base) * 100 if unit == "bp" else s[keys[i + k]] / base * 100 for k in SPAN]


def usable(code, year):
    return int(year) >= DAILY[code][3]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fetch", action="store_true")
    if p.parse_args().fetch:
        fetch()
    S = {c: load(v[1]) for c, v in DAILY.items()}
    S["DXY"] = {d: v for d, v in S["DXY"].items() if d.year >= 1974}
    K = {c: sorted(s) for c, s in S.items()}

    rows = []
    for e, (regime, strict) in ELECTIONS.items():
        day, y = dt.date.fromisoformat(e), e[:4]
        for code, (_, _, unit, _) in DAILY.items():
            row = {"year": y, "regime": regime, "strict": strict, "asset": code,
                   "common": COMMON[0] <= int(y) <= COMMON[1]}
            for c, (a, b) in COLS.items():
                row[c] = window(S[code], K[code], day, a, b, unit) if usable(code, y) else None
            rows.append(row)

    # 月度长债：10 月均值至 11 月、12 月均值（1961 年及以前 LTGOVTBD，1962 年起 GS10）
    lt, g10, tb = load("LTGOVTBD.csv"), load("GS10.csv"), load("TB3MS.csv")
    monthly = []
    for y in range(1926, 2026):
        src = lt if y <= 1961 else g10
        o, n, d = (src.get(dt.date(y, m, 1)) for m in (10, 11, 12))
        to, tn, td = (tb.get(dt.date(y, m, 1)) for m in (10, 11, 12))
        e = next((k for k in ELECTIONS if k[:4] == str(y)), None)
        monthly.append({"year": str(y), "midterm": y % 4 == 2, "pres": y % 4 == 0,
                        "peg": 1942 <= y <= 1950, "regime": ELECTIONS[e][0] if e else "",
                        "strict": ELECTIONS[e][1] if e else "",
                        "lt_1m": round((n - o) * 100) if o and n else None,
                        "lt_2m": round((d - o) * 100) if o and d else None,
                        "tb_2m": round((td - to) * 100) if to and td else None})

    # 平均路径：统一样本与最长样本
    groups = {"regime": ["统一→分治", "统一保持", "分治保持"], "strict": ["只丢众议院", "两院皆失", "两院皆保"]}
    paths = {}
    for sample in ("common", "longest"):
        paths[sample] = {}
        for layer, gs in groups.items():
            paths[sample][layer] = {}
            for code, (_, _, unit, _) in DAILY.items():
                paths[sample][layer][code] = {}
                for g in gs:
                    ps = [p for e, (r, s) in ELECTIONS.items()
                          if (r if layer == "regime" else s) == g and usable(code, e[:4])
                          and (sample == "longest" or COMMON[0] <= int(e[:4]) <= COMMON[1])
                          for p in [path(S[code], K[code], dt.date.fromisoformat(e), unit)] if p]
                    paths[sample][layer][code][g] = {"n": len(ps), "values": [round(st.mean(c), 3) for c in zip(*ps)] if ps else []}

    # 对照：中期选举年 vs 大选年 vs 其他年份（日度，各资产最长样本）
    control = {}
    for code, (_, _, unit, y0) in DAILY.items():
        res = {"中期选举年": [], "大选年": [], "其他年份": []}
        for y in range(max(y0, 1954), 2026):
            v = window(S[code], K[code], election_day(y), 0, 42, unit)
            v1 = window(S[code], K[code], election_day(y), 0, 21, unit)
            if v is None:
                continue
            k = "中期选举年" if y % 4 == 2 else ("大选年" if y % 4 == 0 else "其他年份")
            res[k].append((v1, v))
        control[code] = {k: {"n": len(v), "m1": round(st.mean(a for a, _ in v), 2), "m2": round(st.mean(b for _, b in v), 2),
                             "up1": sum(a > 0 for a, _ in v), "up2": sum(b > 0 for _, b in v)} for k, v in res.items()}
    mres = {"中期选举年": [], "大选年": [], "其他年份": []}
    for m in monthly:
        if m["peg"] or m["lt_2m"] is None:
            continue
        k = "中期选举年" if m["midterm"] else ("大选年" if m["pres"] else "其他年份")
        mres[k].append(m["lt_2m"])
    control["LT_monthly"] = {k: {"n": len(v), "m2": round(st.mean(v), 1), "down2": sum(x < 0 for x in v)} for k, v in mres.items()}

    # 检验：统一→分治 vs 统一保持（有至少 2 个样本时）
    rnd = random.Random(2026)
    tests = []
    for code in DAILY:
        for c in ("post_1m", "post_2m"):
            a = [r[c] for r in rows if r["asset"] == code and r["regime"] == "统一→分治" and r[c] is not None]
            b = [r[c] for r in rows if r["asset"] == code and r["regime"] == "统一保持" and r[c] is not None]
            if len(a) >= 2 and len(b) >= 2:
                d, pv = perm(a, b, rnd)
                tests.append({"asset": code, "col": c, "diff": d, "p": pv, "n": [len(a), len(b)]})
    ma = [m["lt_2m"] for m in monthly if m["regime"] == "统一→分治" and not m["peg"] and m["lt_2m"] is not None]
    mb = [m["lt_2m"] for m in monthly if m["regime"] == "统一保持" and not m["peg"] and m["lt_2m"] is not None]
    d, pv = perm(ma, mb, rnd)
    tests.append({"asset": "LT_monthly", "col": "post_2m", "diff": d, "p": pv, "n": [len(ma), len(mb)]})

    out = {"assets": [{"code": c, "name": v[0], "unit": v[2], "start": v[3]} for c, v in DAILY.items()],
           "elections": {e: {"regime": r, "strict": s} for e, (r, s) in ELECTIONS.items()},
           "rows": rows, "monthly": monthly, "offsets": list(SPAN), "paths": paths, "control": control, "tests": tests}
    with open(os.path.join(DATA, "macro_long.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    for code in DAILY:
        for sample in ("common", "longest"):
            line = []
            for layer, gs in groups.items():
                for g in gs:
                    v = [r["post_2m"] for r in rows if r["asset"] == code and r[layer] == g and r["post_2m"] is not None
                         and (sample == "longest" or r["common"])]
                    if v:
                        line.append(f"{g}{st.mean(v):+.1f}({sum(x > 0 for x in v)}/{len(v)})")
            print(code, sample, " ".join(line))
    print(json.dumps(control, ensure_ascii=False))
    print(tests)
    print([(m["year"], m["regime"], m["strict"], m["lt_2m"]) for m in monthly if m["year"] in [e[:4] for e in ELECTIONS]])


if __name__ == "__main__":
    main()
