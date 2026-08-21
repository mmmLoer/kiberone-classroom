import json
import threading
import time
import urllib.request
import urllib.error
import random
import socket

# --- НАСТРОЙКИ ТЕСТА ---
TEACHER_IP = "127.0.0.1"  # ВПИШИ СЮДА IP ТЬЮТОРА (например, 192.168.1.15)
PORT = 8765
TOKEN = "kiberone-sync-2026"
VIRTUAL_STUDENTS = 20     # Сколько учеников имитируем
REQUESTS_PER_STUDENT = 50 # Сколько запросов сделает каждый
PAYLOAD_SIZE_KB = 512     # Размер отправляемого файла в КБ (имитация сохранения игры)

# -----------------------

def simulate_student(student_id: int, results: list):
    base_url = f"http://{TEACHER_IP}:{PORT}"
    errors = 0
    total_time = 0.0
    
    # Генерируем мусорные данные для имитации файла сохранения
    dummy_data = os.urandom(PAYLOAD_SIZE_KB * 1024) if 'os' in globals() else b"x" * (PAYLOAD_SIZE_KB * 1024)

    for i in range(REQUESTS_PER_STUDENT):
        start = time.time()
        try:
            # 1. Пинг (Heartbeat)
            hb_body = json.dumps({
                "client_id": f"stress-mac-{student_id}",
                "pc_number": str(student_id),
                "watch_folder": "C:/StressTest",
            }).encode()
            
            req = urllib.request.Request(f"{base_url}/heartbeat", data=hb_body, 
                headers={'X-Sync-Token': TOKEN, 'Content-Type': 'application/json'})
            urllib.request.urlopen(req, timeout=3.0)

            # 2. Имитация отправки файла (Upload)
            # В реальном приложении это /upload
            req_up = urllib.request.Request(f"{base_url}/upload", data=dummy_data,
                headers={'X-Sync-Token': TOKEN, 'X-Relative-Path': f"stress_test_{student_id}.bin"})
            urllib.request.urlopen(req_up, timeout=5.0)

        except Exception as e:
            errors += 1
            
        total_time += (time.time() - start)
        
        # Небольшая пауза, имитирующая реальную работу
        time.sleep(random.uniform(0.1, 0.5))

    results.append({
        "id": student_id,
        "errors": errors,
        "avg_time": total_time / REQUESTS_PER_STUDENT
    })

if __name__ == "__main__":
    import os
    print(f"Начинаем стресс-тест Wi-Fi на {TEACHER_IP}:{PORT}...")
    print(f"Имитируем {VIRTUAL_STUDENTS} учеников, отправляющих файлы по {PAYLOAD_SIZE_KB} КБ.")
    
    threads = []
    results = []
    
    start_time = time.time()
    
    for i in range(1, VIRTUAL_STUDENTS + 1):
        t = threading.Thread(target=simulate_student, args=(i, results))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    total_duration = time.time() - start_time
    total_requests = VIRTUAL_STUDENTS * REQUESTS_PER_STUDENT * 2 # heartbeat + upload
    total_errors = sum(r["errors"] for r in results)
    
    print("\n=== РЕЗУЛЬТАТЫ СТРЕСС-ТЕСТА ===")
    print(f"Затрачено времени: {total_duration:.2f} сек")
    print(f"Всего запросов: {total_requests}")
    print(f"Ошибок (таймаутов/обрывов связи): {total_errors} ({total_errors/total_requests*100:.1f}%)")
    
    avg_latency = sum(r["avg_time"] for r in results) / len(results)
    print(f"Среднее время обработки 1 цикла (Пинг + Загрузка файла): {avg_latency:.2f} сек")
    
    if total_errors > total_requests * 0.05:
        print("\n⚠️ ВНИМАНИЕ: Роутер теряет более 5% пакетов под нагрузкой! Wi-Fi не справляется.")
    elif avg_latency > 2.0:
        print("\n⚠️ ВНИМАНИЕ: Задержки слишком высокие. Роутер захлёбывается, связь будет медленной.")
    else:
        print("\n✅ ОТЛИЧНО: Роутер уверенно держит нагрузку!")
