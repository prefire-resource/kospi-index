"""
주간 트레이딩 지수 v2 (-10 ~ +10) — 금요일 마감 후 1회 산출, 2~3개월 보유 전제

v1과 달라진 점
- 추세(이동평균·모멘텀)를 점수에서 뺌: 2011~2019 박스장에선 역방향으로 작동해 성과를 깎았음
- 두 장세(2011~19, 2020~26)에서 모두 같은 방향으로 작동한 신용·예탁금·패닉 지표로 점수 구성
- 수급은 점수(25%)와 '하락 조기경보 가드'로 사용
- 가격 급락 가드 추가: 조건 충족 시 지수와 무관하게 즉시 현금

필요 데이터(일별)
  close, value(거래대금)                     : KRX 지수
  deposits(투자자예탁금), credit(신용융자),
  forced(반대매매금액)                       : 금융투자협회 freesis.kofia.or.kr '증시자금추이'
  foreign, inst, indiv(순매수 금액)          : KRX 투자자별 거래실적 (없으면 수급 요소·가드 비활성)
"""
import numpy as np
import pandas as pd

P = dict(
    z_win=156, z_min=52,            # 환경 지표 정규화 (최대 3년)
    fz_win=104, fz_min=26,          # 수급 정규화 (최대 2년)
    w_flow=0.25,                    # 수급 비중
    entry=3.0, exit=0.0, hard_exit=-3.0, min_hold=8,
    guard_dd=-0.08, guard_vol=1.8, guard_flow=-0.5,
    cost=0.0015,                    # 편도 거래비용
)


def _z(s, win, mn):
    r = s.rolling(win, min_periods=mn)
    return ((s - r.mean()) / r.std()).clip(-3, 3)


def to_weekly(d):
    ret = d["close"].pct_change()
    w = d.resample("W-FRI").last()
    w["last_date"] = pd.Series(d.index, index=d.index).resample("W-FRI").last()
    for c in ["value", "forced", "foreign", "inst", "indiv"]:
        if c in d:
            w[c] = d[c].resample("W-FRI").sum(min_count=1)
    w["rv"] = (ret.rolling(20).std() * np.sqrt(252)).resample("W-FRI").last()
    w = w.dropna(subset=["close"])
    if len(w) and w.index[-1] > d.index[-1] and d.index[-1].dayofweek < 4:
        w = w.iloc[:-1]                                   # 끝나지 않은 주 제외
    return w


def compute_index(daily, p=P):
    w = to_weekly(daily)
    z = lambda s: _z(s, p["z_win"], p["z_min"])
    c = w["close"]
    dd13 = c / c.rolling(13).max() - 1
    volratio = w["rv"] / w["rv"].rolling(p["z_win"], min_periods=p["z_min"]).median()
    ma10 = c.rolling(10).mean()

    comp = pd.DataFrame(index=w.index)
    # ① 레버리지 과열: 예탁금 대비 신용융자가 높을수록 (-)
    comp["신용과열"] = -z(w["credit"] / w["deposits"])
    # ② 패닉: 13주 고점 대비 급락 + 변동성 확대가 동시에 나오면 (+) → 바닥 조기 포착
    comp["패닉"] = z(volratio).clip(lower=0) * np.tanh(-dd13 / 0.08)
    # ③ 증시 연료: 예탁금 증가율 − 신용 증가율 (+)
    comp["연료"] = z(w["deposits"].pct_change(13, fill_method=None) - w["credit"].pct_change(13, fill_method=None))
    # ④ 반대매매 급증 (+) → 강제청산 물량 소화 후 반등
    comp["반대매매"] = z(w["forced"].rolling(4).sum() / w["credit"])
    S = comp.mean(axis=1, skipna=False)

    flow = pd.Series(np.nan, index=w.index)
    if {"foreign", "inst", "indiv"} <= set(w.columns):
        fz = lambda s: _z(s, p["fz_win"], p["fz_min"])
        v4 = w["value"].rolling(4).sum()
        flow = (0.50 * fz(w["foreign"].rolling(4).sum() / v4)
                + 0.35 * fz(w["inst"].rolling(4).sum() / v4)
                - 0.15 * fz(w["indiv"].rolling(4).sum() / v4))
        comp["수급"] = flow
        S = ((1 - p["w_flow"]) * S + p["w_flow"] * flow).where(flow.notna(), S)

    out = comp.round(2)
    out.insert(0, "close", c)
    out.insert(0, "last_date", w["last_date"])
    out["index"] = (10 * np.tanh(S)).round(2)
    out["가드_가격"] = ((c < ma10) & (dd13 < p["guard_dd"]) & (volratio > p["guard_vol"])).fillna(False)
    out["가드_수급"] = ((flow.rolling(2).max() < p["guard_flow"]) & (dd13 < p["guard_dd"])).fillna(False)

    # 포지션 상태 (금요일 신호 → 다음 거래일 종가 체결)
    state, k, sig = 0, 0, []
    for v in out["index"]:
        if np.isnan(v):
            sig.append(np.nan); continue
        if state == 0 and v >= p["entry"]:
            state, k = 1, 0
        elif state == 1:
            k += 1
            if v <= p["hard_exit"] or (k >= p["min_hold"] and v < p["exit"]):
                state = 0
        sig.append(float(state))
    out["보유신호"] = sig
    out["포지션"] = out["보유신호"].where(~(out["가드_가격"] | out["가드_수급"]), 0.0)
    return out


def backtest(daily, idx, p=P):
    close = daily["close"]; dates = close.index
    pos = pd.Series(np.nan, index=dates)
    for _, row in idx.dropna(subset=["포지션"]).iterrows():
        i = dates.searchsorted(row["last_date"], side="right")
        if i < len(dates):
            pos.iloc[i] = row["포지션"]
    pos = pos.ffill().fillna(0)
    held = pos.shift(1).fillna(0)
    ret = held * close.pct_change().fillna(0) - pos.diff().abs().fillna(0) * p["cost"]
    chg = pos.diff().fillna(pos.iloc[0])
    ent, ex = dates[chg > 0], dates[chg < 0]
    trades = []
    for e in ent:
        x = ex[ex > e]
        x = x[0] if len(x) else dates[-1]
        trades.append((e.date(), x.date(), (x - e).days, close[x] / close[e] - 1))
    return ret, held, pd.DataFrame(trades, columns=["매수일", "매도일", "보유일수", "수익률"])


def stats(ret, held=None):
    eq = (1 + ret).cumprod()
    yrs = (ret.index[-1] - ret.index[0]).days / 365.25
    vol = ret.std() * np.sqrt(252)
    d = {"총수익": eq.iloc[-1] - 1, "연수익(CAGR)": eq.iloc[-1] ** (1 / yrs) - 1,
         "최대낙폭": (eq / eq.cummax() - 1).min(), "샤프": ret.mean() * 252 / vol}
    if held is not None:
        d["투자비중"] = held.mean()
    return d
