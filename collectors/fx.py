"""환율 수집기 — Frankfurter (ECB 고시, 무료·키 불필요)

fx_usdkrw.csv : date, usdkrw  (1999년 이후 영업일)
"""
from __future__ import annotations

import pandas as pd

from .common import http_get, log, upsert_csv, last_date

# 주소 형식이 바뀐 적이 있어 후보를 순서대로 시도한다
URLS = [
    "https://api.frankfurter.dev/v1/{frm}..{to}?base=USD&symbols=KRW",
    "https://api.frankfurter.app/{frm}..{to}?from=USD&to=KRW",
    "https://api.frankfurter.app/{frm}..{to}?base=USD&symbols=KRW",
]


def _fetch(frm: str, to: str) -> dict:
    last = None
    for tpl in URLS:
        try:
            js = http_get(tpl.format(frm=frm, to=to), retries=2).json()
            if js.get("rates"):
                return js["rates"]
        except Exception as e:      # 다음 후보로
            last = e
    log.warning("환율 조회 실패 %s~%s: %s", frm, to, last)
    return {}


def collect(start: str, end: str | None = None) -> pd.DataFrame:
    s = pd.Timestamp(start); e = pd.Timestamp(end) if end else pd.Timestamp.today()
    rows = {}
    for y in range(s.year, e.year + 1):                  # 연 단위로 나눠 요청
        a = max(s, pd.Timestamp(f"{y}-01-01")).strftime("%Y-%m-%d")
        b = min(e, pd.Timestamp(f"{y}-12-31")).strftime("%Y-%m-%d")
        for day, val in _fetch(a, b).items():
            if isinstance(val, dict) and "KRW" in val:
                rows[day] = val["KRW"]
        log.info("환율 %s: 누적 %d행", y, len(rows))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame({"date": pd.to_datetime(list(rows)), "usdkrw": list(rows.values())}).sort_values("date")


def run(start: str | None = None, days_back: int = 20) -> None:
    if start is None:
        prev = last_date("fx_usdkrw.csv")
        start = ((prev - pd.Timedelta(days=days_back)) if prev is not None
                 else pd.Timestamp("2007-01-01")).strftime("%Y-%m-%d")
    else:
        start = pd.Timestamp(start).strftime("%Y-%m-%d")
    df = collect(start)
    if df.empty:
        raise RuntimeError("환율 데이터를 받지 못했습니다")
    upsert_csv("fx_usdkrw.csv", df)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else None)
