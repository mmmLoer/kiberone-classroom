# KIBERone Classroom

Панель управления учебными ПК по локальной сети: преподаватель + ученик.

## Быстрый старт

### Преподаватель
```powershell
python -m classroom.run_teacher
# или
.\dist\KIBERoneTeacher.exe
```

### Ученик
```powershell
python -m classroom.run_student
# или
.\dist\KIBERoneStudent.exe
```

Ученик может найти преподавателя кнопкой **«Найти в сети»** (UDP broadcast).

## Возможности

- Автопоиск преподавателя в LAN
- Синхронизация файлов с ПК ученика
- Удалённые команды: ссылки, обои, установщики, сообщения
- История версий и откат файлов
- Идентификация ПК по MAC + номер ПК

## Сборка exe

```bat
build.bat
```

Появятся `dist\KIBERoneTeacher.exe` и `dist\KIBERoneStudent.exe`.

## Тесты

```powershell
python -m pytest classroom/tests -v
```

## Папки

| Путь | Назначение |
|------|------------|
| `Рабочий стол\Ученики\<MAC>\` | Бэкапы учеников на ПК преподавателя |
| `deploy\` | Файлы для раздачи (обои, установщики) |
| `dist\` | Готовые exe |

Крупные установщики (>100 МБ) в git не кладём из‑за лимита GitHub — положи их локально в `deploy\`.
