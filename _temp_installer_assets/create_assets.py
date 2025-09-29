# create_assets.py
# Цей скрипт створить тимчасові зображення-заглушки для інсталятора.
import os

# Створюємо папку, якщо її немає
folder = "_temp_installer_assets"
os.makedirs(folder, exist_ok=True)

# Функція для створення простого BMP файлу
def create_bmp(path, width, height, color=(22, 26, 33)): # Колір #161A21
    with open(path, "wb") as f:
        # BMP Header
        f.write(b'BM')
        file_size = 14 + 40 + (width * height * 3)
        f.write(file_size.to_bytes(4, 'little'))
        f.write((0).to_bytes(4, 'little'))
        f.write((54).to_bytes(4, 'little'))
        # DIB Header
        f.write((40).to_bytes(4, 'little'))
        f.write(width.to_bytes(4, 'little'))
        f.write(height.to_bytes(4, 'little'))
        f.write((1).to_bytes(2, 'little'))
        f.write((24).to_bytes(2, 'little'))
        f.write((0).to_bytes(4, 'little'))
        f.write((width * height * 3).to_bytes(4, 'little'))
        f.write((0).to_bytes(16, 'little'))
        # Pixel data
        for _ in range(height):
            for _ in range(width):
                f.write(bytes([color[2], color[1], color[0]])) # BGR

# Функція для створення простого ICO файлу
def create_ico(path, size=32):
    with open(path, "wb") as f:
        # ICO Header
        f.write((0).to_bytes(2, 'little'))
        f.write((1).to_bytes(2, 'little'))
        f.write((1).to_bytes(2, 'little'))
        # Icon Directory Entry
        f.write(size.to_bytes(1, 'little'))
        f.write(size.to_bytes(1, 'little'))
        f.write((0).to_bytes(1, 'little'))
        f.write((0).to_bytes(1, 'little'))
        f.write((1).to_bytes(2, 'little'))
        f.write((32).to_bytes(2, 'little'))
        image_size = 40 + size * size * 4 + size * size // 8
        f.write(image_size.to_bytes(4, 'little'))
        f.write((22).to_bytes(4, 'little')) # Offset
        # BMP DIB Header
        f.write((40).to_bytes(4, 'little'))
        f.write(size.to_bytes(4, 'little'))
        f.write((size * 2).to_bytes(4, 'little'))
        f.write((1).to_bytes(2, 'little'))
        f.write((32).to_bytes(2, 'little')) # 32-bit (RGBA)
        f.write((0).to_bytes(4, 'little'))
        f.write((0).to_bytes(4, 'little')) # Image size can be 0 for BI_RGB
        f.write((0).to_bytes(16, 'little'))
        # Pixel data (fully transparent)
        f.write(bytes(size * size * 4)) # Transparent pixels
        # AND mask (all opaque)
        f.write(bytes(size * size // 8))

# Створюємо файли
create_bmp(os.path.join(folder, "sidebar.bmp"), 164, 314)
create_bmp(os.path.join(folder, "logo_small.bmp"), 55, 58)
create_ico(os.path.join(folder, "logo.ico"), 32)

print(f"Створено 3 файли-заглушки у папці '{folder}'")