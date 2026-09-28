"""최근 한 달 시그널 지표·권고 포지션·코스피를 한 장의 차트로 만든다."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.patches import Patch

from collectors.common import DATA

OUT = Path("/tmp/signal_chart.png")
KO_FONTS = ["NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR",
            "Malgun Gothic", "AppleGothic"]

# (하한, 상한, 색, 투명도, 한글 라벨, 영문 라벨)
ZONES = [
    (5, 10, "#2e8b57", 0.16, "적극 매수", "Strong buy"),
    (2, 5, "#7cb342", 0.14, "매수 우위", "Buy"),
    (-2, 2, "#9aa0a6", 0.10, "중립", "Neutral"),
    (-5, -2, "#e8871a", 0.13, "방어", "Defensive"),
    (-10, -5, "#c0392b", 0.15, "위험", "Risk-off"),
]


def _smooth(y, k: int = 12):
    """Catmull-Rom 스플라인으로 점 사이를 부드럽게 잇는다 (외부 의존성 없음)."""
    import numpy as np
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return np.arange(n, dtype=float), y
    p = np.concatenate([[y[0]], y, [y[-1]]])
    xs, ys = [], []
    t = np.linspace(0, 1, k, endpoint=False)
    for i in range(n - 1):
        p0, p1, p2, p3 = p[i], p[i + 1], p[i + 2], p[i + 3]
        seg = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                     + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
        xs.append(i + t); ys.append(seg)
    xs.append([n - 1.0]); ys.append([y[-1]])
    return np.concatenate(xs), np.concatenate(ys)


def _font() -> bool:
    have = {f.name for f in fm.fontManager.ttflist}
    for name in KO_FONTS:
        if name in have:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return True
    return False


def _color(v: float) -> str:
    for lo, hi, c, _, _, _ in ZONES:
        if v >= lo:
            return c
    return ZONES[-1][2]


def make(days: int = 30) -> Path | None:
    path = DATA / "daily_index.csv"
    if not path.exists():
        return None
    d = pd.read_csv(path, parse_dates=["date"]).set_index("date").sort_index()
    d = d[d.index >= d.index[-1] - pd.Timedelta(days=days)]
    if len(d) < 5:
        return None
    ko = _font()
    T = ({"head": f"KOSPI 시그널 지표  최근 {days}일", "idx": "시그널 지표",
          "pos": "권고 포지션", "price": "코스피", "x1": "1배 전략", "x2": "2배 전략"}
         if ko else
         {"head": f"KOSPI Signal Index  last {days} days", "idx": "Signal index",
          "pos": "Position", "price": "KOSPI", "x1": "1x", "x2": "2x"})

    fig, ax = plt.subplots(3, 1, figsize=(8, 8.4), sharex=True,
                           gridspec_kw={"height_ratios": [1.25, 0.8, 1.0], "hspace": 0.16})

    # ① 시그널 지표 — Y축 구간 배경색 + 부드러운 곡선 + 값 라벨
    import numpy as np
    ix = d["index"]
    for lo, hi, c, al, _, _ in ZONES:
        ax[0].axhspan(lo, hi, color=c, alpha=al, lw=0, zorder=0)
        ax[0].axhline(lo, lw=0.5, color="white", zorder=1)
    xi = np.arange(len(ix))
    sx, sy = _smooth(ix.values)
    num = mdates.date2num(d.index.to_pydatetime())
    ax[0].plot(np.interp(sx, xi, num), np.clip(sy, -10, 10), color="#1f2937", lw=1.8, zorder=3)
    ax[0].scatter(d.index, ix, s=26, color=[_color(v) for v in ix],
                  edgecolor="white", linewidth=0.8, zorder=4)
    for i, (dt, v) in enumerate(ix.items()):
        up = i == 0 or v >= ix.iloc[i - 1]
        ax[0].annotate(f"{v:.1f}", (dt, v), textcoords="offset points",
                       xytext=(0, 7 if up else -12), ha="center", fontsize=6.5,
                       color="#374151", zorder=5)
    ax[0].axhline(0, lw=0.9, color="#4b5563", zorder=2)
    ax[0].set_ylim(-10, 10)
    ax[0].set_yticks([-10, -5, -2, 0, 2, 5, 10])
    ax[0].set_ylabel(T["idx"])
    ax[0].set_title(T["head"], fontsize=12, loc="left", pad=16)
    ax[0].legend(handles=[Patch(facecolor=c, alpha=min(al * 3, 0.6), label=(kl if ko else el))
                          for _, _, c, al, kl, el in ZONES],
                 fontsize=7.5, frameon=False, ncol=5, loc="lower center",
                 bbox_to_anchor=(0.5, 1.0), handlelength=1.1, columnspacing=1.0)

    # ② 권고 포지션 (지표는 하나, 비중 산식만 다름)
    c1 = d["1배_Daily"] if "1배_Daily" in d else d.get("코스피포지션")
    c2 = d["2배_Daily"] if "2배_Daily" in d else d.get("레버리지포지션")
    ax[1].step(d.index, c1 * 100, where="post", lw=1.6, color="#2e8b57", label=T["x1"])
    ax[1].step(d.index, c2 * 100, where="post", lw=1.6, color="#8e44ad", label=T["x2"])
    ax[1].fill_between(d.index, 0, c1 * 100, step="post", color="#2e8b57", alpha=0.10)
    for series, col in [(c1, "#2e8b57"), (c2, "#8e44ad")]:
        last = float(series.iloc[-1]) * 100
        ax[1].scatter([d.index[-1]], [last], s=46, color=col, edgecolor="white",
                      linewidth=1.2, zorder=5)
        ax[1].annotate(f"{last:.0f}%", (d.index[-1], last), textcoords="offset points",
                       xytext=(10, -3), ha="left", va="center",
                       fontsize=9, fontweight="bold", color=col, zorder=6,
                       annotation_clip=False)
    ax[1].set_ylim(-6, 108)
    ax[1].set_ylabel(T["pos"] + " (%)")
    ax[1].legend(fontsize=8, frameon=False, ncol=2, loc="upper left")

    # ③ 코스피
    ax[2].plot(d.index, d["close"], color="#1f2937", lw=1.6)
    ax[2].fill_between(d.index, d["close"].min() * 0.995, d["close"], color="#1f2937", alpha=0.06)
    ax[2].set_ylabel(T["price"])
    ax[2].annotate(f"{d['close'].iloc[-1]:,.0f}", (d.index[-1], d["close"].iloc[-1]),
                   textcoords="offset points", xytext=(-6, 8), ha="right", fontsize=10, fontweight="bold")
    span = d.index[-1] - d.index[0]
    ax[2].set_xlim(d.index[0] - span * 0.02, d.index[-1] + span * 0.10)
    ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%m/%d"))
    ax[2].xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO))

    for a in ax:
        a.grid(alpha=0.25)
        a.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate(rotation=0, ha="center")
    fig.subplots_adjust(left=0.10, right=0.97, top=0.92, bottom=0.08)
    fig.savefig(OUT, dpi=140)
    plt.close(fig)
    return OUT
