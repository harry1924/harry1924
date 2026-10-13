"""生成报告图表所需数据：data/chart_data.json。

依赖 midterm_windows.py 读取的同一批数据（先运行 midterm_windows.py --fetch）。
"""
import bisect
import csv
import datetime as dt
import json
import os
import random
import statistics as st

from midterm_windows import DATA, ELECTIONS, REGIME, STRICT, build_rows, load, series

S = series()
ROWS = build_rows(S)
SPAN = range(-63, 64)


def path(name, day, mode):
    s = S[name]
    keys = sorted(s)
    i = bisect.bisect_right(keys, day) - 1
    if i < 0 or (day - keys[i]).days > 5 or i + SPAN[0] < 0 or i + SPAN[-1] >= len(keys):
        return None
    base = s[keys[i]]
    if mode == "pct":
        return [round((s[keys[i + k]] / base) * 100, 3) for k in SPAN]
    return [round((s[keys[i + k]] - base) * 100, 2) for k in SPAN]


def avg_path(name, mode, pick):
    ps = [p for e, meta in ELECTIONS.items() if pick(meta)
          for p in [path(name, dt.date.fromisoformat(e), mode)] if p]
    return {"n": len(ps), "values": [round(st.mean(col), 3) for col in zip(*ps)]}


def event_paths():
    out = {"offsets": list(SPAN)}
    groups = {"全部": lambda m: True, "加息": lambda m: m[0] == "加息", "宽松": lambda m: m[0] == "宽松",
              "反对党新获两院": lambda m: m[1] == "反对党新获两院",
              "众议院易主": lambda m: m[1] == "众议院易主",
              "执政党保住两院": lambda m: m[1] == "执政党保住两院"}
    out["SPX"] = {g: avg_path("SPX", "pct", f) for g, f in groups.items()}
    out["UST10"] = {g: avg_path("UST10", "bp", f) for g, f in groups.items()}
    out["DXY"] = {g: avg_path("DXY", "pct", f) for g, f in groups.items()}
    out["Gold"] = {g: avg_path("Gold", "pct", f) for g, f in groups.items()}
    out["UST3M"] = {g: avg_path("UST3M", "bp", f) for g, f in groups.items()}
    out["WTI"] = {g: avg_path("WTI", "pct", f) for g, f in groups.items()}
    out["Gold_years"] = {e[:4]: p for e in ELECTIONS
                         for p in [path("Gold", dt.date.fromisoformat(e), "pct")] if p}
    return out


def election_day(y):
    d = dt.date(y, 11, 1)
    while d.weekday() != 0:
        d += dt.timedelta(1)
    return d + dt.timedelta(1)


def control():
    """中期选举年与大选年、其他年份同一日期之后的表现对照。"""
    out = {}
    specs = {"UST10": ("bp", 1962), "DXY": ("pct", 1974), "Gold": ("pct", 2000)}
    for name, (mode, y0) in specs.items():
        s = S[name]
        keys = sorted(s)
        res = {"中期选举年": [], "大选年": [], "其他年份": []}
        for y in range(y0, 2026):
            day = election_day(y)
            i = bisect.bisect_right(keys, day) - 1
            if i < 0 or i + 42 >= len(keys) or (day - keys[i]).days > 5:
                continue
            k = "中期选举年" if y % 4 == 2 else ("大选年" if y % 4 == 0 else "其他年份")
            x, a, b = s[keys[i]], s[keys[i + 21]], s[keys[i + 42]]
            f = (lambda u, v: (v - u) * 100) if mode == "bp" else (lambda u, v: (v / u - 1) * 100)
            res[k].append((y, f(x, a), f(x, b)))
        out[name] = {k: {"n": len(v), "m1": round(st.mean([z[1] for z in v]), 2),
                         "m2": round(st.mean([z[2] for z in v]), 2),
                         "up1": sum(z[1] > 0 for z in v), "down1": sum(z[1] < 0 for z in v),
                         "up2": sum(z[2] > 0 for z in v), "down2": sum(z[2] < 0 for z in v)}
                     for k, v in res.items()}
    # 黄金月度长样本：10 月至 11 月、10 月至 12 月
    gm = S["Gold_M"]
    res = {"中期选举年": [], "大选年": [], "其他年份": []}
    for y in range(1974, 2026):
        o, n_, d_ = gm.get(dt.date(y, 10, 1)), gm.get(dt.date(y, 11, 1)), gm.get(dt.date(y, 12, 1))
        if o and n_ and d_:
            k = "中期选举年" if y % 4 == 2 else ("大选年" if y % 4 == 0 else "其他年份")
            res[k].append((y, (n_ / o - 1) * 100, (d_ / o - 1) * 100))
    out["Gold_M"] = {k: {"n": len(v), "m1": round(st.mean([z[1] for z in v]), 2),
                         "m2": round(st.mean([z[2] for z in v]), 2),
                         "up1": sum(z[1] > 0 for z in v), "down1": sum(z[1] < 0 for z in v),
                         "up2": sum(z[2] > 0 for z in v), "down2": sum(z[2] < 0 for z in v)}
                     for k, v in res.items()}
    return out


def analog_2026():
    """2018、2022 与 2026 年标普 500 路径，按距离选举日的交易日对齐，以 2026 年最新可比日为 100。"""
    s = S["SPX"]
    keys = sorted(s)
    e26 = dt.date(2026, 11, 3)
    last = keys[-1]
    # 2026 年最新交易日距离选举日的交易日数（按工作日估算，剔除感恩节前无假期）
    days_left = sum(1 for k in range(1, (e26 - last).days + 1)
                    if (last + dt.timedelta(k)).weekday() < 5)
    out = {"days_left": days_left, "latest": str(last), "series": {}}
    rng = range(-126, 64)
    out["offsets"] = list(rng)
    for y, e in (("2018", "2018-11-06"), ("2022", "2022-11-08")):
        i = bisect.bisect_right(keys, dt.date.fromisoformat(e)) - 1
        base = s[keys[i - days_left]]
        out["series"][y] = [round(s[keys[i + k]] / base * 100, 2) for k in rng]
    # 历次均值
    allp = []
    for e in ELECTIONS:
        i = bisect.bisect_right(keys, dt.date.fromisoformat(e)) - 1
        base = s[keys[i - days_left]]
        allp.append([s[keys[i + k]] / base * 100 for k in rng])
    out["series"]["20 次均值"] = [round(st.mean(c), 2) for c in zip(*allp)]
    j = len(keys) - 1
    base = s[keys[j]]
    v26 = []
    for k in rng:
        idx = j + (k + days_left)
        v26.append(round(s[keys[idx]] / base * 100, 2) if idx <= j else None)
    out["series"]["2026"] = v26
    return out


def long_series():
    out = {}
    ust = S["UST10"]
    monthly = {}
    for d, v in sorted(ust.items()):
        monthly[(d.year, d.month)] = v  # 月末值
    out["UST10_monthly"] = [[f"{y}-{m:02d}", v] for (y, m), v in sorted(monthly.items())]
    spx = S["SPX"]
    m2 = {}
    for d, v in sorted(spx.items()):
        if d.year >= 1946:
            m2[(d.year, d.month)] = v
    out["SPX_monthly"] = [[f"{y}-{m:02d}", round(v, 2)] for (y, m), v in sorted(m2.items())]
    deficit = load(os.path.join(DATA, "FYFSGDA188S.csv"))
    out["deficit"] = [[d.year, round(v, 2)] for d, v in sorted(deficit.items()) if d.year >= 1946]
    return out


# 1946—2026 年政府格局：总统所在党是否同时控制两院（2001 年参议院年中易手，按分治计）
UNIFIED = set(range(1946, 1947)) | set(range(1949, 1955)) | set(range(1961, 1969)) | \
    set(range(1977, 1981)) | set(range(1993, 1995)) | set(range(2003, 2007)) | \
    set(range(2009, 2011)) | set(range(2017, 2019)) | set(range(2021, 2023)) | set(range(2025, 2027))


def deficit_by_regime():
    deficit = {d.year: v for d, v in load(os.path.join(DATA, "FYFSGDA188S.csv")).items()}
    res = {"统一": [], "分治": []}
    for y in range(1947, 2026):
        if y in deficit and y - 1 in deficit:
            res["统一" if y in UNIFIED else "分治"].append(deficit[y] - deficit[y - 1])
    return {k: {"n": len(v), "mean": round(st.mean(v), 2), "improve": sum(x > 0 for x in v)}
            for k, v in res.items()}


def perm_test(asset, col, key):
    d = [(r[key], r[col]) for r in ROWS if r["asset"] == asset and r[col] is not None]
    y = [v for _, v in d]
    m = st.mean(y)
    sst = sum((v - m) ** 2 for v in y)

    def ssb(labels):
        g = {}
        for k, v in zip(labels, y):
            g.setdefault(k, []).append(v)
        return sum(len(v) * (st.mean(v) - m) ** 2 for v in g.values())

    labels = [k for k, _ in d]
    obs = ssb(labels) / sst
    rnd = random.Random(2026)
    hit = 0
    for _ in range(20000):
        rnd.shuffle(labels)
        hit += ssb(labels) / sst >= obs
    return {"eta2": round(obs, 2), "p": round(hit / 20000, 3), "n": len(y)}


def tests():
    out = []
    for asset, col, label in [("SPX", "day_after", "标普 500·选举次日"), ("SPX", "post_2m", "标普 500·选后两个月"),
                              ("UST10", "post_1m", "10 年美债·选后一个月"), ("UST3M", "post_2m", "3 个月国债·选后两个月"),
                              ("DXY", "day_after", "美元指数·选举次日"), ("Gold_M", "post_2m", "黄金月度·选后两个月"),
                              ("WTI", "post_1m", "WTI·选后一个月")]:
        out.append({"label": label, "outcome": perm_test(asset, col, "outcome"), "fed": perm_test(asset, col, "fed")})
    return out


LAYER_ASSETS = [("SPX", "pct"), ("UST3M", "bp"), ("UST10", "bp"), ("DXY", "pct"), ("GoldL", "pct"), ("WTI", "pct")]


def layer_paths():
    """两层分类下各资产的选举前后平均路径。"""
    out = {"offsets": list(SPAN)}
    for layer, groups in (("regime", REGIME), ("strict", STRICT)):
        out[layer] = {}
        for name, mode in LAYER_ASSETS:
            out[layer][name] = {}
            for g, years in groups.items():
                ps = [p for e in ELECTIONS if e[:4] in years
                      for p in [path(name, dt.date.fromisoformat(e), mode)] if p]
                out[layer][name][g] = {"n": len(ps), "values": [round(st.mean(c), 3) for c in zip(*ps)] if ps else []}
    return out


EXT_ASSETS = ["MKT", "IXIC", "SMB", "HML", "IND_Banks", "IND_Oil", "IND_Drugs", "IND_Util", "IND_Guns"]
PREWAR = {"1930": "1930-11-04", "1934": "1934-11-06", "1938": "1938-11-08", "1942": "1942-11-03"}


def ext_paths():
    """补充美股指标：第二层三种结果的平均路径，另给出含战前（1930—1942）的两院皆保。"""
    out = {}
    for name in EXT_ASSETS:
        out[name] = {}
        groups = {g: [e for e in ELECTIONS if e[:4] in ys] for g, ys in STRICT.items() if ys}
        groups["两院皆保（含战前）"] = groups["两院皆保"] + list(PREWAR.values())
        for g, dates in groups.items():
            ps = [p for e in dates for p in [path(name, dt.date.fromisoformat(e), "pct")] if p]
            out[name][g] = {"n": len(ps), "values": [round(st.mean(c), 3) for c in zip(*ps)] if ps else []}
    # 战前四次的选后表现（用于表格）
    pre = {}
    for name in EXT_ASSETS:
        pre[name] = {}
        for y, e in PREWAR.items():
            d = dt.date.fromisoformat(e)
            vals = [path(name, d, "pct")]
            if vals[0]:
                v = vals[0]
                pre[name][y] = {"post_1m": round(v[63 + 21] - 100, 2), "post_2m": round(v[63 + 42] - 100, 2)}
    return out, pre


def regime_tests():
    """第一层：统一→分治与统一保持的差异，以及四类分组整体的解释度。"""
    rnd = random.Random(2026)
    res = []
    for name, _ in LAYER_ASSETS:
        for col in ("post_1m", "post_2m"):
            a = [r[col] for r in ROWS if r["asset"] == name and r["regime"] == "统一→分治" and r[col] is not None]
            b = [r[col] for r in ROWS if r["asset"] == name and r["regime"] == "统一保持" and r[col] is not None]
            if len(a) < 2 or len(b) < 2:
                res.append({"asset": name, "col": col, "na": len(a), "nb": len(b), "p": None})
                continue
            obs = st.mean(a) - st.mean(b)
            vals, hit = a + b, 0
            for _ in range(20000):
                rnd.shuffle(vals)
                hit += abs(st.mean(vals[:len(a)]) - st.mean(vals[len(a):])) >= abs(obs)
            res.append({"asset": name, "col": col, "na": len(a), "nb": len(b), "diff": round(obs, 2),
                        "p": round(hit / 20000, 3), "regime_all": perm_test(name, col, "regime")})
    return res


def main():
    data = {
        "rows": ROWS,
        "elections": {e: {"fed": f, "outcome": o} for e, (f, o) in ELECTIONS.items()},
        "event": event_paths(),
        "analog": analog_2026(),
        "long": long_series(),
        "deficit_regime": deficit_by_regime(),
        "tests": tests(),
        "layer": layer_paths(),
        "ext": dict(zip(("paths", "prewar"), ext_paths())),
        "regime_tests": regime_tests(),
        "control": control(),
    }
    with open(os.path.join(DATA, "chart_data.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: data[k] for k in ("deficit_regime", "tests")}, ensure_ascii=False, indent=1))
    print("analog", data["analog"]["days_left"], data["analog"]["latest"])
    for g, v in data["event"]["SPX"].items():
        print("SPX", g, v["n"], v["values"][63 - 21], v["values"][63], v["values"][63 + 21], v["values"][63 + 42])
    print(json.dumps(data["control"], ensure_ascii=False))
    for k in ("DXY", "Gold"):
        for g, v in data["event"][k].items():
            if v["n"]:
                print(k, g, v["n"], v["values"][63 - 21], v["values"][63 + 21], v["values"][63 + 42])
    for g, v in data["event"]["UST10"].items():
        print("UST10", g, v["n"], v["values"][63 - 21], v["values"][63 + 21], v["values"][63 + 42])


if __name__ == "__main__":
    main()
