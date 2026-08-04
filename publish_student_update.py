"""Публикует dist/KIBERoneStudent.exe в updates/ (для сборки тьютора)."""

from __future__ import annotations

from pathlib import Path

from classroom.shared.constants import APP_VERSION
from classroom.shared.updates import publish_student_exe


def main() -> None:
    src = Path("dist") / "KIBERoneStudent.exe"
    if not src.is_file():
        raise SystemExit(f"Нет файла: {src}")
    info = publish_student_exe(src, version=APP_VERSION)
    print(f"Published v{info['version']} ({info['size']} bytes) -> updates/")


if __name__ == "__main__":
    main()
