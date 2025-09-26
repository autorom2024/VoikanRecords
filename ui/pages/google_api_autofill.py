# google_api_autofill.py
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import os
import pickle

# Якщо ви хочете змінити область доступу, змініть SCOPES
SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]

TOKEN_FILE = "token.pickle"

def authorize_google_autofill(client_secret_file=None):
    """Авторизація в Google API"""
    creds = None
    
    # Перевіряємо, чи існує збережений токен
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)
    
    # Якщо немає валідних облікових даних, запитуємо авторизацію
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if client_secret_file and os.path.exists(client_secret_file):
                flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
            else:
                # Шукаємо client_secret.json в поточній папці
                client_secret_file = os.path.join(os.getcwd(), "client_secret.json")
                if os.path.exists(client_secret_file):
                    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
                else:
                    raise FileNotFoundError("Не знайдено файл client_secret.json")
            
            creds = flow.run_local_server(port=0)
        
        # Зберігаємо облікові дані для майбутнього використання
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
    
    # Створюємо сервіс YouTube
    youtube = build("youtube", "v3", credentials=creds)
    return youtube, creds, SCOPES

def get_videos_split(youtube, max_results=500, unpublished_only=False):
    """Отримує список відео з каналу, розділений на відео та shorts"""
    # Ця функція залишається без змін
    # ... (існуючий код функції)