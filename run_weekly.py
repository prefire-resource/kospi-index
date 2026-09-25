"""금요일 마감 후: 지수 계산 + 텔레그램 신호 발송."""
from __future__ import annotations

import sys
import traceback

from index.compute import run
from notify.telegram import format_signal, send

if __name__ == "__main__":
    try:
        s = run()
        send(format_signal(s))
    except Exception as e:
        traceback.print_exc()
        send(f"[지수 계산 실패] {type(e).__name__} {str(e)[:200]}")
        sys.exit(1)
