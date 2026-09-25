"""수집된 CSV를 합쳐 주간 지수와 매매 신호를 계산한다.

출력
  data/weekly_index.csv  주차별 지수·구성요소·가드·포지션
  data/latest_signal.json 최신 주차 요약 (알림용)
"""
from __future__ import annotations

import json

import pandas as pd

from collectors.common import DATA, load_csv, log
from index.model import compute_index, backtest, stats


def build_daily() -> pd.DataFrame:
    """일별 입력 데이터 구성. 금액 단위는 원으로 통일."""
    idx = load_csv("kospi_index.csv")
    if idx.empty:
        raise RuntimeError("kospi_index.csv 가 없습니다. 먼저 수집을 실행하세요.")
    d = pd.DataFrame({"close": idx["close"], "value": idx["value"]})
    if "mcap" in idx:
        d["mcap"] = idx["mcap"]

    inv = load_csv("krx_investor.csv")
    if not inv.empty:
        d = d.join(inv[["foreign", "inst", "indiv"]])
    else:                                            # KRX 실패 시 네이버(억원) 사용
        nv = load_csv("kospi_investor_naver.csv")
        if not nv.empty:
            d = d.join((nv[["외국인", "기관계", "개인"]] * 1e8)
                       .rename(columns={"외국인": "foreign", "기관계": "inst", "개인": "indiv"}))
            log.warning("KRX 수급 데이터가 없어 네이버 데이터를 사용했습니다.")

    k = load_csv("kofia_funds.csv")
    if k.empty:
        raise RuntimeError("kofia_funds.csv 가 없습니다. 예탁금·신용 데이터가 있어야 지수를 계산합니다.")
    d = d.join(k[["deposits", "credit", "forced"]] * 1e6)

    val = load_csv("kospi_valuation.csv")
    if not val.empty:                                # PBR 은 v3 에서 점수에 반영 예정
        d = d.join(val[["pbr", "per"]])

    d = d.dropna(subset=["close", "value", "deposits", "credit", "forced"])
    log.info("입력 데이터 %d행 (%s ~ %s)", len(d), d.index[0].date(), d.index[-1].date())
    return d


def run() -> dict:
    daily = build_daily()
    idx = compute_index(daily)
    if "pbr" in daily:
        idx["pbr"] = daily["pbr"].resample("W-FRI").last().reindex(idx.index)
        win = min(len(idx), 520)
        idx["pbr_pct"] = (idx["pbr"].rolling(win, min_periods=104)
                          .rank(pct=True).round(2))
    idx.to_csv(DATA / "weekly_index.csv", encoding="utf-8-sig")

    ret, held, trades = backtest(daily, idx)
    start = idx.dropna(subset=["포지션"])["last_date"].iloc[0]
    perf = {"전략": stats(ret[start:], held[start:]),
            "단순보유": stats(daily["close"].pct_change().fillna(0)[start:])}

    cur = idx.dropna(subset=["포지션"]).iloc[-1]
    prev = idx.dropna(subset=["포지션"]).iloc[-2] if len(idx.dropna(subset=["포지션"])) > 1 else cur
    if cur["포지션"] == 1 and prev["포지션"] == 0:
        signal = "신규 매수"
    elif cur["포지션"] == 1:
        signal = "보유 유지"
    elif prev["포지션"] == 1:
        signal = "청산"
    else:
        signal = "관망"
    out = {
        "기준일": str(pd.Timestamp(cur["last_date"]).date()),
        "종가": round(float(cur["close"]), 2),
        "지수": float(cur["index"]),
        "신호": signal,
        "가드": ("가격" if cur["가드_가격"] else "") + ("수급" if cur["가드_수급"] else "") or "없음",
        "구성": {k: float(cur[k]) for k in ["신용과열", "패닉", "연료", "반대매매", "수급"] if k in idx.columns and pd.notna(cur[k])},
        "PBR": None if "pbr" not in idx.columns or pd.isna(cur.get("pbr")) else float(cur["pbr"]),
        "PBR백분위": None if "pbr_pct" not in idx.columns or pd.isna(cur.get("pbr_pct")) else float(cur["pbr_pct"]),
        "성과": {k: {kk: round(float(vv), 3) for kk, vv in v.items()} for k, v in perf.items()},
        "매매횟수": int(len(trades)),
    }
    (DATA / "latest_signal.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    trades.to_csv(DATA / "trades.csv", index=False, encoding="utf-8-sig")
    log.info("최신 신호: %s", out)
    return out


if __name__ == "__main__":
    run()
