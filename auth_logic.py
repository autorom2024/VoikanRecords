# auth_logic.py
import os
import hashlib
import psutil
import gspread
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDENTIALS_DIR = 'credentials'
CLIENT_SECRETS_FILE = os.path.join(CREDENTIALS_DIR, 'client_secrets.json')
SERVICE_ACCOUNT_FILE = os.path.join(CREDENTIALS_DIR, 'service_account.json')
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, 'token.json')
LOCAL_LICENSE_FILE = os.path.join(CREDENTIALS_DIR, 'license.key')
SCOPES = ['https://www.googleapis.com/auth/userinfo.profile', 'https://www.googleapis.com/auth/userinfo.email', 'openid']
SPREADSHEET_NAME = 'VoikanUsers'

# !!! ВАЖЛИВО: ВСТАВТЕ ВАШ ЗГЕНЕРОВАНИЙ КЛЮЧ ЗАМІСТЬ ЦЬОГО ТЕКСТУ !!!
ENCRYPTION_KEY = b'SegKtKp0_Ck6cSws-5ytDWItJH_nND2RKuScsMm89JY='
fernet = Fernet(ENCRYPTION_KEY)

def save_local_license(license_data):
    try:
        os.makedirs(CREDENTIALS_DIR, exist_ok=True)
        license_data['last_check'] = datetime.now().isoformat()
        temp_data = license_data.copy()
        if 'expires_on' in temp_data and isinstance(temp_data.get('expires_on'), datetime):
            temp_data['expires_on'] = temp_data['expires_on'].isoformat()
        encrypted_data = fernet.encrypt(json.dumps(temp_data).encode())
        with open(LOCAL_LICENSE_FILE, 'wb') as f: f.write(encrypted_data)
        return True
    except Exception as e:
        print(f"Помилка збереження локальної ліцензії: {e}"); return False

def load_local_license():
    try:
        if not os.path.exists(LOCAL_LICENSE_FILE): return None
        with open(LOCAL_LICENSE_FILE, 'rb') as f: decrypted_data = fernet.decrypt(f.read())
        data = json.loads(decrypted_data)
        if 'expires_on' in data and data.get('expires_on'):
            data['expires_on'] = datetime.fromisoformat(data['expires_on'])
        return data
    except Exception as e:
        print(f"Помилка завантаження локальної ліцензії: {e}")
        if os.path.exists(LOCAL_LICENSE_FILE): os.remove(LOCAL_LICENSE_FILE)
        return None

def get_google_auth_credentials():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        os.makedirs(CREDENTIALS_DIR, exist_ok=True)
        with open(TOKEN_FILE, 'w') as token: token.write(creds.to_json())
    return creds

def get_user_info(credentials):
    try:
        service = build('oauth2', 'v2', credentials=credentials)
        user_info = service.userinfo().get().execute()
        return {'email': user_info.get('email'), 'name': user_info.get('name')}
    except Exception as e:
        print(f"Помилка отримання інформації про користувача: {e}"); return None

def get_machine_id():
    try:
        cpu_serial = os.popen('wmic cpu get ProcessorId').read().replace("ProcessorId", "").strip()
        if not cpu_serial: raise ValueError("Not a Windows OS")
    except Exception:
        system_info = f"{psutil.boot_time()}-{os.name}-{psutil.cpu_count()}"
        mac_address = ""
        for intf, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == psutil.AF_LINK and addr.address: mac_address = addr.address; break
            if mac_address: break
        cpu_serial = f"{system_info}-{mac_address}"
    return hashlib.sha256(cpu_serial.encode()).hexdigest()

def _parse_features(record):
    features = {
        "suno": record[5].upper() == 'TRUE' if len(record) > 5 else False,
        "vertex": record[6].upper() == 'TRUE' if len(record) > 6 else False,
        "montage": record[7].upper() == 'TRUE' if len(record) > 7 else False,
        "planner": record[8].upper() == 'TRUE' if len(record) > 8 else False,
        "autofill": record[9].upper() == 'TRUE' if len(record) > 9 else False,
    }
    return features

def check_user_license(user_data, machine_id):
    try:
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        worksheet = gc.open(SPREADSHEET_NAME).sheet1
    except Exception as e:
        return {'plan': 'error', 'message': f"Помилка підключення до бази: {e}", 'access_granted': False}
    email = user_data['email']; user_data['email'] = email
    try: user_cell = worksheet.find(email, in_column=1)
    except gspread.exceptions.CellNotFound: user_cell = None
    now = datetime.now()
    if user_cell is None:
        trial_expires_on = now + timedelta(days=1)
        new_user_data = [email, machine_id, now.isoformat(), 'trial', trial_expires_on.isoformat(), 'TRUE', 'TRUE', 'TRUE', 'TRUE', 'TRUE']
        worksheet.append_row(new_user_data)
        license_data = {
            'email': email, 'plan': 'trial', 'access_granted': True, 'expires_on': trial_expires_on, 'hwid': machine_id,
            'features': {k: True for k in ["suno", "vertex", "montage", "planner", "autofill"]}
        }
        save_local_license(license_data)
        return license_data
    else:
        record = worksheet.row_values(user_cell.row)
        stored_hwid, plan = record[1], record[3]
        license_data = {'email': email, 'plan': plan, 'hwid': stored_hwid}
        if stored_hwid and stored_hwid != machine_id:
            license_data.update({'message': 'Ліцензія прив\'язана до іншого ПК.', 'access_granted': False})
            return license_data
        if not stored_hwid: worksheet.update_cell(user_cell.row, 2, machine_id); license_data['hwid'] = machine_id
        features = _parse_features(record)
        license_data.update({'features': features})
        if plan == 'trial':
            expires_on = datetime.fromisoformat(record[4])
            if now < expires_on: license_data.update({'access_granted': True, 'expires_on': expires_on})
            else: license_data.update({'plan': 'trial_expired', 'access_granted': False, 'expires_on': expires_on})
        elif plan == 'pro':
            license_data['features'] = {k: True for k in features}; license_data['access_granted'] = True
        elif plan == 'blocked':
            license_data['access_granted'] = False
        else:
            license_data['access_granted'] = any(features.values())
        if license_data.get('access_granted'): save_local_license(license_data)
        return license_data

def get_license_status(email):
    try:
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        worksheet = gc.open(SPREADSHEET_NAME).sheet1
        user_cell = worksheet.find(email, in_column=1)
        if not user_cell: return None
        record = worksheet.row_values(user_cell.row)
        plan = record[3]
        features = _parse_features(record)
        license_info = {'email': email, 'plan': plan, 'features': features, 'access_granted': False, 'hwid': record[1]}
        if plan == 'trial':
            expires_on = datetime.fromisoformat(record[4])
            license_info['expires_on'] = expires_on
            if datetime.now() < expires_on: license_info['access_granted'] = True
            else: license_info['plan'] = 'trial_expired'
        elif plan == 'pro':
            license_info['features'] = {k: True for k in features}
            license_info['access_granted'] = True
        elif plan == 'blocked':
            license_info['access_granted'] = False
        else:
            license_info['access_granted'] = any(features.values())
        return license_info
    except Exception as e:
        print(f"Помилка при читанні статусу: {e}"); return None

def update_hwid_in_sheet(email, new_hwid):
    try:
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE)
        worksheet = gc.open(SPREADSHEET_NAME).sheet1
        user_cell = worksheet.find(email, in_column=1)
        if user_cell:
            worksheet.update_cell(user_cell.row, 2, new_hwid)
            print(f"HWID для {email} оновлено на {new_hwid}"); return True
        else:
            print(f"Користувача {email} не знайдено."); return False
    except Exception as e:
        print(f"Помилка оновлення HWID: {e}"); return False