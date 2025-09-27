# setup_logic.py (ВЕРСІЯ З ДЕТАЛЬНИМ ЛОГУВАННЯМ)
import sys
import os
import subprocess
import urllib.request
import ctypes
import time

# ... (список FILES_TO_DOWNLOAD залишається той самий) ...
GITHUB_REPO_URL = "https://raw.githubusercontent.com/autorom2024/VoikanRecords/main/"
FILES_TO_DOWNLOAD = [
    "main.py", "updater.py", "version.py", "auth_logic.py", "dark_modern.qss",
    "google_api.py", "google_api_autofill.py", "helpers_youtube.py",
    "ui/heavy_installer_window.py", "ui/login_window.py", "ui/main_window.py",
    "ui/splash_screen.py", "ui/theme_loader.py", "ui/custom_title_bar.py",
    "ui/animated_push_button.py", "ui/glass_item_delegate.py"
]

def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)

# ... (функція run_command без змін) ...
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
    urllib.request.urlretrieve("https://bootstrap.pypa.io/get-pip.py", get_pip_path)
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
            log(f"  > Успішно завантажено: {file_path}")
        except urllib.error.HTTPError as e:
            log(f"============================================================")
            log(f"!!! КРИТИЧНА ПОМИЛКА: НЕ ВДАЛОСЯ ЗАВАНТАЖИТИ ФАЙЛ !!!")
            log(f"!!! URL: {url}")
            log(f"!!! Помилка: {e}")
            log(f"!!! Перевір, чи цей файл існує в репозиторії на GitHub і чи правильно він прописаний у списку FILES_TO_DOWNLOAD у setup_logic.py")
            log(f"============================================================")
            raise e

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
    if len(sys.argv) < 2:
        sys.exit(1)
    
    target_dir = sys.argv[1]
    try:
        main(target_dir)
        # Додамо паузу в кінці, щоб вікно не закрилося одразу
        log("\nНатисніть Enter для завершення...")
        input()
    except Exception as e:
        # Показуємо помилку у вікні і в консолі
        error_message = f"Під час встановлення сталася критична помилка:\n\n{e}"
        log(error_message)
        ctypes.windll.user32.MessageBoxW(0, error_message, "Помилка встановлення", 0x10)
        log("\nНатисніть Enter для закриття...")
        input()
        sys.exit(1)