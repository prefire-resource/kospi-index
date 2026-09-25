"""수집 데이터 검증. 문제가 있으면 메시지 목록을 돌려준다."""
from __future__ import annotations

import sys

import pandas as pd

from collectors.common import load_csv

REQUIRED = {
    "kospi_index.csv": ["close", "value"],
    "kospi_valuation.csv": ["pbr"],
    "kofia_funds.csv": ["deposits", "credit", "forced"],
}
FRESH_DAYS = {"kospi_index.csv": 5, "kospi_valuation.csv": 5, "kofia_funds.csv": 7,
              "krx_investor.csv": 5, "kospi_investor_naver.csv": 5}


def check() -> list[str]:
    problems, today = [], pd.Timestamp.today().normalize()
    for name, cols in REQUIRED.items():
        df = load_csv(name)
        if df.empty:
            problems.append(f"{name}: 파일이 없거나 비어 있음")
            continue
        for c in cols:
            if c not in df.columns:
                problems.append(f"{name}: 컬럼 {c} 없음")
            elif df[c].tail(60).isna().mean() > 0.2:
                problems.append(f"{name}: 최근 60행 중 {c} 결측 과다")
        if df.index.duplicated().any():
            problems.append(f"{name}: 중복 날짜 존재")

    for name, days in FRESH_DAYS.items():
        df = load_csv(name)
        if df.empty:
            continue
        gap = (today - df.index[-1]).days
        if gap > days:
            problems.append(f"{name}: 최신 데이터가 {gap}일 전 ({df.index[-1].date()})")

    inv = load_csv("krx_investor.csv")
    if not inv.empty and {"foreign", "inst", "indiv"} <= set(inv.columns):
        tot = inv[["foreign", "inst", "indiv"] + (["corp"] if "corp" in inv else [])].tail(20).sum(axis=1).abs()
        scale = inv[["foreign", "inst", "indiv"]].tail(20).abs().sum(axis=1)
        if (tot > scale * 0.2).mean() > 0.5:
            problems.append("krx_investor.csv: 투자자별 합계가 0에 가깝지 않음 (수집 오류 의심)")
    return problems


if __name__ == "__main__":
    p = check()
    print("\n".join(p) if p else "데이터 검증 통과")
    sys.exit(1 if p else 0)
