"""美国中期选举前后大类资产窗口统计（1946—2022 共 20 次中期选举）。

用法：
    python3 scripts/midterm_windows.py --fetch   # 重新下载行情到 data/
    python3 scripts/midterm_windows.py           # 用 data/ 下已有数据计算

日度窗口以选举日（或其前最近一个交易日；1984 年以前选举日休市）为 T，偏移单位为交易日：
    T-21→T（选前约一个月）、T→T+1（选举次日）、T→T+21（选后约一个月）、T→T+42（选后约两个月）。
月度窗口（黄金、原油的长样本）以 10 月为 M：9 月→10 月（选前）、10 月→11 月（选后一个月）、10 月→12 月（选后两个月）。
股价、美元、黄金、原油为涨跌幅（%）；美债收益率为变动（bp）；VIX 为点位变动。

各资产日度数据起点决定样本数：
    标普 500 1946 起（20 次）、3 个月国债 1954 起（18 次）、10 年美债 1962 起（16 次）、
    2 年美债 1978 起（12 次）、美元指数 1974 起（13 次）、VIX/VXO 1986 起（10 次）、
    WTI 日度 1986 起（10 次）、黄金日度 2002 起（6 次）；黄金、WTI 月度 1974 起（13 次）。
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import os
import statistics
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")

# 选举日: (美联储当时所处阶段, 选举结果类型)
# 结果类型：反对党新获两院 / 众议院易主（参议院未易主） / 执政党保住两院 / 维持分治
ELECTIONS = {
    "1946-11-05": ("暂停", "反对党新获两院"),   # 利率钉住时期
    "1950-11-07": ("暂停", "执政党保住两院"),   # 利率钉住时期
    "1954-11-02": ("宽松", "反对党新获两院"),
    "1958-11-04": ("加息", "维持分治"),
    "1962-11-06": ("暂停", "执政党保住两院"),
    "1966-11-08": ("加息", "执政党保住两院"),   # 紧缩末段
    "1970-11-03": ("宽松", "维持分治"),
    "1974-11-05": ("宽松", "维持分治"),
    "1978-11-07": ("加息", "执政党保住两院"),
    "1982-11-02": ("宽松", "维持分治"),
    "1986-11-04": ("宽松", "反对党新获两院"),
    "1990-11-06": ("宽松", "维持分治"),
    "1994-11-08": ("加息", "反对党新获两院"),
    "1998-11-03": ("宽松", "维持分治"),
    "2002-11-05": ("宽松", "执政党保住两院"),
    "2006-11-07": ("暂停", "反对党新获两院"),
    "2010-11-02": ("宽松", "众议院易主"),
    "2014-11-04": ("暂停", "反对党新获两院"),
    "2018-11-06": ("加息", "众议院易主"),
    "2022-11-08": ("加息", "众议院易主"),
}

FRED = {"UST10": "DGS10", "UST2": "DGS2", "UST3M": "DTB3", "WTI": "DCOILWTICO",
        "VIX": "VIXCLS", "VXO": "VXOCLS", "WTI_M": "WTISPLC"}
YAHOO = {"SPX": "%5EGSPC", "DXY": "DX-Y.NYB", "Gold": "GC%3DF"}
GOLD_M_URL = "https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly.csv"
RATES = {"UST10", "UST2", "UST3M"}
LEVELS = {"VIX"}
START = {"DXY": dt.date(1974, 1, 1)}  # 1971—1973 为布雷顿森林体系解体过渡期
OFFSETS = [(-21, 0), (0, 1), (0, 21), (0, 42)]
M_OFFSETS = [(-1, 0), (0, 1), (0, 2)]  # 相对 10 月
ASSETS = ["SPX", "UST3M", "UST2", "UST10", "DXY", "Gold", "WTI", "VIX", "Gold_M", "WTI_M"]


def fetch():
    os.makedirs(DATA, exist_ok=True)
    for sid in FRED.values():
        urllib.request.urlretrieve(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}",
                                   os.path.join(DATA, f"{sid}.csv"))
    urllib.request.urlretrieve(GOLD_M_URL, os.path.join(DATA, "gold_monthly.csv"))
    for name, tk in YAHOO.items():
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}"
               "?period1=-1400000000&period2=1800000000&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = json.load(urllib.request.urlopen(req))["chart"]["result"][0]
        closes = r["indicators"]["quote"][0]["close"]
        with open(os.path.join(DATA, f"{name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", name])
            for t, c in zip(r["timestamp"], closes):
                if c:
                    day = (dt.datetime(1970, 1, 1) + dt.timedelta(seconds=t)).date()
                    w.writerow([day.isoformat(), round(c, 4)])


def load(path):
    out = {}
    with open(path) as f:
        for row in list(csv.reader(f))[1:]:
            try:
                d = row[0] if len(row[0]) > 7 else row[0] + "-01"
                out[dt.date.fromisoformat(d)] = float(row[1])
            except (ValueError, IndexError):
                pass
    return out


def series():
    s = {k: load(os.path.join(DATA, f"{v}.csv")) for k, v in FRED.items()}
    s.update({k: load(os.path.join(DATA, f"{k}.csv")) for k in YAHOO})
    s["Gold_M"] = load(os.path.join(DATA, "gold_monthly.csv"))
    # VIX 1990 年起，此前用 VXO 补足
    vxo = s.pop("VXO")
    s["VIX"] = {**{d: v for d, v in vxo.items() if d.year < 1990}, **s["VIX"]}
    for k, d0 in START.items():
        s[k] = {d: v for d, v in s[k].items() if d >= d0}
    s["Gold_M"] = {d: v for d, v in s["Gold_M"].items() if d.year >= 1974}
    s["WTI_M"] = {d: v for d, v in s["WTI_M"].items() if d.year >= 1974}
    return s


def daily_at(s, day, off):
    keys = sorted(s)
    i = bisect.bisect_right(keys, day) - 1
    j = i + off
    if i < 0 or not 0 <= j < len(keys) or (day - keys[i]).days > 5:
        return None
    return s[keys[j]]


def monthly_at(s, day, off):
    m = day.month - 1 + off
    return s.get(dt.date(day.year + m // 12, m % 12 + 1, 1))


def change(name, x, y):
    if name in RATES:
        return round((y - x) * 100, 1)
    if name in LEVELS:
        return round(y - x, 2)
    return round((y / x - 1) * 100, 2)


COLS = ["pre_1m", "day_after", "post_1m", "post_2m"]


def build_rows(S):
    rows = []
    for e, (fed, outcome) in ELECTIONS.items():
        day = dt.date.fromisoformat(e)
        for name in ASSETS:
            s = S[name]
            monthly = name.endswith("_M")
            offs = M_OFFSETS if monthly else OFFSETS
            at = monthly_at if monthly else daily_at
            row = {"election": e, "fed": fed, "outcome": outcome, "asset": name,
                   "level_T": at(s, day.replace(month=10) if monthly else day, 0)}
            cols = ["pre_1m", "post_1m", "post_2m"] if monthly else COLS
            for c, (a, b) in zip(cols, offs):
                base = day.replace(day=1, month=10) if monthly else day
                x, y = at(s, base, a), at(s, base, b)
                row[c] = None if x is None or y is None else change(name, x, y)
            row.setdefault("day_after", None)
            rows.append(row)
    return rows


def stats(v):
    if not v:
        return "n/a"
    return f"{statistics.mean(v):7.2f} | {statistics.median(v):6.2f} ({sum(x > 0 for x in v)}/{len(v)})"


def summary(rows, label, pick):
    print(f"\n== {label} ==   均值 | 中位数 (上涨次数/样本数)")
    print(f"{'asset':<7}" + "".join(f"{c:>26}" for c in COLS))
    for name in ASSETS:
        cells = [stats([r[c] for r in rows if r["asset"] == name and pick(r) and r[c] is not None])
                 for c in COLS]
        print(f"{name:<7}" + "".join(f"{c:>26}" for c in cells))


def spx_path(S):
    s = S["SPX"]
    keys = sorted(s)
    print("\n== 标普 500 选前低点（9 月 1 日至选举日）与选后路径 ==")
    for e in ELECTIONS:
        d = dt.date.fromisoformat(e)
        w = [k for k in keys if dt.date(d.year, 9, 1) <= k <= d]
        low = min(w, key=lambda k: s[k])
        high = max([k for k in keys if dt.date(d.year, 7, 1) <= k <= low], key=lambda k: s[k])
        t = keys[bisect.bisect_right(keys, d) - 1]
        ye = [k for k in keys if k <= dt.date(d.year, 12, 31)][-1]
        print(f"{d.year} 低点 {low}  回撤 {(s[low]/s[high]-1)*100:6.1f}%  "
              f"选举日→年末 {(s[ye]/s[t]-1)*100:6.1f}%  低点→年末 {(s[ye]/s[low]-1)*100:6.1f}%")


def latest(S):
    print("\n== 最新值 ==")
    for name in ["SPX", "UST3M", "UST2", "UST10", "DXY", "Gold", "WTI", "VIX"]:
        k = max(S[name])
        print(name, k, round(S[name][k], 2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fetch", action="store_true")
    if p.parse_args().fetch:
        fetch()
    S = series()
    rows = build_rows(S)
    with open(os.path.join(DATA, "midterm_windows.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["election", "fed", "outcome", "asset", "level_T"] + COLS)
        w.writeheader()
        w.writerows(rows)

    summary(rows, "全部样本", lambda r: True)
    for fed in ("加息", "宽松", "暂停"):
        summary(rows, f"美联储{fed}", lambda r, f=fed: r["fed"] == f)
    for oc in ("反对党新获两院", "众议院易主", "执政党保住两院", "维持分治"):
        summary(rows, f"结果：{oc}", lambda r, o=oc: r["outcome"] == o)
    summary(rows, "1990 年以后（对照）", lambda r: r["election"] >= "1990")
    spx_path(S)
    latest(S)


if __name__ == "__main__":
    main()
