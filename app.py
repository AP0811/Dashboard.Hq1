import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import os
import smtplib
import base64
import hashlib
import hmac
import time
import json
import tomllib
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle
from collections.abc import Mapping

# Configuration de la page
st.set_page_config(layout="wide", page_title="Dashboard Entraînement")

# Palette de couleurs cohérente pour toutes les visualisations
COLOR_PALETTE = {
    'Musculation': '#FF6B6B',  # Rouge
    'Cardio': '#4ECDC4',      # Turquoise
    'Hockey': '#45B7D1',      # Bleu principal
    'Sport': '#FFA07A',       # Orange
    'Skills': '#7FB3D5',      # Bleu clair (nuance de Hockey)
    'Pratique': '#2E86AB',    # Bleu moyen (nuance de Hockey)
    'Match': '#1B4F72',       # Bleu foncé (nuance de Hockey)
    'Repos': '#E0E0E0',       # Gris
    'Blessure': '#C0392B',    # Rouge foncé
    'Vacances': '#27AE60',    # Vert
    'Manque de temps': '#95A5A6',  # Gris moyen
}

FRENCH_MONTHS = {
    1: 'Janvier',
    2: 'Février',
    3: 'Mars',
    4: 'Avril',
    5: 'Mai',
    6: 'Juin',
    7: 'Juillet',
    8: 'Août',
    9: 'Septembre',
    10: 'Octobre',
    11: 'Novembre',
    12: 'Décembre'
}

# Mapping codes Qualtrics (après déduplication pandas) → noms de variables internes
# La 2e occurrence de Q32 devient Q32.1 quand pandas lit le fichier avec header=0
QUALTRICS_Q_TO_VAR = {
    'Q32':    'Id',                                     # Nom de l'athlète
    'Q43_1':  'Date',
    'Q27':    'Activités',
    'Q4':     'Entraînement sur glace',
    'Q5_1':   'Intensité (entraînement sur glace)',
    'Q6_1':   'Durée (entraînement sur glace)',
    'Q20':    'Skills coach (entraînement sur glace)',
    'Q32.1':  'Musculation',                            # 2e occurrence de Q32
    'Q8_1':   'Intensité (musculation)',
    'Q9_1':   'Durée (musculation)',
    'Q21':    'Skills coach (musculation)',
    'Q31':    'Match',
    'Q29_1':  'Intensité (match)',
    'Q28_1':  'Durée (match)',
    'Q22':    'Skills',
    'Q24_1':  'Intensité (skills)',
    'Q25_1':  'Durée (skills)',
    'Q26':    'Skills coach (skills)',
    'Q33':    'Cardio',
    'Q34_1':  'Intensité (cardio)',
    'Q35_1':  'Durée (cardio)',
    'Q14_1':  'Douleur',
    'Q15':    'Localisation (douleur)',
    'Q16':    'Autres sports',
    'Q17':    'Précisez le sport',
    'Q18_1':  'Intensité (autres sports)',
    'Q19_1':  'Durée (autres sports)',
}

# Paires (colonne durée, colonne intensité, nom de la colonne charge calculée)
ACTIVITY_LOAD_PAIRS = [
    ('Durée (entraînement sur glace)', 'Intensité (entraînement sur glace)', 'Pratique load'),
    ('Durée (musculation)',            'Intensité (musculation)',             'Muscu load'),
    ('Durée (match)',                  'Intensité (match)',                   'Match load'),
    ('Durée (skills)',                 'Intensité (skills)',                  'Skills load'),
    ('Durée (cardio)',                 'Intensité (cardio)',                  'Cardio load'),
    ('Durée (autres sports)',          'Intensité (autres sports)',           'Sport load'),
]

# Configuration des utilisateurs
# En production, utiliser une base de données sécurisée et une gestion des rôles centralisée
PRIVATE_DATA_DIR = 'private_data'


# Détermine où lire/écrire les données de l'application.
def resolve_data_root():
    # Priorité: variable d'environnement > private_data
    env_data_dir = os.getenv('APP_DATA_DIR')
    if env_data_dir:
        return env_data_dir
    return PRIVATE_DATA_DIR


DATA_ROOT = resolve_data_root()
AUTH_COOKIE_KEY = os.getenv('APP_AUTH_COOKIE_KEY', 'workout_dashboard_cookie_key_change_me_2026_32_plus_chars')

# Configuration SMTP — priorité: st.secrets > variables d'environnement
# Récupère une variable de config depuis st.secrets ou les variables d'environnement.
def _secret(key, default=''):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

SMTP_HOST     = _secret('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT     = int(_secret('SMTP_PORT', '587'))
SMTP_USER     = _secret('SMTP_USER', '')
SMTP_PASSWORD = _secret('SMTP_PASSWORD', '')
SMTP_FROM     = _secret('SMTP_FROM', SMTP_USER)
APP_BASE_URL  = _secret('APP_BASE_URL', 'http://localhost:8501')
RESET_TOKEN_SECRET = _secret('APP_RESET_TOKEN_SECRET', AUTH_COOKIE_KEY)
RESET_TOKEN_EXPIRY = 1800  # 30 minutes


def _read_local_streamlit_secrets():
    """Lit le fichier local .streamlit/secrets.toml (prioritaire pour la réidentification)."""
    try:
        local_path = Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml'
        if local_path.exists():
            return tomllib.loads(local_path.read_text(encoding='utf-8'))
    except Exception:
        pass
    return {}


def _get_reid_secret_key():
    local = _read_local_streamlit_secrets()
    local_key = local.get('APP_REID_SECRET_KEY', '')
    if isinstance(local_key, str) and local_key.strip():
        return local_key.strip()
    return _secret('APP_REID_SECRET_KEY', '')


def _load_reid_codebook():
    """
    Charge un codebook de réidentification depuis APP_REID_CODEBOOK.
    Formats acceptés:
      - dict dans st.secrets
      - JSON string via variable d'environnement/secrets
    Exemple JSON: {"athlete_001": "CODE-ALPHA", "athlete_002": "CODE-BETA"}
    """
    local = _read_local_streamlit_secrets()
    local_value = local.get('APP_REID_CODEBOOK', '')
    if isinstance(local_value, Mapping):
        return {str(k).strip(): str(v) for k, v in local_value.items()}

    raw_value = _secret('APP_REID_CODEBOOK', '')
    if isinstance(raw_value, Mapping):
        return {str(k).strip(): str(v) for k, v in raw_value.items()}
    if hasattr(raw_value, 'items'):
        try:
            return {str(k).strip(): str(v) for k, v in raw_value.items()}
        except Exception:
            pass
    if isinstance(raw_value, str) and raw_value.strip():
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, Mapping):
                return {str(k).strip(): str(v) for k, v in parsed.items()}
        except Exception:
            return {}
    return {}

CREDENTIALS_FOLDER = os.path.join(DATA_ROOT, 'credentials')
CREDENTIALS_XLSX = os.path.join(CREDENTIALS_FOLDER, 'users.xlsx')
CREDENTIALS_CSV = os.path.join(CREDENTIALS_FOLDER, 'users.csv')

DEFAULT_USERS = {
    "coach1": {"name": "Coach 1", "password": "coachpass", "role": "coach", "id": "coach1"},
    "admin": {"name": "Admin", "password": "adminpass", "role": "admin", "id": "admin"}
}

file_path = os.path.join(DATA_ROOT, 'Activités.xlsx') if os.path.exists(os.path.join(DATA_ROOT, 'Activités.xlsx')) else os.path.join(DATA_ROOT, 'trainings.xlsx')


# Trouve une colonne en essayant plusieurs noms possibles (égalité stricte puis partielle).
def find_column(columns, choices):
    for choice in choices:
        for col in columns:
            if str(col).strip().lower() == choice.lower():
                return col
    for choice in choices:
        for col in columns:
            if choice.lower() in str(col).strip().lower():
                return col
    return None


# Masque un identifiant athlète de manière stable pour l'affichage admin.
def mask_athlete_identifier(value):
    if pd.isna(value):
        return ''
    raw = str(value).strip()
    if not raw:
        return ''
    codebook = _load_reid_codebook()
    if raw in codebook:
        return codebook[raw]
    raw_lower = raw.lower()
    for key, mapped_value in codebook.items():
        if str(key).strip().lower() == raw_lower:
            return mapped_value
    reid_secret_key = _get_reid_secret_key()
    if reid_secret_key:
        digest = hmac.new(reid_secret_key.encode('utf-8'), raw.encode('utf-8'), hashlib.sha256).hexdigest()[:10].upper()
        return f"RID_{digest}"
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:8].upper()
    return f"ATHLETE_{digest}"


# Retourne une copie du DataFrame avec la colonne Id (ou équivalent) anonymisée pour l'admin.
def anonymize_athlete_column_for_admin(df):
    df_display = df.copy()
    athlete_col = find_column(df_display.columns, ['Id', 'athlete_id', 'utilisateur', 'Utilisateur'])
    if athlete_col is not None:
        df_display[athlete_col] = df_display[athlete_col].apply(mask_athlete_identifier)
    return df_display, athlete_col


# Détecte un export Qualtrics brut via la première cellule d'en-tête.
def is_qualtrics_format(df_raw):
    """Détecte si le DataFrame brut est un export Qualtrics (première cellule = 'StartDate')."""
    if df_raw.empty:
        return False
    return str(df_raw.iloc[0, 0]).strip() == 'StartDate'


# Convertit un export Qualtrics vers le format interne exploité par le dashboard.
def parse_qualtrics_df(df):
    """
    Transforme un DataFrame Qualtrics (codes Q en colonnes, ligne de libellés déjà ignorée)
    en DataFrame normalisé avec noms de variables et colonnes de charge calculées.
    Filtre les réponses de prévisualisation (Status contenant 'preview').
    """
    # Supprimer les lignes de prévisualisation Qualtrics
    if 'Status' in df.columns:
        df = df[~df['Status'].astype(str).str.lower().str.contains('preview', na=False)].copy()
    else:
        df = df.copy()

    # Renommer les colonnes selon le mapping Q-code → variable interne
    rename_map = {k: v for k, v in QUALTRICS_Q_TO_VAR.items() if k in df.columns}
    df = df.rename(columns=rename_map)

    # Calculer les charges : charge = durée × intensité pour chaque activité
    for dur_col, int_col, load_col in ACTIVITY_LOAD_PAIRS:
        if dur_col in df.columns and int_col in df.columns:
            dur   = pd.to_numeric(df[dur_col],  errors='coerce').fillna(0)
            inten = pd.to_numeric(df[int_col], errors='coerce').fillna(0)
            df[load_col] = dur * inten

    # Hockey load = somme des sous-activités sur glace (Pratique + Match + Skills)
    hockey_parts = [c for c in ['Pratique load', 'Match load', 'Skills load'] if c in df.columns]
    if hockey_parts:
        df['Hockey load'] = df[hockey_parts].fillna(0).sum(axis=1)

    # Garder uniquement les colonnes utiles pour l'application
    keep_cols = (
        list(QUALTRICS_Q_TO_VAR.values())
        + ['Pratique load', 'Muscu load', 'Match load', 'Skills load',
           'Cardio load', 'Sport load', 'Hockey load']
    )
    df = df[[c for c in keep_cols if c in df.columns]]

    return df


# Formate une date au format lisible en français.
def format_date_fr(value):
    dt = pd.to_datetime(value)
    return f"{dt.day:02d} {FRENCH_MONTHS[dt.month]} {dt.year}"


# Charge le fichier de comptes (CSV prioritaire, XLSX en fallback).
def read_credentials_df():
    if os.path.exists(CREDENTIALS_CSV):
        return pd.read_csv(CREDENTIALS_CSV)
    if os.path.exists(CREDENTIALS_XLSX):
        try:
            return pd.read_excel(CREDENTIALS_XLSX)
        except PermissionError:
            st.warning('Le fichier des identifiants est ouvert dans une autre application. Ferme-le pour charger les comptes.')
            return pd.DataFrame()
    return None


# Vérifie si un mot de passe est déjà hashé (bcrypt).
def is_hashed_password(password):
    return isinstance(password, str) and password.startswith(('$2a$', '$2b$', '$2y$'))


# Construit la structure d'identifiants attendue par streamlit-authenticator.
def load_user_credentials():
    df = read_credentials_df()
    if df is not None and not df.empty:
        email_col = find_column(df.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
        password_col = find_column(df.columns, ['password', 'mot de passe', 'mdp'])
        name_col = find_column(df.columns, ['name', 'nom'])
        role_col = find_column(df.columns, ['role', 'rôle'])
        athlete_id_col = find_column(df.columns, ['athlete_id', 'id', 'utilisateur'])

        if email_col is None or password_col is None:
            st.warning('Le fichier des identifiants doit contenir au moins les colonnes courriel et mot de passe.')
            return {'usernames': DEFAULT_USERS}

        credentials = {'usernames': {}}
        for _, row in df.iterrows():
            username = str(row[email_col]).strip()
            if not username or username.lower() == 'nan':
                continue
            name = str(row[name_col]).strip() if name_col and not pd.isna(row[name_col]) else username
            password = str(row[password_col]).strip()
            if is_hashed_password(password):
                hashed_password = password
            else:
                hashed_password = stauth.Hasher.hash(password)
            role = str(row[role_col]).strip() if role_col and not pd.isna(row[role_col]) else 'athlete'
            athlete_id = str(row[athlete_id_col]).strip() if athlete_id_col and not pd.isna(row[athlete_id_col]) else username
            credentials['usernames'][username] = {
                'name': name,
                'password': hashed_password,
                'role': role,
                'id': athlete_id
            }

        return credentials

    return {'usernames': DEFAULT_USERS}


users = load_user_credentials()


# Écrit les comptes utilisateurs dans le fichier CSV sécurisé.
def write_credentials_df(df):
    os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)
    try:
        df.to_csv(CREDENTIALS_CSV, index=False)
        return True
    except PermissionError:
        return False


# Sérialise les identifiants en DataFrame puis les sauvegarde.
def save_user_credentials(credentials_dict):
    rows = []
    for username, info in credentials_dict['usernames'].items():
        rows.append({
            'email': username,
            'name': info.get('name', username),
            'password': info['password'],
            'role': info.get('role', 'athlete'),
            'athlete_id': info.get('id', username)
        })
    df = pd.DataFrame(rows)
    write_credentials_df(df)


# Sauvegarde le fichier principal de données (XLSX ou CSV selon extension).
def save_data_file(df):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    try:
        if file_path.lower().endswith('.xlsx'):
            df.to_excel(file_path, index=False)
        else:
            df.to_csv(file_path, index=False)
        return True
    except PermissionError:
        return False


# Lit la date limite de disponibilité des données (metadata/max_date.txt).
def load_max_data_date():
    """Charge la date max des données disponibles"""
    metadata_file = os.path.join(DATA_ROOT, 'metadata', 'max_date.txt')
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, 'r') as f:
                date_str = f.read().strip()
                return pd.to_datetime(date_str).date()
        except Exception:
            return None
    return None


# Persiste la date limite de disponibilité des données.
def save_max_data_date(date_obj):
    """Sauvegarde la date max des données disponibles"""
    os.makedirs(os.path.join(DATA_ROOT, 'metadata'), exist_ok=True)
    metadata_file = os.path.join(DATA_ROOT, 'metadata', 'max_date.txt')
    try:
        with open(metadata_file, 'w') as f:
            f.write(str(date_obj))
        return True
    except Exception:
        return False


# Supprime les doublons basés sur la clé composite (Id + Date).
def deduplicate_data(df, existing_df=None):
    """
    Déduplique les données basées sur (Id, Date).
    Retourne (nouvelles_lignes, doublons_trouvés)
    """
    # Normaliser les dates au format YYYY-MM-DD pour comparaison cohérente
    df = df.copy()
    df['_date_key'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
    df['_id_key'] = df['Id'].astype(str).str.strip()
    df['_key'] = df['_id_key'] + '|' + df['_date_key']

    duplicates = pd.DataFrame()

    if existing_df is not None and not existing_df.empty:
        existing = existing_df.copy()
        existing['_date_key'] = pd.to_datetime(existing['Date'], format='mixed', errors='coerce').dt.strftime('%Y-%m-%d')
        existing['_id_key'] = existing['Id'].astype(str).str.strip()
        existing['_key'] = existing['_id_key'] + '|' + existing['_date_key']
        existing_keys = set(existing['_key'].dropna())
        # Séparer les doublons des nouvelles lignes
        duplicates = df[df['_key'].isin(existing_keys)].drop(columns=['_key', '_date_key', '_id_key'])
        df = df[~df['_key'].isin(existing_keys)]

    # Enlever les doublons internes au nouveau fichier
    df = df.drop_duplicates(subset=['_key'], keep='last')
    # Supprimer les colonnes temporaires
    df = df.drop(columns=['_key', '_date_key', '_id_key'])
    return df, duplicates


# Normalise un fichier importé pour garantir les colonnes Id et Date.
def normalize_uploaded_data(df):
    date_col = find_column(df.columns, ['date', 'Date'])
    athlete_id_col = find_column(df.columns, ['athlete_id', 'Id', 'utilisateur', 'Utilisateur'])
    if date_col is None or athlete_id_col is None:
        return None, None, 'Le fichier doit contenir au moins une colonne date et une colonne Id / athlete_id.'

    if date_col != 'Date':
        df = df.rename(columns={date_col: 'Date'})
    if athlete_id_col != 'Id':
        df = df.rename(columns={athlete_id_col: 'Id'})

    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
    invalid_count = df['Date'].isna().sum()
    if invalid_count > 0:
        df = df.dropna(subset=['Date'])
        if df.empty:
            return None, None, 'Toutes les dates sont invalides. Vérifie le format de la colonne date.'
        st.info(f"ℹ️ {invalid_count} ligne(s) sans date valide ignorée(s).")

    return df, 'Id', None


# Ajoute un nouvel utilisateur au fichier de comptes.
def append_user_to_file(email, name, password, role, athlete_id):
    email = str(email).strip()
    if not email:
        return False, 'invalid'

    df = read_credentials_df()
    if df is None:
        df = pd.DataFrame(columns=['email', 'name', 'password', 'role', 'athlete_id'])

    email_col = find_column(df.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
    if email_col is None:
        email_col = 'email'
    if email_col not in df.columns:
        df[email_col] = ''
    df[email_col] = df[email_col].astype(str).str.strip()
    if email.lower() in df[email_col].str.lower().tolist():
        return False, 'exists'

    hashed_password = stauth.Hasher.hash(password)
    new_row = {
        'email': email,
        'name': name,
        'password': hashed_password,
        'role': role,
        'athlete_id': athlete_id
    }
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    if not write_credentials_df(df):
        return False, 'permission'
    return True, None


# Met à jour le mot de passe d'un utilisateur existant.
def update_password_in_file(email, password):
    email = str(email).strip()
    if not os.path.exists(CREDENTIALS_CSV) and not os.path.exists(CREDENTIALS_XLSX):
        return False, 'missing'

    df = read_credentials_df()
    if df is None or df.empty:
        return False, 'missing'

    email_col = find_column(df.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
    if email_col is None:
        return False, 'missing_email_col'
    df[email_col] = df[email_col].astype(str).str.strip()
    match = df[email_col].str.lower() == email.lower()
    if not match.any():
        return False, 'not_found'
    df.loc[match, 'password'] = stauth.Hasher.hash(password)
    if not write_credentials_df(df):
        return False, 'permission'
    return True, None


# ── Gestion des tokens de réinitialisation par courriel ──────────────────────

# Récupère les informations d'authentification minimales d'un utilisateur.
def _get_user_auth_record(email):
    df = read_credentials_df()
    if df is None or df.empty:
        return None

    email_col = find_column(df.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
    password_col = find_column(df.columns, ['password', 'mot de passe', 'mdp'])
    if email_col is None or password_col is None:
        return None

    df[email_col] = df[email_col].astype(str).str.strip()
    matches = df[df[email_col].str.lower() == str(email).strip().lower()]
    if matches.empty:
        return None

    row = matches.iloc[0]
    return {
        'email': str(row[email_col]).strip().lower(),
        'password_hash': str(row[password_col]).strip()
    }


# Encode des octets au format Base64 URL-safe.
def _b64url_encode(data):
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


# Décode une chaîne Base64 URL-safe.
def _b64url_decode(data):
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# Calcule une empreinte courte du hash de mot de passe pour invalider les tokens anciens.
def _password_fingerprint(password_hash):
    return hashlib.sha256(password_hash.encode('utf-8')).hexdigest()[:16]


# Génère un token de réinitialisation signé et expirant.
def generate_reset_token(email):
    user_record = _get_user_auth_record(email)
    if user_record is None:
        return None

    payload = {
        'email': user_record['email'],
        'exp': int(time.time()) + RESET_TOKEN_EXPIRY,
        'pwd': _password_fingerprint(user_record['password_hash'])
    }
    payload_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    signature = hmac.new(
        RESET_TOKEN_SECRET.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


# Vérifie l'authenticité, la validité temporelle et la cohérence du token.
def verify_reset_token(token):
    try:
        payload_part, signature_part = str(token).split('.', 1)
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(signature_part)
    except Exception:
        return None

    expected_signature = hmac.new(
        RESET_TOKEN_SECRET.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).digest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(payload_bytes.decode('utf-8'))
    except Exception:
        return None

    if time.time() > payload.get('exp', 0):
        return None

    email = payload.get('email')
    user_record = _get_user_auth_record(email)
    if user_record is None:
        return None

    if payload.get('pwd') != _password_fingerprint(user_record['password_hash']):
        return None

    return user_record['email']


# Placeholder: les tokens sont stateless et expirent via la signature/empreinte.
def consume_reset_token(token):
    # Token stateless: après changement de mot de passe, il devient invalide automatiquement.
    return None


# Envoie le courriel de réinitialisation de mot de passe.
def send_reset_email(to_email, token):
    if not SMTP_USER or not SMTP_PASSWORD:
        return False, 'smtp_non_configure'

    reset_url = f"{APP_BASE_URL}?reset_token={token}"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = 'Réinitialisation de votre mot de passe'
    msg['From'] = SMTP_FROM
    msg['To'] = to_email

    corps = (
        f"Bonjour,\n\n"
        f"Une demande de réinitialisation de mot de passe a été reçue pour votre compte.\n\n"
        f"Cliquez sur le lien ci-dessous pour choisir un nouveau mot de passe.\n"
        f"Ce lien est valide pendant 30 minutes et ne peut être utilisé qu'une seule fois :\n\n"
        f"{reset_url}\n\n"
        f"Si vous n'avez pas fait cette demande, ignorez simplement ce courriel.\n\n"
        f"L'équipe Hockey Lab"
    )
    msg.attach(MIMEText(corps, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_FROM, to_email, msg.as_string())
        return True, None
    except smtplib.SMTPAuthenticationError:
        return False, 'auth'
    except Exception as exc:
        return False, str(exc)


with st.sidebar.expander('Créer un compte'):
    with st.form('register_form', clear_on_submit=True):
        new_email = st.text_input('Adresse courriel')
        new_name = st.text_input('Nom complet')
        new_password = st.text_input('Mot de passe', type='password')
        athlete_id = st.text_input('Identifiant athlète (facultatif)')
        if st.form_submit_button('Créer un compte'):
            if not new_email or not new_password:
                st.error('Adresse courriel et mot de passe sont requis.')
            else:
                if not athlete_id:
                    athlete_id = new_email
                created, msg = append_user_to_file(new_email, new_name or new_email, new_password, 'athlete', athlete_id)
                if created:
                    st.success('Compte créé. Recharge la page pour te connecter.')
                    st.experimental_rerun()
                elif msg == 'exists':
                    st.warning('Cette adresse courriel existe déjà. Utilise la récupération de mot de passe si nécessaire.')
                elif msg == 'permission':
                    st.error('Impossible d’écrire le fichier des identifiants. Ferme le fichier Excel ou vérifie les permissions.')
                else:
                    st.error('Impossible de créer le compte. Vérifie les informations et réessaie.')

with st.sidebar.expander('Mot de passe oublié'):
    if not SMTP_USER or not SMTP_PASSWORD:
        st.warning('Réinitialisation par courriel non configurée. Contacte un administrateur.')
    else:
        with st.form('reset_form', clear_on_submit=True):
            reset_email = st.text_input('Adresse courriel', key='reset_email')
            if st.form_submit_button('Envoyer le lien de réinitialisation'):
                if not reset_email:
                    st.error('Adresse courriel requise.')
                else:
                    df_creds = read_credentials_df()
                    email_exists = False
                    if df_creds is not None and not df_creds.empty:
                        ec = find_column(df_creds.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
                        if ec:
                            email_exists = reset_email.strip().lower() in df_creds[ec].astype(str).str.lower().str.strip().tolist()
                    if email_exists:
                        token = generate_reset_token(reset_email)
                        if token is None:
                            st.success('Si ce courriel est associé à un compte, un lien de réinitialisation a été envoyé (valide 30 minutes).')
                        else:
                            sent, err = send_reset_email(reset_email, token)
                            if not sent and err == 'auth':
                                st.error("Erreur d'authentification SMTP. Vérifie les variables SMTP_USER et SMTP_PASSWORD.")
                            elif not sent:
                                st.error(f"Erreur d'envoi : {err}")
                            else:
                                st.success('Si ce courriel est associé à un compte, un lien de réinitialisation a été envoyé (valide 30 minutes).')
                    else:
                        st.success('Si ce courriel est associé à un compte, un lien de réinitialisation a été envoyé (valide 30 minutes).')
# Charge et prépare les données d'un athlète pour le dashboard.
def load_athlete_data(athlete_id):
    if not os.path.exists(file_path):
        st.error("Fichier de données non trouvé.")
        return pd.DataFrame()

    df = pd.read_excel(file_path)
    athlete_id = str(athlete_id).strip()
    if 'Id' in df.columns:
        df['Id'] = df['Id'].astype(str).str.strip()
        df = df[df['Id'] == athlete_id].copy()
    elif 'athlete_id' in df.columns:
        df['athlete_id'] = df['athlete_id'].astype(str).str.strip()
        df = df[df['athlete_id'] == athlete_id].copy()
    else:
        st.error("Aucune colonne d'identifiant d'athlète trouvée dans le fichier.")
        return pd.DataFrame()

    if df.empty:
        return df

    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
    df = df.dropna(subset=['Date'])

    # Calculer Hockey load à partir des sous-activités s'il est absent
    hockey_sub = [c for c in ['Pratique load', 'Match load', 'Skills load'] if c in df.columns]
    if hockey_sub and 'Hockey load' not in df.columns:
        df['Hockey load'] = df[hockey_sub].fillna(0).sum(axis=1)

    # Toujours recalculer depuis les colonnes individuelles (Total load peut être NaN)
    # Insensible à la casse et exclut Hockey load pour éviter le double comptage
    load_cols = [c for c in df.columns if c.lower().endswith('load')
                 and c not in ['Total load', 'charge_totale', 'Hockey load']]
    if load_cols:
        df['charge_totale'] = df[load_cols].fillna(0).sum(axis=1)
    else:
        df['charge_totale'] = 0

    return df


# Retourne la liste des identifiants d'athlètes déclarés dans les comptes.
def get_registered_athlete_ids():
    athlete_ids = []
    for _, info in users.get('usernames', {}).items():
        role = str(info.get('role', '')).strip().lower()
        if role == 'athlete':
            athlete_id = str(info.get('id', '')).strip()
            if athlete_id and athlete_id.lower() != 'nan':
                athlete_ids.append(athlete_id)
    return sorted(set(athlete_ids), key=str.lower)


# Construit un suivi de complétude quotidienne des questionnaires sur une période.
def build_questionnaire_completeness(df_all, athlete_column, start_date, end_date):
    df_status = df_all.copy()
    df_status['Date'] = pd.to_datetime(df_status['Date'], format='mixed', errors='coerce')
    df_status = df_status.dropna(subset=['Date'])
    df_status[athlete_column] = df_status[athlete_column].astype(str).str.strip()

    period_days = pd.date_range(start=pd.Timestamp(start_date), end=pd.Timestamp(end_date), freq='D').date
    expected_day_set = set(period_days)

    # Dernière soumission globale par athlète.
    last_submission = (
        df_status.groupby(athlete_column, as_index=False)['Date']
        .max()
        .rename(columns={'Date': 'Dernière soumission'})
    )

    registered_ids = set(get_registered_athlete_ids())
    data_ids = set(df_status[athlete_column].dropna().astype(str).str.strip().tolist())
    athlete_ids = sorted(registered_ids.union(data_ids), key=str.lower)

    # Jours soumis sur la période (un seul enregistrement par jour suffit).
    in_period = df_status[
        (df_status['Date'].dt.date >= start_date) &
        (df_status['Date'].dt.date <= end_date)
    ].copy()

    grouped_days = {}
    if not in_period.empty:
        grouped_days = (
            in_period.groupby(athlete_column)['Date']
            .apply(lambda s: set(pd.to_datetime(s).dt.date.tolist()))
            .to_dict()
        )

    rows = []
    for athlete_id in athlete_ids:
        submitted_days = grouped_days.get(athlete_id, set())
        missing_days = sorted(expected_day_set - submitted_days)
        match = last_submission[last_submission[athlete_column] == athlete_id]
        last_date = match['Dernière soumission'].iloc[0].date() if not match.empty else None

        expected_count = len(expected_day_set)
        submitted_count = len(submitted_days)
        missing_count = len(missing_days)
        completion_pct = (submitted_count / expected_count * 100.0) if expected_count > 0 else 0.0

        rows.append({
            'Athlète': athlete_id,
            'Jours manquants': missing_count,
            'Complétude (%)': round(completion_pct, 1),
            'Dernière soumission': last_date,
            '_missing_days': missing_days,
        })

    completeness_df = pd.DataFrame(rows)
    if not completeness_df.empty:
        completeness_df = completeness_df.sort_values(['Jours manquants', 'Athlète'], ascending=[False, True]).reset_index(drop=True)
    return completeness_df


# Calcule la monotonie: moyenne mobile 7 jours / écart-type mobile 7 jours.
def calculate_monotony(df):
    if df.empty:
        return float('nan')
    # Normaliser la date (supprimer la composante horaire) pour grouper par jour calendaire
    df = df.copy()
    df['_date'] = pd.to_datetime(df['Date']).dt.normalize()
    daily_load = df.groupby('_date')['charge_totale'].sum()

    # Remplir les jours calendaires manquants (sans soumission) avec 0
    if len(daily_load) >= 2:
        full_range = pd.date_range(daily_load.index.min(), daily_load.index.max(), freq='D')
        daily_load = daily_load.reindex(full_range, fill_value=0)

    if len(daily_load) < 7:
        return float('nan')

    rolling_mean = daily_load.rolling(7).mean()
    rolling_std  = daily_load.rolling(7).std()

    # Éviter la division par 0 (écart-type nul)
    safe_std = rolling_std.where(rolling_std > 0, other=float('nan'))
    monotony = rolling_mean / safe_std

    valid = monotony.dropna()
    if valid.empty:
        return float('nan')
    return float(valid.iloc[-1])


# Calcule l'ACWR: charge aiguë (7j) / (charge chronique (28j) / 4).
def calculate_acwr(df):
    if df.empty:
        return float('nan')

    df = df.copy()
    df['_date'] = pd.to_datetime(df['Date']).dt.normalize()
    daily_load = df.groupby('_date')['charge_totale'].sum()

    if len(daily_load) >= 2:
        full_range = pd.date_range(daily_load.index.min(), daily_load.index.max(), freq='D')
        daily_load = daily_load.reindex(full_range, fill_value=0)

    if len(daily_load) < 28:
        return float('nan')

    acute_load = daily_load.tail(7).sum()
    chronic_load = daily_load.tail(28).sum() / 4

    if chronic_load <= 0:
        return float('nan')

    return float(acute_load / chronic_load)

# Traduit la monotonie en message clinique simple et code couleur.
def interpret_monotony(monotony_value):
    """Interprète la valeur de monotonie et retourne (texte, couleur, emoji)"""
    if monotony_value == float('inf') or pd.isna(monotony_value):
        return "Données insuffisantes", "#FFA500", "⚠️"
    
    if monotony_value < 1.0:
        return "Variabilité élevée (bon)", "#28A745", "✓"
    elif monotony_value < 2.0:
        return "Normal", "#4ECDC4", "•"
    elif monotony_value < 2.5:
        return "Répétitif", "#FFA500", "!"
    else:
        return "Trop répétitif", "#DC3545", "!"


# Traduit l'ACWR en niveau de risque et code couleur.
def interpret_acwr(acwr_value):
    if pd.isna(acwr_value) or acwr_value == float('inf'):
        return "Données insuffisantes", "#FFA500", "⚠️"

    if acwr_value < 0.5:
        return "Charge faible (les 7 derniers jours sont faibles par rapport au dernier mois)", "#4ECDC4", "↓"
    elif acwr_value <= 1.3:
        return "Zone cible (les 7 derniers jours sont stables par rapport au dernier mois)", "#28A745", "✓"
    elif acwr_value <= 1.5:
        return "Charge élevée (les 7 derniers jours sont élevés par rapport au dernier mois)", "#FFA500", "!"
    else:
        return "Charge très élevée (les 7 derniers jours sont très élevés par rapport au dernier mois)", "#DC3545", "!"


# Dessine une jauge demi-cercle paramétrable (zones colorées + aiguille).
def render_semicircle_gauge(title, value, zones, vmax, tick_values):
    gauge_value = max(0.0, min(float(value), float(vmax)))

    def value_to_angle(current_value, vmin=0.0, upper=vmax):
        ratio = (current_value - vmin) / (upper - vmin)
        return 180 - (ratio * 180)

    fig, ax = plt.subplots(figsize=(6.6, 2.9))
    ax.set_aspect('equal')

    for start, end, zone_color in zones:
        theta1 = value_to_angle(end)
        theta2 = value_to_angle(start)
        ax.add_patch(Wedge((0, 0), 1.0, theta1, theta2, width=0.24, facecolor=zone_color, edgecolor='white'))

    needle_angle = np.deg2rad(value_to_angle(gauge_value))
    needle_x = 0.68 * np.cos(needle_angle)
    needle_y = 0.68 * np.sin(needle_angle)
    ax.plot([0, needle_x], [0, needle_y], color='#111111', linewidth=2)
    ax.add_patch(Circle((0, 0), 0.035, color='#111111'))

    for tick in tick_values:
        tick_angle = np.deg2rad(value_to_angle(tick))
        x = 1.08 * np.cos(tick_angle)
        y = 1.08 * np.sin(tick_angle)
        ax.text(x, y, f"{tick:g}", ha='center', va='center', fontsize=9)

    ax.text(0, -0.10, title, ha='center', va='center', fontsize=10)
    ax.text(0, 0.20, f"{gauge_value:.2f}", ha='center', va='center', fontsize=18, fontweight='bold')

    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-0.2, 1.2)
    ax.axis('off')
    return fig


# Retourne l'activité dominante de la journée à partir des charges.
def get_main_activity(row, activity_cols):
    """Retourne l'activité principale (celle avec la plus grande charge) pour une ligne"""
    activities = {label: row.get(col, 0) for label, col in activity_cols.items()}
    if all(v == 0 or pd.isna(v) for v in activities.values()):
        return "Repos"
    main = max(activities, key=lambda k: activities[k] or 0)
    return main if activities[main] > 0 else "Repos"


# Liste toutes les activités non nulles d'une journée.
def get_all_activities(row, activity_cols):
    """Retourne toutes les activités du jour (avec charge > 0)"""
    activities = []
    for label, col in activity_cols.items():
        charge = row.get(col, 0)
        if charge > 0 and not pd.isna(charge):
            activities.append(f"{label} ({int(charge)})")
    return activities if activities else ["Repos"]


# Convertit la réponse textuelle "Activités" en statut standardisé.
def _parse_activite_status(value):
    """Classifie la réponse Q27 en étiquette affichable."""
    s = str(value).strip().lower()
    if 'blessure' in s or 'injury' in s or 'injur' in s:
        return 'Blessure'
    if 'vacance' in s or 'vacation' in s:
        return 'Vacances'
    if 'temps' in s or 'time' in s:
        return 'Manque de temps'
    if s.startswith('non') or s.startswith('no '):
        return 'Repos'
    if 'repos' in s or 'recov' in s or 'rest' in s:
        return 'Repos'
    return None  # Oui / Yes ou NaN → ne rien afficher comme statut de repos


# Génère le calendrier mensuel avec activités/stats journalières.
def create_activity_calendar(df_filtered, activity_cols):
    """Crée un calendrier HTML avec proportions des activités par jour."""
    import calendar as cal_module
    
    color_map = COLOR_PALETTE
    
    # Pour le calendrier, afficher les sous-catégories de Hockey au lieu de Hockey
    calendar_activity_cols = {label: col for label, col in activity_cols.items() if label != 'Hockey'}
    
    # Obtenir les proportions pour chaque jour
    def get_proportions(row, activity_cols):
        """Retourne dict avec activité -> charge pour créer proportion"""
        result = {}
        for label, col in activity_cols.items():
            charge = row.get(col, 0)
            if charge > 0 and not pd.isna(charge):
                result[label] = charge
        return result if result else None
    
    df_filtered_sorted = df_filtered.sort_values('Date').copy()
    df_filtered_sorted['Proportions'] = df_filtered_sorted.apply(lambda row: get_proportions(row, calendar_activity_cols), axis=1)
    
    # Créer un dictionnaire date -> proportions (seulement si des charges existent)
    proportion_dict = {
        date: props
        for date, props in zip(df_filtered_sorted['Date'].dt.date, df_filtered_sorted['Proportions'])
        if props is not None
    }

    # Dictionnaire date -> statut de repos (Repos / Blessure / Vacances / Manque de temps)
    status_dict = {}
    if 'Activités' in df_filtered_sorted.columns:
        for _, row in df_filtered_sorted.iterrows():
            val = row.get('Activités', None)
            if pd.notna(val):
                status = _parse_activite_status(val)
                if status:
                    status_dict[row['Date'].date()] = status
    
    # Obtenir les mois à afficher
    if df_filtered.empty:
        return
    
    min_date = df_filtered['Date'].dt.date.min()
    max_date = df_filtered['Date'].dt.date.max()
    
    current = min_date.replace(day=1)
    
    while current <= max_date:
        year, month = current.year, current.month
        with st.expander(f"📅 {FRENCH_MONTHS[month]} {year}"):
            # Créer une grille de dates
            cal = cal_module.monthcalendar(year, month)
            
            # Afficher le calendrier
            cols = st.columns(7)
            days_of_week = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
            
            # En-têtes jours de la semaine
            for col, day_name in zip(cols, days_of_week):
                with col:
                    st.write(f"**{day_name}**")
            
            # Dates du mois
            for week in cal:
                cols = st.columns(7)
                for col, day in zip(cols, week):
                    with col:
                        if day == 0:
                            st.write("")
                        else:
                            date_obj = pd.Timestamp(year=year, month=month, day=day).date()
                            proportions = proportion_dict.get(date_obj, None)
                            
                            if proportions:
                                # Créer la barre proportionnelle
                                total = sum(proportions.values())
                                
                                # Créer la barre stacked avec les couleurs
                                bars_html = '<div style="display: flex; height: 18px; border-radius: 3px; overflow: hidden; margin: 6px 0; width: 100%;">'
                                for activity, charge in proportions.items():
                                    percentage = (charge / total) * 100
                                    color = color_map.get(activity, '#CCCCCC')
                                    if percentage > 0:
                                        bars_html += f'<div style="width: {percentage:.1f}%; background-color: {color};" title="{activity}"></div>'
                                bars_html += '</div>'
                                
                                # Afficher les noms des activités
                                activity_names = "<br/>".join(proportions.keys())
                                
                                st.markdown(
                                    f"""
                                    <div style="padding: 8px; border-radius: 5px; background-color: #F9F9F9; min-height: 90px; display: flex; flex-direction: column; position: relative; border: 1px solid #EEE;">
                                        <div style="display: flex; align-items: flex-start; margin-bottom: 4px;">
                                            <span style="font-weight: bold; font-size: 12px;">{day}</span>
                                        </div>
                                        {bars_html}
                                        <div style="font-size: 8px; text-align: center; margin-top: 4px; line-height: 1.2;">{activity_names}</div>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                            else:
                                day_status = status_dict.get(date_obj, None)
                                if day_status:
                                    status_color = color_map.get(day_status, '#E0E0E0')
                                    text_color = '#FFFFFF' if day_status in ('Blessure', 'Vacances') else '#555555'
                                    # Icône selon le statut
                                    icons = {'Blessure': '🩹', 'Vacances': '🌴', 'Manque de temps': '⏱️', 'Repos': '😴'}
                                    icon = icons.get(day_status, '•')
                                    st.markdown(
                                        f"""
                                        <div style="background-color: {status_color}; padding: 8px; border-radius: 5px; text-align: center; min-height: 80px; display: flex; flex-direction: column; align-items: center; justify-content: center; border: 1px solid {status_color};">
                                            <span style="font-size: 12px; font-weight: bold; color: {text_color}; margin-bottom: 4px;">{day}</span>
                                            <span style="font-size: 16px;">{icon}</span>
                                            <span style="font-size: 8px; color: {text_color}; font-weight: 600; margin-top: 2px;">{day_status}</span>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )
                                else:
                                    st.markdown(
                                        f"""
                                        <div style="background-color: #F5F5F5; padding: 8px; border-radius: 5px; text-align: center; min-height: 80px; display: flex; flex-direction: column; align-items: center; justify-content: center; position: relative; border: 1px solid #E0E0E0;">
                                            <span style="font-size: 12px; font-weight: bold; color: #666; margin-bottom: 4px;">{day}</span>
                                            <span style="font-size: 9px; color: #999;">Aucune réponse</span>
                                        </div>
                                        """,
                                        unsafe_allow_html=True
                                    )
        
        # Passer au mois suivant
        if month == 12:
            current = current.replace(year=year+1, month=1)
        else:
            current = current.replace(month=month+1)


# Affiche le dashboard complet d'un athlète (graphiques, jauges, calendrier).
def show_athlete_dashboard(athlete_id):
    st.title("Préparation estivales Maitres chez nous")
    st.subheader(f"Tableau de bord - {name}")
    df = load_athlete_data(athlete_id)
    if df.empty:
        st.warning("Aucune donnée disponible pour cet athlète.")
        return

    # Définir les activités
    activity_map = {
        'Musculation': 'Muscu load',
        'Cardio': 'Cardio load',
        'Hockey': 'Hockey load',
        'Pratique': 'Pratique load',
        'Sport': 'Sport load',
        'Match': 'Match load',
        'Skills': 'Skills load'
    }
    activity_cols = {label: col for label, col in activity_map.items() if col in df.columns}

    # Afficher le calendrier avec TOUTES les données (avant les filtres)
    st.subheader("Calendrier des Activités")
    create_activity_calendar(df, activity_cols)

    st.divider()

    # Charger la date max des données disponibles
    max_data_date = load_max_data_date()
    
    # Sélecteur de plage de dates
    st.subheader("Analyse par période")
    
    # Afficher l'information sur la date limite
    if max_data_date:
        st.info(f"📅 Données disponibles jusqu'au **{format_date_fr(max_data_date)}**")
    
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Date de début",
            value=df['Date'].max() - pd.Timedelta(days=7) if not df.empty else None
        )
    with col2:
        # Limiter end_date à max_data_date s'il est défini
        default_end = df['Date'].max() if not df.empty else None
        if max_data_date and default_end:
            default_end = min(default_end, pd.Timestamp(max_data_date))
        elif max_data_date:
            default_end = pd.Timestamp(max_data_date)
        
        end_date = st.date_input(
            "Date de fin",
            value=default_end,
            max_value=max_data_date
        )

    # Filtrer les données par plage de dates
    df_filtered = df[(df['Date'].dt.date >= start_date) & (df['Date'].dt.date <= end_date)].copy()
    
    if df_filtered.empty:
        st.warning("Aucune donnée disponible pour cette plage de dates.")
        return

    # Créer deux colonnes pour les graphiques côte à côte
    col1, col2 = st.columns(2)

    # Tableau 1: Line Chart (Charge par Activité)
    with col1:
        st.subheader("Charge par Activité")
        if activity_cols:
            # Exclure les sous-catégories de hockey
            main_activity_cols_line = {label: col for label, col in activity_cols.items() if label not in ['Skills', 'Pratique', 'Match']}
            
            if main_activity_cols_line:
                # Convertir les dates en format date uniquement (sans heures)
                df_chart = df_filtered[['Date'] + list(main_activity_cols_line.values())].copy()
                df_chart['Date'] = pd.to_datetime(df_chart['Date']).dt.normalize()
                
                # Melt les données
                plot_df = df_chart.melt(
                    id_vars=['Date'],
                    value_vars=list(main_activity_cols_line.values()),
                    var_name='charge_column',
                    value_name='Charge'
                )
                plot_df['Activité'] = plot_df['charge_column'].map({v: k for k, v in main_activity_cols_line.items()})
                
                # Grouper par Date et Activité pour consolider les valeurs
                plot_df = plot_df.groupby(['Date', 'Activité'], as_index=False)['Charge'].sum()
                
                # Créer une plage complète de dates pour remplir les trous
                if not plot_df.empty:
                    min_date = plot_df['Date'].min()
                    max_date = plot_df['Date'].max()
                    date_range = pd.date_range(start=min_date, end=max_date, freq='D')
                    
                    # Créer toutes les combinaisons de (Date, Activité)
                    all_combinations = []
                    for date in date_range:
                        for activity in plot_df['Activité'].unique():
                            all_combinations.append({'Date': date, 'Activité': activity})
                    
                    complete_df = pd.DataFrame(all_combinations)
                    # Fusionner avec les données existantes et remplir les valeurs manquantes avec 0
                    plot_df = complete_df.merge(plot_df, on=['Date', 'Activité'], how='left')
                    plot_df['Charge'] = plot_df['Charge'].fillna(0)
                
                fig = px.line(plot_df, x='Date', y='Charge', color='Activité', title="Charge par Activité", 
                             color_discrete_map=COLOR_PALETTE, markers=True)
                fig.update_layout(showlegend=False)
                st.plotly_chart(fig, width='stretch')
            else:
                st.warning("Aucune activité principale détectée dans le fichier.")
        else:
            st.warning("Aucune colonne de charge d'activité détectée dans le fichier.")

    # Tableau 2: Pie Chart (Charge Totale)
    with col2:
        st.subheader("Charge Totale")
        # Exclure les sous-catégories de hockey
        main_activity_cols = {label: col for label, col in activity_cols.items() if label not in ['Skills', 'Pratique', 'Match']}
        
        if main_activity_cols:
            total_activity = df_filtered[list(main_activity_cols.values())].sum().reset_index()
            total_activity.columns = ['charge_column', 'Charge']
            total_activity['Activité'] = total_activity['charge_column'].map({v: k for k, v in main_activity_cols.items()})
            # Exclure les activités avec charge nulle ou négative
            total_activity = total_activity[total_activity['Charge'] > 0]
            
            # Définir les couleurs pour chaque activité
            color_map = {k: v for k, v in COLOR_PALETTE.items() if k in total_activity['Activité'].values}
            total_activity['Couleur'] = total_activity['Activité'].map(color_map)
            
            # Créer un graphique en camembert avec proportions
            fig2 = px.pie(total_activity, values='Charge', names='Activité', title="Charge Totale par Activité (Proportions)",
                         color='Activité', color_discrete_map=COLOR_PALETTE)
            fig2.update_traces(textposition='inside', textinfo='percent+label')
            fig2.update_layout(showlegend=False)
            st.plotly_chart(fig2, width='stretch')
        else:
            st.warning("Aucune donnée d'activité disponible pour le graphique de charge totale.")

    # Légende commune pour les graphiques du haut
    st.subheader("Légende des Couleurs")
    
    # Activités uniquement (exclure sous-catégories Hockey et statuts de non-entraînement)
    main_activities = {k: v for k, v in COLOR_PALETTE.items() if k not in ['Skills', 'Pratique', 'Match', 'Repos', 'Blessure', 'Vacances', 'Manque de temps']}
    legend_cols = st.columns(len(main_activities))
    for i, (activity, color) in enumerate(main_activities.items()):
        with legend_cols[i % len(legend_cols)]:
            st.markdown(
                f'<div style="display: flex; align-items: center; margin-bottom: 5px;">'
                f'<div style="width: 20px; height: 20px; background-color: {color}; border-radius: 3px; margin-right: 8px;"></div>'
                f'<span style="font-size: 14px;">{activity}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

    st.divider()

    st.subheader("Monotonie")
    all_monotony_dates = sorted(df['Date'].dt.date.unique().tolist())
    monotony_by_date = {}
    acwr_by_date = {}
    for date_value in all_monotony_dates:
        df_until_date = df[df['Date'].dt.date <= date_value]
        monotony_by_date[date_value] = calculate_monotony(df_until_date)
        acwr_by_date[date_value] = calculate_acwr(df_until_date)

    # Sélecteur horizontal de dates (stable, sans reset sur clic)
    def monotony_symbol(value):
        if value == float('inf') or pd.isna(value):
            return "⚪"
        if value < 1.0:
            return "🟢"
        if value < 2.0:
            return "🔵"
        if value < 2.5:
            return "🟠"
        return "🔴"

    def monotony_zone_color(value):
        if value == float('inf') or pd.isna(value):
            return '#9E9E9E'
        if value < 1.0:
            return '#28A745'
        if value < 2.0:
            return '#4ECDC4'
        if value < 2.5:
            return '#FFA500'
        return '#DC3545'

    def acwr_zone_color(value):
        if pd.isna(value) or value == float('inf'):
            return '#9E9E9E'
        if value < 0.5:
            return '#4ECDC4'
        if value <= 1.3:
            return '#28A745'
        if value <= 1.5:
            return '#FFA500'
        return '#DC3545'

    # Affichage en 2 colonnes: dates à gauche, gauge à droite
    col_dates, col_gauge = st.columns([1.45, 1], gap="large")

    month_to_dates = {}
    for date_value in all_monotony_dates:
        month_key = date_value.strftime('%Y-%m')
        month_to_dates.setdefault(month_key, []).append(date_value)

    month_options = sorted(month_to_dates.keys())
    if 'selected_monotony_date' not in st.session_state:
        st.session_state.selected_monotony_date = all_monotony_dates[-1]

    def on_monotony_month_change(radio_key, map_key):
        selected_label = st.session_state.get(radio_key)
        label_to_date = st.session_state.get(map_key, {})
        if selected_label and selected_label != "__none__":
            selected_date = label_to_date.get(selected_label)
            if selected_date is not None:
                st.session_state.selected_monotony_date = selected_date

    with col_dates:
        st.markdown("**Dates par mois**")

        css_rules = [
            "div[data-testid='stRadio'] div[role='radiogroup']{gap:4px; flex-wrap:wrap;}",
            "div[data-testid='stRadio'] div[role='radiogroup'] > label:nth-child(1){display:none;}",
            "div[data-testid='stRadio'] div[role='radiogroup'] > label p{color:white; font-weight:700; font-size:0.80rem; line-height:1.0;}",
            "div[data-testid='stRadio'] div[role='radiogroup'] > label:has(input:checked){border:3px solid #111111 !important; box-shadow: 0 0 0 1px rgba(0,0,0,0.2) inset;}"
        ]

        selected_month_key = st.session_state.selected_monotony_date.strftime('%Y-%m')

        for month_index, month_key in enumerate(month_options, start=1):
            month_dates = month_to_dates[month_key]
            month_dt = pd.to_datetime(f"{month_key}-01")
            month_title = f"{FRENCH_MONTHS[month_dt.month]} {month_dt.year}"
            st.markdown(f"**{month_title}**")

            day_labels = [d.strftime('%d') for d in month_dates]
            options = ["__none__"] + day_labels
            label_to_date = {d.strftime('%d'): d for d in month_dates}

            radio_key = f"monotony_day_radio_{month_key.replace('-', '_')}"
            map_key = f"{radio_key}_map"
            st.session_state[map_key] = label_to_date

            if month_key == selected_month_key and st.session_state.selected_monotony_date in month_dates:
                current_value = st.session_state.selected_monotony_date.strftime('%d')
            elif month_key != selected_month_key:
                current_value = "__none__"
            else:
                current_value = "__none__"

            radio_label = f"jours-{month_key}"

            st.radio(
                radio_label,
                options=options,
                index=options.index(current_value),
                key=radio_key,
                horizontal=True,
                label_visibility="collapsed",
                on_change=on_monotony_month_change,
                args=(radio_key, map_key)
            )

            for option_index, d in enumerate(month_dates, start=2):
                mono_color = monotony_zone_color(monotony_by_date.get(d, float('nan')))
                acwr_color = acwr_zone_color(acwr_by_date.get(d, float('nan')))
                split_bg = f"linear-gradient(90deg, {mono_color} 0%, {mono_color} 50%, {acwr_color} 50%, {acwr_color} 100%)"
                css_rules.append(
                    "div[role='radiogroup'][aria-label='" + radio_label + "'] > label:nth-child(" + str(option_index) + ") {"
                    + f"background:{split_bg}; border:1.5px solid rgba(0,0,0,0.22); border-radius:8px; padding:1px 7px; margin:0; min-height:unset;"
                    + "}"
                )

        st.markdown("<style>" + "".join(css_rules) + "</style>", unsafe_allow_html=True)

    monotony_date = st.session_state.selected_monotony_date
    monotony = monotony_by_date.get(monotony_date, float('nan'))
    interpretation, color, emoji = interpret_monotony(monotony)
    acwr = acwr_by_date.get(monotony_date, float('nan'))
    acwr_interpretation, acwr_color, acwr_emoji = interpret_acwr(acwr)

    with col_gauge:
        st.markdown("**Monotonie**")
        if pd.isna(monotony):
            st.metric(f"Monotonie au {monotony_date.isoformat()}", "N/A")
            st.info("Données insuffisantes pour calculer la monotonie (minimum 7 jours).")
        elif monotony == float('inf'):
            st.metric(f"Monotonie au {monotony_date.isoformat()}", "∞")
            st.info("La monotonie est infinie (variance nulle sur la fenêtre).")
        else:
            fig = render_semicircle_gauge(
                f"Monotonie au {monotony_date.isoformat()}",
                monotony,
                [
                    (0.0, 1.0, '#28A745'),
                    (1.0, 2.0, '#4ECDC4'),
                    (2.0, 2.5, '#FFA500'),
                    (2.5, 3.5, '#DC3545'),
                ],
                3.5,
                [0.0, 1.0, 2.0, 2.5, 3.5],
            )
            st.pyplot(fig, width='stretch')
            plt.close(fig)

        st.markdown(
            f"<div style='background-color: {color}; padding: 10px; border-radius: 8px; color: white; font-weight: 600; text-align: center;'>{emoji} {interpretation}</div>",
            unsafe_allow_html=True
        )

        st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
        st.markdown("**ACWR**")

        if pd.isna(acwr):
            st.metric(f"ACWR au {monotony_date.isoformat()}", "N/A")
            st.info("Données insuffisantes pour calculer l'ACWR (minimum 28 jours).")
        else:
            acwr_fig = render_semicircle_gauge(
                f"ACWR au {monotony_date.isoformat()}",
                acwr,
                [
                    (0.0, 0.5, '#4ECDC4'),
                    (0.5, 1.3, '#28A745'),
                    (1.3, 1.5, '#FFA500'),
                    (1.5, 2.0, '#DC3545'),
                ],
                2.0,
                [0.0, 0.5, 1.3, 1.5, 2.0],
            )
            st.pyplot(acwr_fig, width='stretch')
            plt.close(acwr_fig)

        st.markdown(
            f"<div style='background-color: {acwr_color}; padding: 10px; border-radius: 8px; color: white; font-weight: 600; text-align: center;'>{acwr_emoji} {acwr_interpretation}</div>",
            unsafe_allow_html=True
        )

# Vue coach: sélection d'un athlète puis affichage de son dashboard.
def show_coach_dashboard():
    st.title("Tableau de bord coach - Tous les athlètes")
    if not os.path.exists(file_path):
        st.error("Fichier de données non trouvé.")
        return

    df_all = pd.read_excel(file_path)
    athlete_column = 'Id' if 'Id' in df_all.columns else 'athlete_id' if 'athlete_id' in df_all.columns else None
    if athlete_column is None:
        st.error("Aucune colonne d'identifiant d'athlète trouvée dans le fichier.")
        return

    if 'Date' not in df_all.columns:
        st.error("Aucune colonne de date trouvée dans le fichier.")
        return

    df_all[athlete_column] = df_all[athlete_column].astype(str).str.strip()
    athletes = sorted(df_all[athlete_column].dropna().unique().tolist())

    st.subheader("Suivi des questionnaires")
    parsed_dates = pd.to_datetime(df_all['Date'], format='mixed', errors='coerce').dropna()
    latest_data_date = parsed_dates.max().date() if not parsed_dates.empty else pd.Timestamp.now().date()
    configured_max_date = load_max_data_date()
    default_end_date = configured_max_date or latest_data_date
    fixed_start_date = pd.Timestamp('2026-04-27').date()
    period_start = fixed_start_date if fixed_start_date <= default_end_date else default_end_date
    period_end = default_end_date

    min_missing_threshold = 3

    completeness_df = build_questionnaire_completeness(df_all, athlete_column, period_start, period_end)
    if completeness_df.empty:
        st.info("Aucun athlète à afficher pour le suivi.")
    else:
        fully_complete_count = int((completeness_df['Jours manquants'] == 0).sum())
        alert_df = completeness_df[completeness_df['Jours manquants'] >= int(min_missing_threshold)].copy()
        alert_count = len(alert_df)
        total_count = len(completeness_df)

        c1, c2, c3 = st.columns(3)
        c1.metric("Total athlètes", total_count)
        c2.metric("A rempli tous les jours", fully_complete_count)
        c3.metric("Manque >= 3 jours", alert_count)

        st.caption(
            f"Période analysée: {period_start.isoformat()} à {period_end.isoformat()} "
            f"({(pd.Timestamp(period_end) - pd.Timestamp(period_start)).days + 1} jours)"
        )

        if alert_df.empty:
            st.success(f"Aucun athlète ne manque {int(min_missing_threshold)} jours ou plus sur la période.")
        else:
            display_alert_df = alert_df.drop(columns=['_missing_days'])
            st.dataframe(display_alert_df, width='stretch', hide_index=True)

        with st.expander("Voir le détail complet par athlète"):
            st.dataframe(completeness_df.drop(columns=['_missing_days']), width='stretch', hide_index=True)

    st.divider()

    selected_athlete = st.selectbox("Sélectionner un athlète", athletes)
    if selected_athlete:
        show_athlete_dashboard(selected_athlete)


# Vue admin: gestion des utilisateurs, import et édition des données.
def show_admin_dashboard():
    st.title("Administration des données")
    st.markdown("Importez un fichier Qualtrics ou un fichier de données d'entraînement. Seuls les rôles `admin` ou `data_manager` peuvent importer des données.")
    st.caption("Identifiants athlètes masqués dans la vue admin. Réidentification possible via les codes définis dans APP_REID_CODEBOOK / APP_REID_SECRET_KEY (secrets).")
    
    # Section Gestion des Utilisateurs
    st.subheader("👥 Gestion des Participants")
    credentials_df = read_credentials_df()
    if credentials_df is not None and not credentials_df.empty:
        st.markdown("**Participants inscrits** : Vous pouvez éditer les données, mais les suppressions ne peuvent pas être annulées.")
        
        edited_users = st.data_editor(
            credentials_df,
            width='stretch',
            num_rows="dynamic",
            key="admin_users_editor",
            hide_index=False
        )
        
        col_users_save, col_users_info = st.columns([1, 3])
        with col_users_save:
            if st.button("💾 Sauvegarder les modifications", key="save_users"):
                try:
                    write_credentials_df(edited_users)
                    st.success(f"Participants sauvegardés ({len(edited_users)} utilisateurs).")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")
        with col_users_info:
            st.info(f"Total : {len(credentials_df)} utilisateurs | Après modification : {len(edited_users)} utilisateurs")
    else:
        st.warning("Aucun participant trouvé.")
    
    st.divider()

    uploaded_file = st.file_uploader("Choisir un fichier à importer", type=['csv', 'xlsx'])
    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith('.csv'):
                new_df = pd.read_csv(uploaded_file)
            else:
                # Lire la première ligne pour détecter le format Qualtrics
                df_peek = pd.read_excel(uploaded_file, header=None, nrows=1)
                uploaded_file.seek(0)
                if is_qualtrics_format(df_peek):
                    # Format Qualtrics : ligne 0 = codes Q, ligne 1 = libellés (à ignorer)
                    new_df = pd.read_excel(uploaded_file, header=0, skiprows=[1])
                    new_df = parse_qualtrics_df(new_df)
                else:
                    new_df = pd.read_excel(uploaded_file)
        except Exception as exc:
            st.error(f"Impossible de lire le fichier : {exc}")
            return

        st.write("Aperçu du fichier importé")
        preview_df, _ = anonymize_athlete_column_for_admin(new_df.head())
        st.dataframe(preview_df)

        df_normalized, id_column, error = normalize_uploaded_data(new_df)
        if error:
            st.error(error)
            return

        st.subheader("Définir la date limite des données")
        max_date_in_file = df_normalized['Date'].max().date() if not df_normalized.empty else pd.Timestamp.now().date()
        max_data_date = st.date_input(
            "Jusqu'à quelle date les données sont-elles à jour?",
            value=max_date_in_file,
            help="Cette date sera affichée aux coachs et athlètes comme limite pour consulter les données."
        )

        if st.button("Ajouter ces données au fichier principal"):
            existing_df = pd.read_excel(file_path) if os.path.exists(file_path) else pd.DataFrame()

            # Dédupliquer les données importées (enlever les doublons Id + Date)
            df_deduplicated, duplicates_found = deduplicate_data(df_normalized, existing_df)

            # Afficher le rapport des doublons
            if not duplicates_found.empty:
                st.warning(f"⚠️ {len(duplicates_found)} ligne(s) déjà présente(s) dans la base — ignorées :")
                activity_cols_report = [c for c in duplicates_found.columns if 'load' in c.lower()]
                report_rows = []
                for _, row in duplicates_found.iterrows():
                    athlete = mask_athlete_identifier(row.get('Id', '?'))
                    date = pd.to_datetime(row.get('Date'), errors='coerce')
                    date_str = date.strftime('%d/%m/%Y') if not pd.isna(date) else '?'
                    activities = [c.replace(' load', '').replace(' Load', '') for c in activity_cols_report if not pd.isna(row.get(c)) and row.get(c, 0) > 0]
                    activities_str = ', '.join(activities) if activities else 'Aucune activité'
                    report_rows.append({'Athlète': athlete, 'Date': date_str, 'Activités': activities_str})
                st.dataframe(pd.DataFrame(report_rows), width='stretch')

            st.write(f"**{len(df_deduplicated)}** nouvelle(s) ligne(s) importée(s).")

            # Combiner les données existantes avec les nouvelles données dédupliquées
            combined = pd.concat([existing_df, df_deduplicated], ignore_index=True)

            if save_data_file(combined):
                # Sauvegarder la date max
                if save_max_data_date(max_data_date):
                    st.success(f"Données importées dans {file_path}. Date limite définie au {max_data_date}.")
                else:
                    st.success(f"Données importées dans {file_path}. (Attention: impossible de sauvegarder la date limite)")
            else:
                st.error("Impossible d'écrire le fichier principal. Ferme-le dans Excel ou vérifie les permissions.")
    st.subheader("Toutes les données")
    if os.path.exists(file_path):
        try:
            all_data = pd.read_excel(file_path)
            all_data_admin_view, athlete_col = anonymize_athlete_column_for_admin(all_data)
            
            st.markdown("**Modifier ou supprimer des lignes** : Cochez les cases pour supprimer, éditez les cellules directement, puis cliquez sur **Sauvegarder les modifications**.")
            st.caption("La colonne identifiant athlète est masquée dans la vue admin pour limiter la divulgation d'information.")
            
            # Tableau éditable avec colonne de sélection pour suppression
            edited_df = st.data_editor(
                all_data_admin_view,
                width='stretch',
                num_rows="dynamic",
                key="admin_data_editor"
            )
            
            col_save, col_info = st.columns([1, 3])
            with col_save:
                if st.button("💾 Sauvegarder les modifications", key="save_data"):
                    restored_df = edited_df.copy()

                    # Restaurer les identifiants réels pour conserver l'intégrité des dashboards.
                    if athlete_col is not None and athlete_col in restored_df.columns:
                        if len(restored_df) > len(all_data):
                            st.error("Ajout de nouvelles lignes désactivé dans la vue anonymisée. Utilise l'import de fichier pour ajouter des données.")
                            return
                        common_idx = restored_df.index.intersection(all_data.index)
                        restored_df.loc[common_idx, athlete_col] = all_data.loc[common_idx, athlete_col]

                    if save_data_file(restored_df):
                        st.success(f"Données sauvegardées ({len(edited_df)} lignes).")
                        st.rerun()
                    else:
                        st.error("Impossible d'écrire le fichier. Ferme-le dans Excel ou vérifie les permissions.")
            with col_info:
                st.info(f"Total : {len(all_data)} lignes | Après modification : {len(edited_df)} lignes")
        except Exception as exc:
            st.error(f"Impossible de lire les données : {exc}")
    else:
        st.warning("Fichier de données non trouvé.")


reset_token_param = st.query_params.get('reset_token')
if reset_token_param:
    if isinstance(reset_token_param, list):
        reset_token_param = reset_token_param[0]

    email_from_token = verify_reset_token(reset_token_param)
    if email_from_token is None:
        st.error('Ce lien de réinitialisation est invalide ou a expiré. Demande un nouveau lien.')
    else:
        st.title('Choisir un nouveau mot de passe')
        st.info(f'Réinitialisation pour : **{email_from_token}**')

        with st.form('password_reset_token_form'):
            new_password = st.text_input('Nouveau mot de passe', type='password', key='token_new_password')
            confirm_password = st.text_input('Confirmer le mot de passe', type='password', key='token_confirm_password')

            if st.form_submit_button('Enregistrer le nouveau mot de passe'):
                if not new_password or not confirm_password:
                    st.error('Les deux champs de mot de passe sont requis.')
                elif new_password != confirm_password:
                    st.error('Les mots de passe ne correspondent pas.')
                else:
                    updated, msg = update_password_in_file(email_from_token, new_password)
                    if updated:
                        consume_reset_token(reset_token_param)
                        st.query_params.clear()
                        st.success('Mot de passe mis à jour. Tu peux maintenant te connecter.')
                        st.rerun()
                    elif msg == 'permission':
                        st.error('Impossible d’écrire le fichier des identifiants. Vérifie les permissions.')
                    else:
                        st.error('Impossible de mettre à jour le mot de passe. Réessaie ou contacte un administrateur.')

    st.stop()

authenticator = stauth.Authenticate(
    credentials=users,
    cookie_name='workout_dashboard',
    key=AUTH_COOKIE_KEY,
    cookie_expiry_days=30
)

try:
    authenticator.login(
        'main',
        fields={
            'Form name': 'Connexion',
            'Username': "Nom d'utilisateur",
            'Password': 'Mot de passe',
            'Login': 'Se connecter'
        }
    )
except Exception as exc:
    # Happens when an old cookie refers to a user not present/authorized anymore.
    if 'User not authorized' in str(exc):
        try:
            authenticator.cookie_controller.delete_cookie()
        except Exception:
            pass
        st.session_state['authentication_status'] = None
        st.session_state.pop('username', None)
        st.session_state.pop('name', None)
        st.warning('Session invalide détectée. Reconnecte-toi.')
    else:
        raise

authentication_status = st.session_state.get('authentication_status')
name = st.session_state.get('name')
username = st.session_state.get('username')

if authentication_status:
    authenticator.logout('Se déconnecter', 'main')
    st.write(f'Bienvenue *{name}*')
    user_role = users['usernames'][username]['role']
    if user_role == 'athlete':
        athlete_id = users['usernames'][username]['id']
        show_athlete_dashboard(athlete_id)
    elif user_role == 'coach':
        show_coach_dashboard()
    elif user_role in ['admin', 'data_manager']:
        show_admin_dashboard()
elif authentication_status == False:
    st.error("Nom d'utilisateur ou mot de passe incorrect")
elif authentication_status is None:
    st.warning("Veuillez entrer votre nom d'utilisateur et votre mot de passe")
