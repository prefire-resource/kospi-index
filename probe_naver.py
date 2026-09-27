"""네이버 금융 투자자별 매매동향 주소 탐색.

기존 주소가 410(삭제)을 내서, 후보 주소들의 응답을 확인한다.
성공하는 주소를 찾으면 collectors/naver.py 를 그 주소로 고친다.
"""
from __future__ import annotations

import pandas as pd
import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
BIZ = pd.Timestamp.today().strftime("%Y%m%d")

CANDIDATES = [
    ("구 페이지(.naver)", f"https://finance.naver.com/sise/investorDealTrendDay.naver?bizdate={BIZ}&sosok=&type=0&page=1"),
    ("구 페이지(.nhn)", f"https://finance.naver.com/sise/investorDealTrendDay.nhn?bizdate={BIZ}&sosok=&type=0&page=1"),
    ("일별 시세 페이지", "https://finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=1"),
    ("지수 메인", "https://finance.naver.com/sise/sise_index.naver?code=KOSPI"),
    ("모바일 API 지수시세", "https://m.stock.naver.com/api/index/KOSPI/price?pageSize=10&page=1"),
    ("모바일 API 투자자", "https://m.stock.naver.com/api/index/KOSPI/investor?pageSize=10&page=1"),
    ("모바일 API 기본정보", "https://m.stock.naver.com/api/index/KOSPI/basic"),
    ("api.stock 투자자", "https://api.stock.naver.com/index/KOSPI/investor?pageSize=10&page=1"),
]


def probe(name: str, url: str) -> str:
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Referer": "https://finance.naver.com/"}, timeout=15)
        body = r.text[:180].replace("\n", " ").replace("\r", " ")
        mark = "OK " if r.ok else "   "
        return f"{mark}[{r.status_code}] {name}\n    {url}\n    {body}"
    except Exception as e:
        return f"   [ERR] {name}: {type(e).__name__} {str(e)[:100]}\n    {url}"


if __name__ == "__main__":
    for name, url in CANDIDATES:
        print(probe(name, url))
        print("-" * 80)
