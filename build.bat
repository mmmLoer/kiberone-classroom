@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo Сборка KIBERone Classroom...
python -m pip install -r requirements-build.txt pillow -q

if not exist assets\app.ico (
  python -c "from PIL import Image; from pathlib import Path; src=Image.open('assets/logo.png').convert('RGBA'); w,h=src.size; side=max(w,h); base=Image.new('RGBA',(side,side),(0,0,0,0)); base.paste(src,((side-w)//2,(side-h)//2),src); icons=[base.resize((s,s), Image.Resampling.LANCZOS) for s in (16,32,48,64,128,256)]; icons[-1].save('assets/app.ico', format='ICO', sizes=[(i.width,i.height) for i in icons]); print('app.ico ok')"
)

echo.
echo [1/3] Student EXE...
pyinstaller --noconfirm --clean ^
  --onefile --windowed ^
  --name KIBERoneStudent ^
  --icon assets\app.ico ^
  --paths . ^
  --add-data "assets;assets" ^
  --hidden-import classroom.student.gui ^
  --hidden-import classroom.student.agent ^
  --hidden-import classroom.shared.discovery ^
  --hidden-import classroom.shared.identity ^
  --hidden-import classroom.shared.theme ^
  --hidden-import classroom.shared.branding ^
  --hidden-import classroom.shared.scrollable ^
  --hidden-import classroom.shared.settings ^
  --hidden-import classroom.shared.scripts ^
  --hidden-import classroom.shared.updates ^
  run_student.py
if errorlevel 1 exit /b 1

echo.
echo [2/3] Публикация Student в updates\...
if not exist updates mkdir updates
python publish_student_update.py
if errorlevel 1 exit /b 1

echo.
echo [3/3] Tutor EXE (со встроенным Student)...
pyinstaller --noconfirm --clean ^
  --onefile --windowed ^
  --name KIBERoneTutor ^
  --icon assets\app.ico ^
  --paths . ^
  --add-data "assets;assets" ^
  --add-data "updates;updates" ^
  --hidden-import classroom.teacher.gui ^
  --hidden-import classroom.server.hub ^
  --hidden-import classroom.shared.discovery ^
  --hidden-import classroom.shared.versions ^
  --hidden-import classroom.shared.theme ^
  --hidden-import classroom.shared.branding ^
  --hidden-import classroom.shared.starter_pack ^
  --hidden-import classroom.shared.scrollable ^
  --hidden-import classroom.shared.settings ^
  --hidden-import classroom.shared.scripts ^
  --hidden-import classroom.shared.updates ^
  --hidden-import classroom.teacher.settings_window ^
  run_tutor.py
if errorlevel 1 exit /b 1

echo.
echo Готово:
echo   dist\KIBERoneTutor.exe
echo   dist\KIBERoneStudent.exe
pause
