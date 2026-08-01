@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo Сборка KIBERone Classroom...
python -m pip install -r requirements-build.txt -q

pyinstaller --noconfirm --clean ^
  --onefile --windowed ^
  --name KIBERoneTeacher ^
  --paths . ^
  --add-data "assets;assets" ^
  --hidden-import classroom.teacher.gui ^
  --hidden-import classroom.server.hub ^
  --hidden-import classroom.shared.discovery ^
  --hidden-import classroom.shared.versions ^
  --hidden-import classroom.shared.theme ^
  --hidden-import classroom.shared.branding ^
  --hidden-import classroom.shared.starter_pack ^
  --hidden-import classroom.shared.scrollable ^
  run_teacher.py

pyinstaller --noconfirm --clean ^
  --onefile --windowed ^
  --name KIBERoneStudent ^
  --paths . ^
  --add-data "assets;assets" ^
  --hidden-import classroom.student.gui ^
  --hidden-import classroom.student.agent ^
  --hidden-import classroom.shared.discovery ^
  --hidden-import classroom.shared.identity ^
  --hidden-import classroom.shared.theme ^
  --hidden-import classroom.shared.branding ^
  --hidden-import classroom.shared.scrollable ^
  run_student.py

echo.
echo Готово:
echo   dist\KIBERoneTeacher.exe
echo   dist\KIBERoneStudent.exe
pause
