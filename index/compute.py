"""수집된 CSV를 합쳐 지수와 주문을 만든다.

체결 규칙: 월요일 마감 신호 → 화요일 종가 매매 (매수 시점 통일)
  월요일 저녁  : 주문 안내 (기준금액의 몇 % 매수 / 보유금액의 몇 % 매도)
  화요일 저녁  : 체결된 것으로 보고 보유 비중 갱신
  그 외 요일   : 지수만 참고용으로 통지

출력
  data/daily_index.csv     일별 지수·구성요소·목표비중
  data/position.json       현재 보유 비중과 대기 주문
  data/latest_signal.json  최신 신호 요약
"""
from __future__ import annotations

import json

import pandas as pd

from collectors.common import DATA, load_csv, log
from index.model import compute_index, backtest, stats, make_order, P

STATE = DATA / "position.json"


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


def _state() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"코스피비중": 0.0, "레버리지비중": 0.0, "대기주문": None}


def run(today: pd.Timestamp | None = None) -> dict:
    daily = build_daily()
    idx = compute_index(daily)
    idx.to_csv(DATA / "daily_index.csv", encoding="utf-8-sig")

    start = idx["코스피비중"].dropna().index[0]
    perf = {}
    ret, held = backtest(daily, idx, column="코스피비중")
    perf["코스피 1배"] = {k: round(float(v), 3) for k, v in stats(ret[start:], held[start:]).items()}
    bh = daily["close"].pct_change().fillna(0)
    perf["단순보유"] = {k: round(float(v), 3) for k, v in stats(bh[start:]).items()}

    cur = idx.dropna(subset=["코스피비중"]).iloc[-1]
    sig_date = idx.dropna(subset=["코스피비중"]).index[-1]
    today = today or pd.Timestamp.today().normalize()
    st = _state()

    # 화요일이면 전날(월) 주문이 오늘 종가에 체결된 것으로 처리
    if today.dayofweek == 1 and st.get("대기주문"):
        st["코스피비중"] = st["대기주문"]["목표비중"]
        st["레버리지비중"] = st["대기주문"].get("레버리지목표", st.get("레버리지비중", 0.0))
        st["대기주문"] = None

    order = None
    if today.dayofweek == 0:                       # 월요일 저녁: 내일 화요일 종가 주문
        order = make_order(float(cur["코스피비중"]), float(st["코스피비중"]))
        order["레버리지목표"] = float(cur["레버리지비중"])
        st["대기주문"] = None if order["동작"] in ("유지", "관망") else order

    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

    comp = [c for c in ["기관수급", "외인수급", "신용부담", "증시연료", "패닉", "밸류", "환율"] if c in idx.columns]
    out = {
        "기준일": str(sig_date.date()),
        "종가": round(float(cur["close"]), 2),
        "지수": float(cur["index"]),
        "목표비중": float(cur["코스피비중"]),
        "현재비중": float(st["코스피비중"]),
        "레버리지목표": float(cur["레버리지비중"]),
        "주문": order,
        "체결일": "다음 화요일 종가" if order else None,
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
