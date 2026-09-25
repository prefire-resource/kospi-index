"""과거 데이터 일괄 수집. 기본 2008-01-01부터."""
from __future__ import annotations

import sys
import traceback

from collectors import kofia, krx, naver
from notify.telegram import send

if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "20080101"
    done, fail = [], []
    for name, fn in [("KRX", lambda: krx.run(start)),
                     ("네이버", lambda: naver.run(start)),
                     ("금투협", lambda: kofia.run(start))]:
        try:
            fn(); done.append(name)
        except Exception as e:
            fail.append(f"{name}: {type(e).__name__} {str(e)[:150]}")
            traceback.print_exc()
    send(f"[백필 완료] 시작일 {start}\n성공: {', '.join(done) or '없음'}\n" +
         ("실패:\n" + "\n".join(fail) if fail else ""))
    sys.exit(1 if fail else 0)
