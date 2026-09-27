"""접속 테스트: 각 소스에서 최근 며칠치를 받아 보고 결과를 알린다."""
from __future__ import annotations

import os
import traceback

import pandas as pd

from notify.telegram import send

RESULTS = []


def try_step(name, fn):
    try:
        info = fn()
        RESULTS.append(f"✅ {name}: {info}")
    except Exception as e:
        RESULTS.append(f"❌ {name}: {type(e).__name__} {str(e)[:120]}")
        traceback.print_exc()


def krx():
    from pykrx import stock
    end = pd.Timestamp.today().strftime("%Y%m%d")
    start = (pd.Timestamp.today() - pd.Timedelta(days=10)).strftime("%Y%m%d")
    o = stock.get_index_ohlcv_by_date(start, end, "1001")
    f = stock.get_index_fundamental_by_date(start, end, "1001")
    v = stock.get_market_trading_value_by_date(start, end, "KOSPI")
    assert len(o) and len(f) and len(v), "빈 응답"
    return f"지수 {len(o)}행, PBR {f['PBR'].iloc[-1]}, 수급 {len(v)}행"


def naver():
    from collectors.naver import fetch_page
    df = fetch_page("KOSPI", 1)
    assert len(df), "빈 응답"
    return f"{len(df)}행, 최신 {df['date'].max().date()}"


def kofia():
    from collectors.kofia import collect
    start = (pd.Timestamp.today() - pd.Timedelta(days=20)).strftime("%Y%m%d")
    df = collect(start)
    assert len(df), "빈 응답"
    return f"{len(df)}행, 최신 {df['date'].max().date()}"


def secrets_status() -> str:
    out = []
    for k in ["KRX_ID", "KRX_PW", "TELEGRAM_TOKEN", "TELEGRAM_CHAT_ID"]:
        v = (os.environ.get(k) or "").strip()
        out.append(f"{k}={'설정됨(%d자)' % len(v) if v else '비어 있음'}")
    return " / ".join(out)


if __name__ == "__main__":
    print("[Secrets]", secrets_status())
    try_step("KRX(pykrx)", krx)
    try_step("네이버 금융", naver)
    try_step("금융투자협회", kofia)
    print("\n[네이버 주소 후보 점검]")
    try:
        from probe_naver import CANDIDATES, probe
        for nm, u in CANDIDATES:
            print(probe(nm, u))
    except Exception as e:
        print("주소 점검 실패:", e)
    msg = "[접속 테스트]\n" + "\n".join(RESULTS) + "\n" + secrets_status()
    print(msg)
    send(msg)
