from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _crash_log(exc: BaseException) -> None:
    try:
        log = Path.home() / "Library" / "Logs" / "KIBERoneTutor-crash.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    try:
        from classroom.teacher.gui import main

        main()
    except BaseException as exc:
        _crash_log(exc)
        raise
