#!/usr/bin/env bash
# Сборка тьютора для macOS. Запускать НА Mac.
set -euo pipefail
cd "$(dirname "$0")"

echo "KIBERone Classroom — Mac Tutor build"
python3 -m pip install -r requirements-build.txt pillow -q

python3 <<'PY'
from pathlib import Path
from PIL import Image
import subprocess
import shutil

src = Image.open("assets/logo.png").convert("RGBA")
w, h = src.size
side = max(w, h)
base = Image.new("RGBA", (side, side), (0, 0, 0, 0))
base.paste(src, ((side - w) // 2, (side - h) // 2), src)

iconset = Path("assets/app.iconset")
if iconset.exists():
    shutil.rmtree(iconset)
iconset.mkdir(parents=True)

files = {
    16: ["icon_16x16.png"],
    32: ["icon_16x16@2x.png", "icon_32x32.png"],
    64: ["icon_32x32@2x.png"],
    128: ["icon_128x128.png"],
    256: ["icon_128x128@2x.png", "icon_256x256.png"],
    512: ["icon_256x256@2x.png", "icon_512x512.png"],
    1024: ["icon_512x512@2x.png"],
}
for size, names in files.items():
    im = base.resize((size, size), Image.Resampling.LANCZOS)
    for name in names:
        im.save(iconset / name)

icns = Path("assets/app.icns")
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
print("wrote", icns)
PY

echo "[1/2] Student..."
pyinstaller --noconfirm --clean \
  --onefile --windowed \
  --name KIBERoneStudent \
  --icon assets/app.icns \
  --paths . \
  --add-data "assets:assets" \
  --hidden-import classroom.student.gui \
  --hidden-import classroom.student.agent \
  --hidden-import classroom.shared.discovery \
  --hidden-import classroom.shared.identity \
  --hidden-import classroom.shared.theme \
  --hidden-import classroom.shared.branding \
  --hidden-import classroom.shared.scrollable \
  --hidden-import classroom.shared.settings \
  --hidden-import classroom.shared.scripts \
  --hidden-import classroom.shared.updates \
  run_student.py

mkdir -p updates
if [[ -f dist/KIBERoneStudent ]]; then
  cp -f dist/KIBERoneStudent "updates/KIBERoneStudent" || true
  python3 publish_student_update.py || true
fi

echo "[2/2] Tutor..."
EXTRA=()
if [[ -d updates ]]; then
  EXTRA+=(--add-data "updates:updates")
fi

pyinstaller --noconfirm --clean \
  --onefile --windowed \
  --name KIBERoneTutor \
  --icon assets/app.icns \
  --paths . \
  --add-data "assets:assets" \
  "${EXTRA[@]}" \
  --hidden-import classroom.teacher.gui \
  --hidden-import classroom.server.hub \
  --hidden-import classroom.shared.discovery \
  --hidden-import classroom.shared.versions \
  --hidden-import classroom.shared.theme \
  --hidden-import classroom.shared.branding \
  --hidden-import classroom.shared.starter_pack \
  --hidden-import classroom.shared.scrollable \
  --hidden-import classroom.shared.settings \
  --hidden-import classroom.shared.scripts \
  --hidden-import classroom.shared.updates \
  --hidden-import classroom.teacher.settings_window \
  run_tutor.py

echo
echo "Готово: dist/KIBERoneTutor  и  dist/KIBERoneStudent"
