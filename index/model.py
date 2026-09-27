"""주간 지수 v4 — 일별 산출, 단기 대응형 (-10 ~ +10)

v3와 구성 요소는 같지만 세 가지가 다르다.
  1) 매일 장 마감 후 산출한다 (주 1회 → 매일)
  2) 비중을 계단이 아니라 연속 함수로 정하고 5일 평균으로 다듬는다 (회전율·수수료 절감)
  3) 급락 매수 오버레이: 3일 -4% 이상 급락 + 변동성 확대 시 5일간 비중 +40%p

발표 시차를 반영한다. 금투협 자금지표는 2일, 수급·밸류·환율은 1일 지연시켜 쓰고,
신호는 다음 거래일 종가에 체결되는 것으로 계산한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

P = dict(
    z_win=250, z_min=120,           # 정규화 1년 창 (일별)
    pct_win=1250, pct_min=250,      # 밸류 백분위 5년 창
    weights=dict(기관수급=.25, 외인수급=.05, 신용부담=.25, 증시연료=.15,
                 패닉=.20, 밸류=.05, 환율=.05),
    # 1배 포지션 = base + tilt*지수/10 (총자산 대비, 0~100%)
    base=0.9, tilt=3.0, max_1x=1.0, smooth=5,
    # 2배(레버리지 ETF) 포지션 = lev_base + lev_tilt*지수/10 (총자산 대비, 0~100%)
    lev_base=0.5, lev_tilt=3.0, max_lev=1.0, lev_dip_add=0.20,
    step=0.10, band=0.10,                       # 10% 단위, 10%p 미만 변화는 조정하지 않음
    guard_dd=-0.08, guard_vol=1.8, guard_exposure=0.30,
    dip_ret=-0.04, dip_vol=1.2, dip_add=0.30, dip_days=5,
    cost=0.0015, lev_fee=0.01 / 252,
)


def _z(s, p=P):
    r = s.rolling(p["z_win"], min_periods=p["z_min"])
    return ((s - r.mean()) / r.std()).clip(-3, 3)


def compute_index(daily, p=P):
    d = daily.sort_index().copy()
    close = d["close"]
    lag = {c: 2 for c in ["deposits", "credit", "forced"]}
    lag.update({c: 1 for c in ["foreign", "inst", "indiv", "per", "pbr", "usdkrw", "value"]})
    L = pd.DataFrame({c: d[c].shift(k) for c, k in lag.items() if c in d})

    out = pd.DataFrame(index=d.index)
    C = pd.DataFrame(index=d.index)
    rv = close.pct_change().rolling(20).std() * np.sqrt(252)
    volratio = rv / rv.rolling(p["pct_win"], min_periods=p["pct_min"]).median()
    dd65 = close / close.rolling(65).max() - 1

    if {"inst", "foreign", "value"} <= set(L.columns):
        v20, v65 = L["value"].rolling(20).sum(), L["value"].rolling(65).sum()
        C["기관수급"] = 0.5 * _z(L["inst"].rolling(20).sum() / v20, p) + 0.5 * _z(L["inst"].rolling(65).sum() / v65, p)
        C["외인수급"] = 0.5 * _z(L["foreign"].rolling(20).sum() / v20, p) + 0.5 * _z(L["foreign"].rolling(65).sum() / v65, p)
    if {"credit", "deposits"} <= set(L.columns):
        cd = L["credit"] / L["deposits"]
        C["신용부담"] = -0.5 * _z(cd, p) - 0.5 * _z(cd.pct_change(65), p)
        C["증시연료"] = _z(L["deposits"].pct_change(65) - L["credit"].pct_change(65), p)
    C["패닉"] = _z(volratio, p).clip(lower=0) * np.tanh(-dd65 / 0.08)
    if {"pbr", "per"} <= set(L.columns):
        rk = lambda s: s.rolling(p["pct_win"], min_periods=p["pct_min"]).rank(pct=True)
        C["밸류"] = 1.5 * (0.6 * (1 - 2 * rk(L["pbr"])) + 0.4 * (1 - 2 * rk(L["per"])))
    if "usdkrw" in L.columns:
        C["환율"] = -_z(L["usdkrw"].pct_change(65), p)

    ws = pd.Series({k: v for k, v in p["weights"].items() if k in C.columns})
    ws = ws / ws.sum()
    S = (C[ws.index] * ws).sum(axis=1) / (C[ws.index].notna() * ws).sum(axis=1)
    ix = 10 * np.tanh(S)

    guard = ((close < close.rolling(50).mean()) & (dd65 < p["guard_dd"]) & (volratio > p["guard_vol"])).fillna(False)
    base = (p["base"] + p["tilt"] * ix / 10).clip(0, p["max_1x"]).where(~guard, p["guard_exposure"])
    base = base.rolling(p["smooth"]).mean()

    dip = ((close.pct_change(3) < p["dip_ret"]) & (volratio > p["dip_vol"])).fillna(False)
    add = pd.Series(0.0, index=d.index)
    for k in range(p["dip_days"]):
        add = np.maximum(add, dip.shift(k, fill_value=False).astype(float) * p["dip_add"])

    out["close"] = close
    for c in C.columns:
        out[c] = C[c].round(2)
    out["index"] = ix.round(2)
    out["가드"] = guard
    out["급락매수"] = add > 0
    out["코스피목표"] = _round_step((base + add).clip(0, p["max_1x"]), p)

    lev = (p["lev_base"] + p["lev_tilt"] * ix / 10).clip(0, p["max_lev"]).where(~guard, 0.0)
    lev = lev.rolling(p["smooth"]).mean()
    lev_add = add / p["dip_add"] * p["lev_dip_add"]
    out["레버리지목표"] = _round_step((lev + lev_add).clip(0, p["max_lev"]), p)

    # 실제 유지 포지션 — 두 가지 운용 방식
    #  Daily : 매일 반영 (전일 신호 → 당일 종가)
    #  Weekly: 월요일 신호 → 화요일 종가, 그 주 내내 유지
    out["1배_Daily"] = _applied(out["코스피목표"], p, "daily")
    out["2배_Daily"] = _applied(out["레버리지목표"], p, "daily")
    out["1배_Weekly"] = _applied(out["코스피목표"], p, "tue")
    out["2배_Weekly"] = _applied(out["레버리지목표"], p, "tue")
    out["코스피포지션"] = out["1배_Daily"]          # 하위호환
    out["레버리지포지션"] = out["2배_Daily"]
    return out


def _round_step(s, p=P):
    return ((s / p["step"]).round() * p["step"]).round(2)


def _applied(target, p=P, cadence="tue"):
    """월요일 마감 신호를 화요일 종가에 반영. 10%p 미만 변화는 건너뛴다."""
    dates = target.index
    cur, vals = 0.0, []
    for i, dt in enumerate(dates):
        if i:
            prev = target.iloc[i - 1]
            trade = True if cadence == "daily" else (
                dt.dayofweek == 1 or (dt.dayofweek > 1 and dates[i - 1].dayofweek > dt.dayofweek))
            if trade and not np.isnan(prev) and abs(prev - cur) >= p["band"] - 1e-9:
                cur = float(prev)
        vals.append(cur)
    return pd.Series(vals, index=dates).round(2)


def _round_step(s, p=P):
    return ((s / p["step"]).round() * p["step"]).round(2)


def _applied(target, p=P, cadence="tue"):
    """월요일 마감 신호를 화요일 종가에 반영. 10%p 미만 변화는 건너뛴다."""
    dates = target.index
    cur, vals = 0.0, []
    for i, dt in enumerate(dates):
        if i:
            prev = target.iloc[i - 1]
            trade = True if cadence == "daily" else (
                dt.dayofweek == 1 or (dt.dayofweek > 1 and dates[i - 1].dayofweek > dt.dayofweek))
            if trade and not np.isnan(prev) and abs(prev - cur) >= p["band"] - 1e-9:
                cur = float(prev)
        vals.append(cur)
    return pd.Series(vals, index=dates).round(2)


def make_order(target: float, current: float, p=P) -> dict:
    """목표 비중과 현재 비중을 비교해 실제 주문을 만든다.
    매수는 기준금액의 %, 매도는 보유금액의 % 로 표시한다."""
    if target is None or np.isnan(target):
        return {"동작": "관망", "설명": "신호 없음"}
    delta = round(target - current, 2)
    if abs(delta) < p["band"] - 1e-9:
        return {"동작": "유지", "변화": 0.0, "목표비중": target, "현재비중": current,
                "설명": f"목표 {target:.0%} 유지"}
    if delta > 0:
        extra = " (기준금액 초과분)" if target > 1.0 else ""
        return {"동작": "매수", "변화": delta, "목표비중": target, "현재비중": current,
                "설명": f"기준금액의 {delta:.0%} 매수 → 누적 {target:.0%}{extra}"}
    share = abs(delta) / current if current > 0 else 1.0
    return {"동작": "매도", "변화": delta, "목표비중": target, "현재비중": current,
            "매도비율": round(share, 2),
            "설명": f"보유금액의 {share:.0%} 매도 → 누적 {target:.0%}"}


def backtest(daily, idx, column="코스피포지션", multiplier=1.0, leveraged=False, p=P, cash_rate=0.0):
    """포지션 = 총자산 대비 비중. multiplier=2 면 2배 ETF (시장 노출 2배)."""
    close = daily["close"]
    pos = idx[column].reindex(close.index).ffill().fillna(0.0)
    held = pos.shift(1).fillna(0.0)
    ret = (held * multiplier * close.pct_change().fillna(0)
           + (1 - held) * cash_rate / 252
           - pos.diff().abs().fillna(0) * multiplier * p["cost"])
    if leveraged:
        ret = ret - held * abs(multiplier) * p["lev_fee"]
    return ret, held


def stats(ret, held=None):
    eq = (1 + ret).cumprod()
    yrs = (ret.index[-1] - ret.index[0]).days / 365.25
    vol = ret.std() * np.sqrt(252)
    o = {"총수익": eq.iloc[-1] - 1, "연수익(CAGR)": eq.iloc[-1] ** (1 / yrs) - 1,
         "최대낙폭": (eq / eq.cummax()).sub(1).min(), "샤프": ret.mean() * 252 / vol}
    if held is not None:
        o["평균비중"] = held.abs().mean()
        o["연회전율"] = held.diff().abs().sum() / (len(held) / 252)
    return o
