"""KRX 수집기 (pykrx)

받는 것
  kospi_index.csv      : 종가, 거래량, 거래대금, 시가총액
  kospi_valuation.csv  : PER, 선행PER, PBR, 배당수익률
  krx_investor.csv     : 투자자별 순매수 금액 (원)

pykrx 1.2 이상은 KRX 로그인이 필요하다. 환경변수 KRX_ID, KRX_PW 를 설정한다.
"""
from __future__ import annotations

import time

import pandas as pd

from .common import log, upsert_csv, last_date

KOSPI = "1001"


def _chunks(start: str, end: str):
    """연 단위로 조회 구간을 쪼갠다."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    for y in range(s.year, e.year + 1):
        a = max(s, pd.Timestamp(f"{y}-01-01")).strftime("%Y%m%d")
        b = min(e, pd.Timestamp(f"{y}-12-31")).strftime("%Y%m%d")
        if a <= b:
            yield a, b


def collect(start: str, end: str | None = None, pause: float = 1.0) -> dict:
    from pykrx import stock

    end = end or pd.Timestamp.today().strftime("%Y%m%d")
    ohlcv, fund, flow = [], [], []
    for a, b in _chunks(start, end):
        log.info("KRX %s ~ %s", a, b)
        ohlcv.append(stock.get_index_ohlcv_by_date(a, b, KOSPI))
        time.sleep(pause)
        fund.append(stock.get_index_fundamental_by_date(a, b, KOSPI))
        time.sleep(pause)
        flow.append(stock.get_market_trading_value_by_date(a, b, "KOSPI"))
        time.sleep(pause)

    o = pd.concat(ohlcv)
    idx = pd.DataFrame({"close": o["종가"], "volume": o["거래량"],
                        "value": o["거래대금"], "mcap": o.get("상장시가총액")})
    idx.index.name = "date"

    f = pd.concat(fund)
    val = pd.DataFrame({"per": f["PER"], "fwd_per": f.get("선행PER"),
                        "pbr": f["PBR"], "div_yield": f["배당수익률"]})
    val.index.name = "date"

    v = pd.concat(flow)
    inv = pd.DataFrame({"foreign": v["외국인합계"], "inst": v["기관합계"],
                        "indiv": v["개인"], "corp": v.get("기타법인")})
    inv.index.name = "date"

    return {"kospi_index.csv": idx.dropna(how="all"),
            "kospi_valuation.csv": val.dropna(how="all"),
            "krx_investor.csv": inv.dropna(how="all")}


def run(start: str | None = None, days_back: int = 20) -> None:
    """증분 수집. start 를 주면 그 날짜부터 전체를 다시 받는다(백필)."""
    if start is None:
        prev = last_date("kospi_index.csv")
        start = ((prev - pd.Timedelta(days=days_back)) if prev is not None
                 else pd.Timestamp("2008-01-01")).strftime("%Y%m%d")
    for name, df in collect(start).items():
        upsert_csv(name, df)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else None)
