"""네이버 금융 수집기 — 투자자별 매매동향 (로그인 불필요)

KRX 로그인이 막히거나 pykrx가 고장났을 때의 대체 소스이자,
연기금·금융투자·투신 등 세부 주체를 따로 보기 위한 소스.
단위는 억원, KRX(원)와 단위가 다르므로 섞어 쓰지 않는다.

kospi_investor_naver.csv / kosdaq_investor_naver.csv
"""
from __future__ import annotations

import re
import time

import pandas as pd
from bs4 import BeautifulSoup

from .common import http_get, log, upsert_csv, last_date

BASE = "https://finance.naver.com"
COLS = ["개인", "외국인", "기관계", "금융투자", "보험", "투신", "은행", "기타금융", "연기금등", "기타법인"]


def _num(s: str) -> float:
    s = s.strip().replace(",", "").replace("+", "")
    if s in ("", "-", "--"):
        return float("nan")
    try:
        return float(s)
    except ValueError:
        return float("nan")


def _date(s: str):
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", s.strip())
    return pd.Timestamp(2000 + int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def fetch_page(market: str = "KOSPI", page: int = 1, bizdate: str | None = None) -> pd.DataFrame:
    sosok = "" if market.upper() == "KOSPI" else "1"
    bizdate = bizdate or pd.Timestamp.today().strftime("%Y%m%d")
    url = f"{BASE}/sise/investorDealTrendDay.naver?bizdate={bizdate}&sosok={sosok}&type=0&page={page}"
    html = http_get(url, encoding="euc-kr", headers={"Referer": f"{BASE}/sise/"}).text
    table = BeautifulSoup(html, "html.parser").find("table", class_="type_1")
    if table is None:
        return pd.DataFrame()
    rows = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 11:
            continue
        d = _date(tds[0].get_text(strip=True))
        if d is not None:
            rows.append([d] + [_num(td.get_text(strip=True)) for td in tds[1:11]])
    return pd.DataFrame(rows, columns=["date"] + COLS) if rows else pd.DataFrame()


def collect(market: str = "KOSPI", since: pd.Timestamp | None = None,
            max_pages: int = 8, max_rounds: int = 400) -> pd.DataFrame:
    """bizdate 를 과거로 옮겨 가며 since 날짜에 닿을 때까지 수집."""
    since = since or (pd.Timestamp.today() - pd.Timedelta(days=30))
    bizdate, frames = None, []
    for _ in range(max_rounds):
        got = []
        for p in range(1, max_pages + 1):
            df = fetch_page(market, p, bizdate)
            if df.empty:
                break
            got.append(df)
            time.sleep(0.2)
        if not got:
            break
        chunk = pd.concat(got, ignore_index=True)
        frames.append(chunk)
        oldest = chunk["date"].min()
        log.info("네이버 %s %s 까지 수집", market, oldest.date())
        if oldest <= since:
            break
        bizdate = (oldest - pd.Timedelta(days=1)).strftime("%Y%m%d")
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["date"]).sort_values("date")
    return out[out["date"] >= since]


def run(start: str | None = None, days_back: int = 20, markets=("KOSPI", "KOSDAQ")) -> None:
    for m in markets:
        name = f"{m.lower()}_investor_naver.csv"
        if start:
            since = pd.Timestamp(start)
        else:
            prev = last_date(name)
            since = (prev - pd.Timedelta(days=days_back)) if prev is not None else pd.Timestamp("2008-01-01")
        df = collect(m, since)
        if not df.empty:
            upsert_csv(name, df)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else None)
