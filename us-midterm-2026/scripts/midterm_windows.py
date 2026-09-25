"""美国中期选举前后大类资产窗口统计（1990—2022 共 9 次中期选举）。

用法：
    python3 scripts/midterm_windows.py --fetch   # 重新下载行情到 data/
    python3 scripts/midterm_windows.py           # 用 data/ 下已有数据计算

窗口以选举日（或其前最近一个交易日）为 T，偏移单位为交易日：
    T-21→T（选前约一个月）、T→T+1（选举次日）、T→T+21（选后约一个月）、T→T+42（选后约两个月）。
股价、美元、黄金、原油为涨跌幅（%）；美债收益率为变动（bp）；VIX 为点位变动。
"""
import argparse
import bisect
import csv
import datetime as dt
import json
import os
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DATA = os.path.join(ROOT, "data")

ELECTIONS = {
    # 选举日: (美联储当时所处阶段, 反对党是否拿下众议院, 选后反对党是否控制两院)
    "1990-11-06": ("宽松", False, False),
    "1994-11-08": ("加息", True, True),
    "1998-11-03": ("宽松", False, False),
    "2002-11-05": ("宽松", False, False),
    "2006-11-07": ("暂停", True, True),
    "2010-11-02": ("宽松", True, False),
    "2014-11-04": ("暂停", False, True),
    "2018-11-06": ("加息", True, False),
    "2022-11-08": ("加息", True, False),
}

FRED = {"UST10": "DGS10", "UST2": "DGS2", "WTI": "DCOILWTICO", "VIX": "VIXCLS"}
YAHOO = {"SPX": "%5EGSPC", "DXY": "DX-Y.NYB", "Gold": "GC%3DF"}
RATES = {"UST10", "UST2"}
LEVELS = {"VIX"}
OFFSETS = [(-21, 0), (0, 1), (0, 21), (0, 42)]


def fetch():
    os.makedirs(DATA, exist_ok=True)
    for sid in FRED.values():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        urllib.request.urlretrieve(url, os.path.join(DATA, f"{sid}.csv"))
    for name, tk in YAHOO.items():
        url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{tk}"
               "?period1=631152000&period2=1800000000&interval=1d")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        r = json.load(urllib.request.urlopen(req))["chart"]["result"][0]
        closes = r["indicators"]["quote"][0]["close"]
        with open(os.path.join(DATA, f"{name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["date", name])
            for t, c in zip(r["timestamp"], closes):
                if c:
                    w.writerow([dt.datetime.utcfromtimestamp(t).date().isoformat(), round(c, 4)])


def load(path):
    out = {}
    with open(path) as f:
        for row in list(csv.reader(f))[1:]:
            try:
                out[dt.date.fromisoformat(row[0])] = float(row[1])
            except ValueError:
                pass
    return out


def series():
    s = {k: load(os.path.join(DATA, f"{v}.csv")) for k, v in FRED.items()}
    s.update({k: load(os.path.join(DATA, f"{k}.csv")) for k in YAHOO})
    return s


def value_at(s, day, off):
    keys = sorted(s)
    i = bisect.bisect_right(keys, day) - 1
    j = i + off
    if i < 0 or not 0 <= j < len(keys) or (day - keys[i]).days > 5:
        return None
    return s[keys[j]]


def change(name, x, y):
    if name in RATES:
        return round((y - x) * 100, 1)
    if name in LEVELS:
        return round(y - x, 2)
    return round((y / x - 1) * 100, 2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--fetch", action="store_true")
    if p.parse_args().fetch:
        fetch()
    S = series()
    rows = []
    for e, (fed, house_flip, opp_both) in ELECTIONS.items():
        day = dt.date.fromisoformat(e)
        for name, s in S.items():
            row = {"election": e, "fed": fed, "house_flip": house_flip,
                   "opp_both": opp_both, "asset": name, "level_T": value_at(s, day, 0)}
            for a, b in OFFSETS:
                x, y = value_at(s, day, a), value_at(s, day, b)
                row[f"T{a:+d}_T{b:+d}"] = None if x is None or y is None else change(name, x, y)
            rows.append(row)
    out = os.path.join(DATA, "midterm_windows.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    cols = [f"T{a:+d}_T{b:+d}" for a, b in OFFSETS]

    def summary(label, pick):
        print(f"\n== {label} ==")
        print("asset   " + "  ".join(f"{c:>14}" for c in cols))
        for name in S:
            cells = []
            for c in cols:
                v = [r[c] for r in rows if r["asset"] == name and pick(r) and r[c] is not None]
                cells.append(f"{sum(v)/len(v):7.2f} ({sum(x > 0 for x in v)}/{len(v)})" if v else f"{'n/a':>14}")
            print(f"{name:<7} " + "  ".join(cells))

    summary("全部样本 均值（上涨次数/样本数）", lambda r: True)
    for fed in ("加息", "宽松", "暂停"):
        summary(f"美联储{fed}", lambda r, f=fed: r["fed"] == f)
    summary("反对党选后控制两院", lambda r: r["opp_both"])
    summary("众议院易主", lambda r: r["house_flip"])


if __name__ == "__main__":
    main()
