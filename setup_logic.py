# setup_logic.py (ОСТАННЯ ВЕРСІЯ)
import sys
import os
import subprocess
import urllib.request
import zipfile
import ctypes
import time

# --- НАЛАШТУВАННЯ ---
PYTHON_VERSION = "3.11.9"
PYTHON_DOWNLOAD_URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
GITHUB_REPO_URL = "https://raw.githubusercontent.com/autorom2024/VoikanRecords/main/"

# ==============================================================================
#      ПОВНИЙ І ВИПРАВЛЕНИЙ СПИСОК ФАЙЛІВ
# ==============================================================================
FILES_TO_DOWNLOAD = [
    # --- КОРЕНЕВА ПАПКА ---
    "main.py",
    "updater.py",
    "version.py",
    "auth_logic.py",
    "generate_my_key.py",
    "google_api.py",
    "google_api_autofill.py",
    "helpers_youtube.py",
    "dark_modern.qss", # <--- ОСЬ ГОЛОВНЕ ВИПРАВЛЕННЯ (файл в корені)

    # --- ПАПКА UI ---
    "ui/heavy_installer_window.py",
    "ui/login_window.py",
    "ui/main_window.py",
    "ui/splash_screen.py",
    "ui/theme_loader.py",
    "ui/custom_title_bar.py",
    "ui/animated_push_button.py",
    "ui/glass_item_delegate.py",
    
    # --- ПАПКА UI/PAGES ---
    # !!! Перевір, чи є файли в 'ui/pages', і додай їх, якщо потрібно
    
    # --- ПАПКА LOGIC ---
    # !!! Перевір, чи є файли в 'logic', і додай їх, якщо потрібно
]
# ==============================================================================

def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

def run_command(command, cwd):
    process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    for line in iter(process.stdout.readline, ''):
        if line:
            log(line.strip())
    process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"Command failed with code {return_code}: {' '.join(command)}")

def main(install_path):
    log(f"Шлях встановлення: {install_path}")
    python_dir = os.path.join(install_path, "python")
    python_exe = os.path.join(python_dir, "python.exe")

    # Вмикаємо можливість імпортувати модулі
    for file in os.listdir(python_dir):
        if file.endswith("._pth"):
            pth_file = os.path.join(python_dir, file)
            with open(pth_file, "a") as f:
                f.write("\nimport site\n")
            log(f"Оновлено {pth_file} для підтримки site-packages.")
            break
            
    # Встановлення pip
    get_pip_path = os.path.join(install_path, "get-pip.py")
    log("Завантаження інсталятора pip...")
    urllib.request.urlretrieve(GET_PIP_URL, get_pip_path)
    log("Встановлення pip...")
    run_command([python_exe, get_pip_path], cwd=install_path)
    os.remove(get_pip_path)

    # Встановлення легких бібліотек
    pip_exe = os.path.join(python_dir, "Scripts", "pip.exe")
    requirements_path = os.path.join(install_path, "requirements-core.txt")
    log("Встановлення базових бібліотек...")
    run_command([pip_exe, "install", "-r", requirements_path], cwd=install_path)
    
    # Завантаження коду програми
    log("Завантаження файлів програми з GitHub...")
    for file_path in FILES_TO_DOWNLOAD:
        url_path = file_path.replace("\\", "/")
        local_path = os.path.join(install_path, file_path)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        url = GITHUB_REPO_URL + url_path
        
        log(f"  > Спроба завантажити: {url}")
        try:
            urllib.request.urlretrieve(url, local_path)
        except urllib.error.HTTPError as e:
            error_message = f"!!! КРИТИЧНА ПОМИЛКА: НЕ ВДАЛОСЯ ЗАВАНТАЖИТИ ФАЙЛ !!!\nURL: {url}\nПомилка: {e}\nПеревір, чи цей файл існує в репозиторії і чи правильно він прописаний у списку."
            log(error_message)
            raise RuntimeError(error_message)

    # Створення файлу для запуску
    run_bat_path = os.path.join(install_path, "run.bat")
    main_py_path = os.path.join(install_path, "main.py")
    with open(run_bat_path, "w", encoding='utf-8') as f:
        f.write(f'@echo off\n')
        f.write(f'cd /d "{install_path}"\n')
        f.write(f'"{python_exe}" "{main_py_path}"\n')

    log("Створення файлу запуску... Готово.")
    log("Встановлення успішно завершено!")

if __name__ == "__main__":
    if len(sys.argv) < 2: sys.exit(1)
    target_dir = sys.argv[1]
    try:
        main(target_dir)
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(0, str(e), "Помилка встановлення", 0x10)
        sys.exit(1)