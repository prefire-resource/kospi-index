"""공통 유틸: HTTP 요청, CSV 누적 저장, 로깅."""
from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd
import requests

DATA = Path(__file__).resolve().parent.parent / "data"
DATA.mkdir(exist_ok=True)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")


def http_get(url: str, encoding: str | None = None, retries: int = 3, headers: dict | None = None):
    for i in range(retries):
        try:
            r = requests.get(url, headers={"User-Agent": UA, **(headers or {})}, timeout=20)
            r.raise_for_status()
            if encoding:
                r.encoding = encoding
            return r
        except requests.RequestException as e:
            if i == retries - 1:
                raise
            log.warning("재시도 %d/%d (%s): %s", i + 1, retries, url[:70], e)
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def http_post_json(url: str, payload: dict, retries: int = 3, headers: dict | None = None) -> dict:
    hdr = {"User-Agent": UA, "Content-Type": "application/json; charset=UTF-8", **(headers or {})}
    for i in range(retries):
        try:
            r = requests.post(url, json=payload, headers=hdr, timeout=30)
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            if i == retries - 1:
                raise
            log.warning("재시도 %d/%d (%s): %s", i + 1, retries, url[:70], e)
            time.sleep(2 * (i + 1))
    raise RuntimeError("unreachable")


def upsert_csv(name: str, df: pd.DataFrame, date_col: str = "date") -> Path:
    """기존 CSV에 새 데이터를 합친다. 같은 날짜는 새 값으로 덮어쓴다."""
    path = DATA / name
    df = df.copy()
    if date_col not in df.columns:
        df = df.reset_index().rename(columns={df.index.name or "index": date_col})
    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    if path.exists():
        old = pd.read_csv(path)
        old[date_col] = pd.to_datetime(old[date_col]).dt.strftime("%Y-%m-%d")
        df = pd.concat([old, df], ignore_index=True)
    df = df.drop_duplicates(subset=[date_col], keep="last").sort_values(date_col)
    df.to_csv(path, index=False, encoding="utf-8")
    log.info("%s 저장: %d행 (%s ~ %s)", name, len(df), df[date_col].iloc[0], df[date_col].iloc[-1])
    return path


def load_csv(name: str) -> pd.DataFrame:
    path = DATA / name
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df.set_index("date").sort_index()


def last_date(name: str):
    df = load_csv(name)
    return None if df.empty else df.index[-1]
