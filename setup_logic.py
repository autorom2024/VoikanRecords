# setup_logic.py (ПОВНА ВЕРСІЯ, ЯКА ТІЛЬКИ ВСТАНОВЛЮЄ БІБЛІОТЕКИ)
import sys
import os
import subprocess
import ctypes
import time
import urllib.request

def log(message):
    """Функція для виводу логів у консоль."""
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

def run_command(command, cwd):
    """
    Запускає команду у фоні і виводить її результат в реальному часі.
    Це ПОВНА версія функції.
    """
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW
    )
    
    # Читаємо вивід по рядках
    for line in iter(process.stdout.readline, ''):
        if line:
            log(line.strip())
            
    process.stdout.close()
    return_code = process.wait()
    
    # Перевіряємо, чи була помилка
    if return_code != 0:
        raise RuntimeError(f"Команда завершилася з помилкою (код {return_code}): {' '.join(command)}")

def main(install_path):
    """Головна логіка встановлення."""
    log(f"Шлях встановлення: {install_path}")
    python_dir = os.path.join(install_path, "python")
    python_exe = os.path.join(python_dir, "python.exe")

    # Крок 1: Налаштування вбудованого Python
    # Знаходимо ._pth файл, щоб дозволити імпорт бібліотек
    pth_file_found = False
    for file in os.listdir(python_dir):
        if file.endswith("._pth"):
            pth_file = os.path.join(python_dir, file)
            with open(pth_file, "a") as f:
                f.write("\nimport site\n")
            log(f"Оновлено {pth_file} для підтримки бібліотек.")
            pth_file_found = True
            break
    if not pth_file_found:
        raise RuntimeError("Не знайдено ._pth файл в архіві Python.")
            
    # Крок 2: Встановлення pip
    get_pip_path = os.path.join(install_path, "get-pip.py")
    log("Завантаження інсталятора pip...")
    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", get_pip_path)
    log("Встановлення pip...")
    run_command([python_exe, get_pip_path], cwd=install_path)
    os.remove(get_pip_path)

    # Крок 3: Встановлення легких бібліотек
    pip_exe = os.path.join(python_dir, "Scripts", "pip.exe")
    requirements_path = os.path.join(install_path, "requirements-core.txt")
    log("Встановлення базових бібліотек (це може зайняти кілька хвилин)...")
    run_command([pip_exe, "install", "-r", requirements_path], cwd=install_path)
    
    log("Код програми вже на місці. Завантаження з GitHub не потрібне.")

    # Крок 4: Створення файлу для запуску
    run_bat_path = os.path.join(install_path, "run.bat")
    main_py_path = os.path.join(install_path, "main.py")
    with open(run_bat_path, "w", encoding='utf-8') as f:
        f.write(f'@echo off\n')
        f.write(f'cd /d "{install_path}"\n')
        f.write(f'"{python_exe}" "{main_py_path}"\n')

    log("Створення файлу запуску... Готово.")
    log("Встановлення успішно завершено!")

if __name__ == "__main__":
    # Цей блок виконується, коли скрипт запускається інсталятором
    if len(sys.argv) < 2:
        # Цього не має статися, якщо Inno Setup працює правильно
        ctypes.windll.user32.MessageBoxW(0, "Не вказано шлях для встановлення.", "Помилка", 0x10)
        sys.exit(1)
    
    target_dir = sys.argv[1]
    try:
        main(target_dir)
    except Exception as e:
        # Якщо щось пішло не так, показуємо вікно з помилкою
        ctypes.windll.user32.MessageBoxW(0, f"Під час встановлення сталася критична помилка:\n\n{e}", "Помилка встановлення", 0x10)
        sys.exit(1)