"""수집된 CSV를 합쳐 지수와 주문을 만든다.

포지션 방식: 총자산(주식 평가액 + 현금) 대비 몇 %를 들고 있어야 하는지를 알려준다.
  월요일 마감 신호 → 화요일 종가에 그 비중으로 맞춘다 (10%p 미만 변화는 건너뜀)

출력
  data/daily_index.csv     일별 지수·구성요소·목표/현재 포지션
  data/latest_signal.json  최신 신호 요약
"""
from __future__ import annotations

import json

import pandas as pd

from collectors.common import DATA, load_csv, log
from index.model import compute_index, backtest, stats

def build_daily() -> pd.DataFrame:
    idx = load_csv("kospi_index.csv")
    if idx.empty:
        raise RuntimeError("kospi_index.csv 가 없습니다. 먼저 수집을 실행하세요.")
    d = pd.DataFrame({"close": idx["close"], "value": idx["value"]})
    if "mcap" in idx:
        d["mcap"] = idx["mcap"]
    inv = load_csv("krx_investor.csv")
    if not inv.empty:
        d = d.join(inv[["foreign", "inst", "indiv"]])
    val = load_csv("kospi_valuation.csv")
    if not val.empty:
        d = d.join(val[["pbr", "per"]])
    k = load_csv("kofia_funds.csv")
    if not k.empty:
        d = d.join(k[["deposits", "credit", "forced"]] * 1e6)
    fx = load_csv("fx_usdkrw.csv")
    if not fx.empty:
        d["usdkrw"] = fx["usdkrw"].reindex(d.index).ffill(limit=5)
    d = d.dropna(subset=["close", "value"])
    log.info("입력 %d행 (%s ~ %s)", len(d), d.index[0].date(), d.index[-1].date())
    return d


def run(today: pd.Timestamp | None = None) -> dict:
    daily = build_daily()
    idx = compute_index(daily)
    idx.to_csv(DATA / "daily_index.csv", encoding="utf-8-sig")

    start = idx["코스피포지션"].replace(0, pd.NA).dropna().index[0]
    perf = {}
    r1, h1 = backtest(daily, idx, "코스피포지션")
    perf["1배 포지션"] = {k: round(float(v), 3) for k, v in stats(r1[start:], h1[start:]).items()}
    r2, h2 = backtest(daily, idx, "레버리지포지션", multiplier=2.0, leveraged=True)
    perf["2배 포지션"] = {k: round(float(v), 3) for k, v in stats(r2[start:], h2[start:]).items()}
    bh = daily["close"].pct_change().fillna(0)
    perf["단순보유"] = {k: round(float(v), 3) for k, v in stats(bh[start:]).items()}

    cur = idx.iloc[-1]
    today = today or pd.Timestamp.today().normalize()
    comp = [c for c in ["기관수급", "외인수급", "신용부담", "증시연료", "패닉", "밸류", "환율"] if c in idx.columns]
    out = {
        "기준일": str(idx.index[-1].date()),
        "종가": round(float(cur["close"]), 2),
        "지수": float(cur["index"]),
        "현재포지션_1배": float(cur["코스피포지션"]),
        "현재포지션_2배": float(cur["레버리지포지션"]),
        "다음조정_1배": float(cur["코스피목표"]),
        "다음조정_2배": float(cur["레버리지목표"]),
        "조정일": "다음 화요일 종가",
        "월요일": today.dayofweek == 0,
        "가드": bool(cur["가드"]),
        "급락매수": bool(cur["급락매수"]),
        "구성": {c: float(cur[c]) for c in comp if pd.notna(cur[c])},
        "성과": perf,
    }
    (DATA / "latest_signal.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("신호 %s", out)
    return out


if __name__ == "__main__":
    run()
