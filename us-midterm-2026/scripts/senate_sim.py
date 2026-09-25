"""2026 参议院控制权蒙特卡洛测算。

输入为各州最新民调均值（民主党领先为正，单位：个点），无民调的州按 Cook 评级赋值（假设）。
误差结构：全国共同误差 + 州独立误差，二者均服从正态分布。
民主党需在 53:47 的基础上净增 4 席（51 席）才能控制参议院。
输出 data/senate_sim.json。
"""
import json
import os
import random

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# (州, 现任党, 民主党领先幅度, 来源)
RACES = [
    ("北卡罗来纳", "R", 6.1, "Pollsmax 均值，Cooper 48.3 vs Whatley 42.2"),
    ("俄亥俄（特别）", "R", 3.7, "PollingSource 近 30 天均值，Brown 46.7 vs Husted 43.0"),
    ("得克萨斯", "R", 2.6, "RCP 均值，Talarico 领先"),
    ("阿拉斯加", "R", 2.0, "RCP 均值，Peltola 49 vs Sullivan 47"),
    ("缅因", "R", 0.8, "RCP 均值，Jackson 46.8 vs Collins 46.0"),
    ("爱荷华", "R", -1.1, "RCP 均值，Hinson 领先"),
    ("内布拉斯加", "R", -6.0, "假设：按 Lean R 赋值（Osborn 为独立候选人）"),
    ("堪萨斯", "R", -6.0, "假设：按 Cook Lean R 赋值"),
    ("密歇根", "D", 4.0, "假设：按 Cook Lean D 赋值"),
    ("新罕布什尔", "D", 4.0, "假设：按 Lean D 赋值"),
    ("佐治亚", "D", 7.0, "假设：按 Cook Likely D 赋值"),
]
NATIONAL_SD = 3.5
STATE_SD = 4.5
N = 200_000


def simulate(shift=0.0, seed=2026):
    rnd = random.Random(seed)
    dist = {}
    wins = {r[0]: 0 for r in RACES}
    control = 0
    for _ in range(N):
        nat = rnd.gauss(shift, NATIONAL_SD)
        net = 0
        for name, inc, m, _ in RACES:
            d_win = m + nat + rnd.gauss(0, STATE_SD) > 0
            wins[name] += d_win
            if inc == "R" and d_win:
                net += 1
            elif inc == "D" and not d_win:
                net -= 1
        dist[net] = dist.get(net, 0) + 1
        control += net >= 4
    return {
        "p_control": round(control / N, 3),
        "dist": {k: round(v / N, 4) for k, v in sorted(dist.items())},
        "race_p": {k: round(v / N, 3) for k, v in wins.items()},
    }


def main():
    base = simulate()
    sens = {str(s): simulate(s)["p_control"] for s in (-3, -2, -1, 0, 1, 2, 3)}
    out = {"races": [{"state": r[0], "inc": r[1], "margin": r[2], "source": r[3],
                      "p_d": base["race_p"][r[0]]} for r in RACES],
           "national_sd": NATIONAL_SD, "state_sd": STATE_SD, "n": N,
           "p_control": base["p_control"], "dist": base["dist"], "sensitivity": sens}
    with open(os.path.join(ROOT, "data", "senate_sim.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
