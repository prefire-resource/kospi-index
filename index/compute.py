"""수집 데이터 → 시그널 지표와 두 가지 운용 포지션을 산출한다.

Daily Position  : 매일 지표를 반영. 전일 마감 신호 → 당일 종가로 조정
Weekly Position : 월요일 마감 신호 → 화요일 종가로 조정, 그 주 내내 유지
두 방식 모두 총자산(주식 평가액 + 현금) 대비 비중이며 10%p 미만 변화는 조정하지 않는다.

출력
  data/daily_index.csv     일별 지표·구성요소·포지션
  data/performance.csv     네 전략 + 단순보유의 일별 수익·누적 기록
  data/live_start.json     실전 운용 시작일 (최초 실행 시 자동 생성)
  data/latest_signal.json  최신 신호 요약
"""
from __future__ import annotations

import json

import pandas as pd

from collectors.common import DATA, load_csv, log
from index.model import compute_index, backtest, stats

COMP = ["기관수급", "외인수급", "신용부담", "증시연료", "패닉", "밸류", "환율"]
LABEL = {"기관수급": "기관 수급", "외인수급": "외국인 수급", "신용부담": "신용/예탁금",
         "증시연료": "증시 자금", "패닉": "패닉 지표", "밸류": "밸류에이션", "환율": "원/달러"}


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


STRATS = [("Daily 1배", "1배_Daily", 1.0, False), ("Daily 2배", "2배_Daily", 2.0, True),
          ("Weekly 1배", "1배_Weekly", 1.0, False), ("Weekly 2배", "2배_Weekly", 2.0, True)]
LIVE = DATA / "live_start.json"


def _summary(ret, held, start):
    s = stats(ret[start:], held[start:] if held is not None else None)
    o = {"연수익": round(float(s["연수익(CAGR)"]), 4), "총수익": round(float(s["총수익"]), 4),
         "최대낙폭": round(float(s["최대낙폭"]), 4), "샤프": round(float(s["샤프"]), 2)}
    if held is not None:
        o["평균비중"] = round(float(s["평균비중"]), 3)
    return o


def run(today: pd.Timestamp | None = None) -> dict:
    daily = build_daily()
    idx = compute_index(daily)
    idx.to_csv(DATA / "daily_index.csv", encoding="utf-8-sig")

    # 모든 구성요소의 정규화 창이 채워진 뒤부터 성과를 집계한다
    first = idx["1배_Daily"].replace(0, pd.NA).dropna().index[0]
    start = max(first, pd.Timestamp("2010-01-01"))
    bh = daily["close"].pct_change().fillna(0)
    rets, perf, hist = {}, {}, pd.DataFrame({"close": daily["close"], "지표": idx["index"]})
    for name, col, mult, lev in STRATS:
        ret, held = backtest(daily, idx, column=col, multiplier=mult, leveraged=lev)
        rets[name] = ret
        perf[name] = _summary(ret, held, start)
        hist[f"{name} 포지션"] = idx[col]
        hist[f"{name} 일수익"] = ret.round(6)
        hist[f"{name} 누적"] = (1 + ret[start:]).cumprod().round(4)
    perf["단순보유"] = _summary(bh, None, start)
    hist["단순보유 일수익"] = bh.round(6)
    hist["단순보유 누적"] = (1 + bh[start:]).cumprod().round(4)
    hist[start:].to_csv(DATA / "performance.csv", encoding="utf-8-sig")

    # 실전 기록: 이 시스템이 처음 돌아간 날부터의 성과
    live = None
    if LIVE.exists():
        live_start = pd.Timestamp(json.loads(LIVE.read_text(encoding="utf-8"))["시작일"])
        if (idx.index[-1] - live_start).days >= 7:
            live = {"시작일": str(live_start.date()),
                    "경과일": int((idx.index[-1] - live_start).days)}
            for name, _, _, _ in STRATS:
                live[name] = round(float((1 + rets[name][live_start:]).prod() - 1), 4)
            live["단순보유"] = round(float((1 + bh[live_start:]).prod() - 1), 4)
    else:
        LIVE.write_text(json.dumps({"시작일": str(idx.index[-1].date())}, ensure_ascii=False),
                        encoding="utf-8")

    cur, prev = idx.iloc[-1], idx.iloc[-2]
    today = today or pd.Timestamp.today().normalize()
    chg = float(daily["close"].pct_change().iloc[-1])
    out = {
        "기준일": str(idx.index[-1].date()),
        "종가": round(float(cur["close"]), 2),
        "등락률": round(chg * 100, 2),
        "지표": float(cur["index"]),
        "지표변화": round(float(cur["index"]) - float(prev["index"]), 2),
        "daily": {"1배": float(cur["1배_Daily"]), "2배": float(cur["2배_Daily"]),
                  "직전_1배": float(prev["1배_Daily"]), "직전_2배": float(prev["2배_Daily"])},
        "weekly": {"1배": float(cur["1배_Weekly"]), "2배": float(cur["2배_Weekly"]),
                   "직전_1배": float(prev["1배_Weekly"]), "직전_2배": float(prev["2배_Weekly"]),
                   "다음조정_1배": float(cur["코스피목표"]), "다음조정_2배": float(cur["레버리지목표"]),
                   "조정일": today.dayofweek == 0},
        "가드": bool(cur["가드"]),
        "급락매수": bool(cur["급락매수"]),
        "구성": {LABEL[c]: round(float(cur[c]), 1) for c in COMP if c in idx.columns and pd.notna(cur[c])},
        "성과": perf,
        "실전": live,
        "검증기간": f"{start.date()} ~ {idx.index[-1].date()}",
    }
    (DATA / "latest_signal.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("신호 %s / %s", out["기준일"], out["지표"])
    return out


if __name__ == "__main__":
    run()
