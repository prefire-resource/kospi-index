"""금융투자협회 freesis 수집기 — 증시자금추이 (로그인 불필요)

kofia_funds.csv (단위: 백만원)
  deposits   투자자예탁금
  unsettled  위탁매매 미수금
  forced     미수금 대비 실제 반대매매 금액
  forced_pct 반대매매 비중(%)
  credit     신용거래융자 전체
  credit_kospi 신용거래융자 유가증권시장

주의: freesis 는 사람이 보는 화면을 전제로 만들어져 있어서, 그냥 요청하면
막힐 수 있다. 차단되면 workflow 로그에 남고 텔레그램 알림이 간다.
그때는 브라우저 자동화(playwright)로 바꿔야 한다.
"""
from __future__ import annotations

import time

import pandas as pd

from .common import http_post_json, log, upsert_csv, last_date

URL = "https://freesis.kofia.or.kr/meta/getMetaDataList.do"
REFERER = "https://freesis.kofia.or.kr/stat/main.do"
OBJ_FUNDS = "STATSCU0100000060BO"    # 예탁금·미수금·반대매매
OBJ_CREDIT = "STATSCU0100000070BO"   # 신용거래융자·대주


def _query(obj: str, frm: str, to: str) -> pd.DataFrame:
    payload = {"dmSearch": {"tmpV40": "1000000", "tmpV41": "1", "tmpV6": "2", "tmpV7": "1",
                            "tmpV4": "", "tmpV11": "", "tmpV1": "RD",
                            "tmpV45": frm, "tmpV46": to, "OBJ_NM": obj}}
    rows = http_post_json(URL, payload, headers={"Referer": REFERER}).get("ds1", [])
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df[df["TMPV1"].notna()]
    df["date"] = pd.to_datetime(df["TMPV1"], format="%Y%m%d", errors="coerce")
    return df.dropna(subset=["date"])


def collect(start: str, end: str | None = None, pause: float = 0.4) -> pd.DataFrame:
    end = end or pd.Timestamp.today().strftime("%Y%m%d")
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    funds, credit = [], []
    for y in range(s.year, e.year + 1):
        a = max(s, pd.Timestamp(f"{y}-01-01")).strftime("%Y%m%d")
        b = min(e, pd.Timestamp(f"{y}-12-31")).strftime("%Y%m%d")
        f = _query(OBJ_FUNDS, a, b)
        time.sleep(pause)
        c = _query(OBJ_CREDIT, a, b)
        time.sleep(pause)
        log.info("금투협 %s: 자금 %d행, 신용 %d행", y, len(f), len(c))
        if not f.empty:
            funds.append(f[["date", "TMPV2", "TMPV5", "TMPV6", "TMPV7"]]
                         .rename(columns={"TMPV2": "deposits", "TMPV5": "unsettled",
                                          "TMPV6": "forced", "TMPV7": "forced_pct"}))
        if not c.empty:
            credit.append(c[["date", "TMPV2", "TMPV3"]]
                          .rename(columns={"TMPV2": "credit", "TMPV3": "credit_kospi"}))
    if not funds and not credit:
        return pd.DataFrame()
    out = pd.concat(funds) if funds else pd.DataFrame(columns=["date"])
    if credit:
        out = out.merge(pd.concat(credit), on="date", how="outer")
    num = [c for c in out.columns if c != "date"]
    out[num] = out[num].apply(pd.to_numeric, errors="coerce")
    return out.sort_values("date")


def run(start: str | None = None, days_back: int = 20) -> None:
    if start is None:
        prev = last_date("kofia_funds.csv")
        start = ((prev - pd.Timedelta(days=days_back)) if prev is not None
                 else pd.Timestamp("2008-01-01")).strftime("%Y%m%d")
    df = collect(start)
    if df.empty:
        raise RuntimeError("금투협에서 받은 데이터가 없습니다 (차단 또는 응답 구조 변경 가능성)")
    upsert_csv("kofia_funds.csv", df)


if __name__ == "__main__":
    import sys
    run(sys.argv[1] if len(sys.argv) > 1 else None)
