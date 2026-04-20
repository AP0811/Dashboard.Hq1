import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import os
import smtplib
import secrets
import time
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle

# Configuration de la page
st.set_page_config(layout="wide", page_title="Dashboard Entraînement")

# Palette de couleurs cohérente pour toutes les visualisations
COLOR_PALETTE = {
    'Musculation': '#FF6B6B',  # Rouge
    'Cardio': '#4ECDC4',      # Turquoise
    'Hockey': '#45B7D1',      # Bleu principal
    'Sport': '#FFA07A',       # Orange
    'Habiletés': '#7FB3D5',   # Bleu clair (nuance de Hockey)
    'Pratique': '#2E86AB',    # Bleu moyen (nuance de Hockey)
    'Match': '#1B4F72',       # Bleu foncé (nuance de Hockey)
    'Repos': '#E0E0E0'        # Gris
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

# Configuration des utilisateurs
# En production, utiliser une base de données sécurisée et une gestion des rôles centralisée
PRIVATE_DATA_DIR = 'private_data'


def resolve_data_root():
    # Priorité: variable d'environnement > private_data
    env_data_dir = os.getenv('APP_DATA_DIR')
    if env_data_dir:
        return env_data_dir
    return PRIVATE_DATA_DIR


DATA_ROOT = resolve_data_root()
AUTH_COOKIE_KEY = os.getenv('APP_AUTH_COOKIE_KEY', 'workout_dashboard_cookie_key_change_me_2026_32_plus_chars')

# Configuration SMTP — priorité: st.secrets > variables d'environnement
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
RESET_TOKEN_EXPIRY = 1800  # 30 minutes

CREDENTIALS_FOLDER = os.path.join(DATA_ROOT, 'credentials')
CREDENTIALS_XLSX = os.path.join(CREDENTIALS_FOLDER, 'users.xlsx')
CREDENTIALS_CSV = os.path.join(CREDENTIALS_FOLDER, 'users.csv')

DEFAULT_USERS = {
    "coach1": {"name": "Coach 1", "password": "coachpass", "role": "coach", "id": "coach1"},
    "admin": {"name": "Admin", "password": "adminpass", "role": "admin", "id": "admin"}
}

file_path = os.path.join(DATA_ROOT, 'Activités.xlsx') if os.path.exists(os.path.join(DATA_ROOT, 'Activités.xlsx')) else os.path.join(DATA_ROOT, 'trainings.xlsx')


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


def format_date_fr(value):
    dt = pd.to_datetime(value)
    return f"{dt.day:02d} {FRENCH_MONTHS[dt.month]} {dt.year}"


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


def is_hashed_password(password):
    return isinstance(password, str) and password.startswith(('$2a$', '$2b$', '$2y$'))


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


def write_credentials_df(df):
    os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)
    try:
        df.to_csv(CREDENTIALS_CSV, index=False)
        return True
    except PermissionError:
        return False


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
    if df['Date'].isna().any():
        return None, None, 'Certaines dates sont invalides. Vérifie le format de la colonne date.'

    return df, 'Id', None


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

def _tokens_file():
    return os.path.join(DATA_ROOT, 'metadata', 'reset_tokens.json')


def _load_tokens():
    path = _tokens_file()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_tokens(tokens):
    os.makedirs(os.path.dirname(_tokens_file()), exist_ok=True)
    with open(_tokens_file(), 'w') as f:
        json.dump(tokens, f)


def generate_reset_token(email):
    tokens = _load_tokens()
    now = time.time()
    # Nettoyer les tokens expirés
    tokens = {k: v for k, v in tokens.items() if v['expires_at'] > now}
    token = secrets.token_urlsafe(32)
    tokens[token] = {'email': email.strip().lower(), 'expires_at': now + RESET_TOKEN_EXPIRY}
    _save_tokens(tokens)
    return token


def verify_reset_token(token):
    tokens = _load_tokens()
    entry = tokens.get(str(token))
    if not entry:
        return None
    if time.time() > entry['expires_at']:
        return None
    return entry['email']


def consume_reset_token(token):
    tokens = _load_tokens()
    tokens.pop(str(token), None)
    _save_tokens(tokens)


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
        f"L'équipe Dashboard Entraînement"
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
                        sent, err = send_reset_email(reset_email, token)
                        if not sent and err == 'auth':
                            st.error("Erreur d'authentification SMTP. Vérifie les variables SMTP_USER et SMTP_PASSWORD.")
                        elif not sent:
                            st.error(f"Erreur d'envoi : {err}")
                        else:
                            st.success('Si ce courriel est associé à un compte, un lien de réinitialisation a été envoyé (valide 30 minutes).')
                    else:
                        st.success('Si ce courriel est associé à un compte, un lien de réinitialisation a été envoyé (valide 30 minutes).')
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

    if 'Total load' in df.columns:
        df['charge_totale'] = df['Total load']
    else:
        load_cols = [c for c in df.columns if c.endswith('load') and c not in ['Total load', 'charge_totale']]
        if load_cols:
            df['charge_totale'] = df[load_cols].sum(axis=1)
        else:
            df['charge_totale'] = 0

    return df


def calculate_monotony(df):
    if df.empty:
        return 0
    daily_load = df.groupby('Date')['charge_totale'].sum()
    rolling_mean = daily_load.rolling(7).mean()
    rolling_std = daily_load.rolling(7).std()
    monotony = rolling_mean / rolling_std
    # Retourner la dernière valeur valide
    if monotony.empty or pd.isna(monotony.iloc[-1]):
        return 0
    return monotony.iloc[-1]

def interpret_monotony(monotony_value):
    """Interprète la valeur de monotonie et retourne (texte, couleur, emoji)"""
    if monotony_value == float('inf') or pd.isna(monotony_value):
        return "Données insuffisantes", "#FFA500", "⚠️"
    
    if monotony_value < 1.0:
        return "Variabilité élevée ✅ (bon)", "#28A745", "✓"
    elif monotony_value < 2.0:
        return "Normal ✓", "#4ECDC4", "•"
    elif monotony_value < 2.5:
        return "⚠️ Risque (trop répétitif)", "#FFA500", "!"
    else:
        return "🔥 Risque élevé (blessure/fatigue)", "#DC3545", "!"


def get_main_activity(row, activity_cols):
    """Retourne l'activité principale (celle avec la plus grande charge) pour une ligne"""
    activities = {label: row.get(col, 0) for label, col in activity_cols.items()}
    if all(v == 0 or pd.isna(v) for v in activities.values()):
        return "Repos"
    main = max(activities, key=lambda k: activities[k] or 0)
    return main if activities[main] > 0 else "Repos"


def get_all_activities(row, activity_cols):
    """Retourne toutes les activités du jour (avec charge > 0)"""
    activities = []
    for label, col in activity_cols.items():
        charge = row.get(col, 0)
        if charge > 0 and not pd.isna(charge):
            activities.append(f"{label} ({int(charge)})")
    return activities if activities else ["Repos"]


def create_activity_calendar(df_filtered, activity_cols):
    """Crée un calendrier HTML avec proportions des activités par jour et monotonie"""
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
        return result if result else {'Repos': 1}
    
    df_filtered_sorted = df_filtered.sort_values('Date').copy()
    df_filtered_sorted['Proportions'] = df_filtered_sorted.apply(lambda row: get_proportions(row, calendar_activity_cols), axis=1)
    
    # Créer un dictionnaire date -> proportions
    proportion_dict = dict(zip(df_filtered_sorted['Date'].dt.date, df_filtered_sorted['Proportions']))
    
    # Pré-calculer la monotonie cumulée jusqu'à chaque date
    monotony_dict = {}
    for i, row in df_filtered_sorted.iterrows():
        date = row['Date'].date()
        df_until_date = df_filtered_sorted[df_filtered_sorted['Date'].dt.date <= date]
        monotony_dict[date] = calculate_monotony(df_until_date)
    
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
                            monotony = monotony_dict.get(date_obj, None)
                            
                            if proportions:
                                # Créer la barre proportionnelle
                                total = sum(proportions.values())
                                
                                # Monotonie en haut à droite
                                monotony_text = "∞" if monotony == float('inf') else f"{monotony:.1f}"
                                
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
                                        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
                                            <span style="font-weight: bold; font-size: 12px;">{day}</span>
                                            <span style="font-size: 9px; background-color: rgba(0,0,0,0.1); padding: 2px 4px; border-radius: 3px; font-weight: bold;">{monotony_text}</span>
                                        </div>
                                        {bars_html}
                                        <div style="font-size: 8px; text-align: center; margin-top: 4px; line-height: 1.2;">{activity_names}</div>
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


def show_athlete_dashboard(athlete_id):
    st.title(f"Tableau de bord - {athlete_id}")
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
        'Habiletés': 'Skills load'
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
            main_activity_cols_line = {label: col for label, col in activity_cols.items() if label not in ['Habiletés', 'Pratique', 'Match']}
            
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
        main_activity_cols = {label: col for label, col in activity_cols.items() if label not in ['Habiletés', 'Pratique', 'Match']}
        
        if main_activity_cols:
            total_activity = df_filtered[list(main_activity_cols.values())].sum().reset_index()
            total_activity.columns = ['charge_column', 'Charge']
            total_activity['Activité'] = total_activity['charge_column'].map({v: k for k, v in main_activity_cols.items()})
            
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
    
    # Créer une légende avec les couleurs utilisées (exclure les sous-catégories et Repos)
    main_activities = {k: v for k, v in COLOR_PALETTE.items() if k not in ['Habiletés', 'Pratique', 'Match', 'Repos']}
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
    for date_value in all_monotony_dates:
        df_until_date = df[df['Date'].dt.date <= date_value]
        monotony_by_date[date_value] = calculate_monotony(df_until_date)

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
            return '#FFA500'
        if value < 1.0:
            return '#28A745'
        if value < 2.0:
            return '#4ECDC4'
        if value < 2.5:
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
                zone_color = monotony_zone_color(monotony_by_date.get(d, 0))
                css_rules.append(
                    "div[role='radiogroup'][aria-label='" + radio_label + "'] > label:nth-child(" + str(option_index) + ") {"
                    + f"background:{zone_color}; border:1.5px solid {zone_color}; border-radius:8px; padding:1px 7px; margin:0; min-height:unset;"
                    + "}"
                )

        st.markdown("<style>" + "".join(css_rules) + "</style>", unsafe_allow_html=True)

    monotony_date = st.session_state.selected_monotony_date
    monotony = monotony_by_date.get(monotony_date, 0)
    interpretation, color, emoji = interpret_monotony(monotony)

    with col_gauge:
        if monotony == float('inf'):
            st.metric(f"Monotonie au {monotony_date.isoformat()}", "∞")
            st.info("La monotonie est infinie (variance nulle sur la fenêtre).")
        else:
            gauge_value = max(0.0, min(float(monotony), 3.5))

            def value_to_angle(value, vmin=0.0, vmax=3.5):
                # 0 -> 180 deg (gauche), 3.5 -> 0 deg (droite)
                ratio = (value - vmin) / (vmax - vmin)
                return 180 - (ratio * 180)

            fig, ax = plt.subplots(figsize=(6.6, 2.9))
            ax.set_aspect('equal')

            zones = [
                (0.0, 1.0, '#28A745'),
                (1.0, 2.0, '#4ECDC4'),
                (2.0, 2.5, '#FFA500'),
                (2.5, 3.5, '#DC3545'),
            ]

            for start, end, zone_color in zones:
                theta1 = value_to_angle(end)
                theta2 = value_to_angle(start)
                ax.add_patch(Wedge((0, 0), 1.0, theta1, theta2, width=0.24, facecolor=zone_color, edgecolor='white'))

            needle_angle = np.deg2rad(value_to_angle(gauge_value))
            needle_x = 0.68 * np.cos(needle_angle)
            needle_y = 0.68 * np.sin(needle_angle)
            ax.plot([0, needle_x], [0, needle_y], color='#111111', linewidth=3)
            ax.add_patch(Circle((0, 0), 0.035, color='#111111'))

            for tick in [0.0, 1.0, 2.0, 2.5, 3.5]:
                tick_angle = np.deg2rad(value_to_angle(tick))
                x = 1.08 * np.cos(tick_angle)
                y = 1.08 * np.sin(tick_angle)
                ax.text(x, y, f"{tick:g}", ha='center', va='center', fontsize=9)

            ax.text(0, -0.10, f"Monotonie au {monotony_date.isoformat()}", ha='center', va='center', fontsize=10)
            ax.text(0, 0.20, f"{gauge_value:.2f}", ha='center', va='center', fontsize=18, fontweight='bold')

            ax.set_xlim(-1.2, 1.2)
            ax.set_ylim(-0.2, 1.2)
            ax.axis('off')
            st.pyplot(fig, width='stretch')
            plt.close(fig)

        st.markdown(
            f"<div style='background-color: {color}; padding: 10px; border-radius: 8px; color: white; font-weight: 600; text-align: center;'>{emoji} {interpretation}</div>",
            unsafe_allow_html=True
        )

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

    df_all[athlete_column] = df_all[athlete_column].astype(str).str.strip()
    athletes = sorted(df_all[athlete_column].dropna().unique().tolist())
    selected_athlete = st.selectbox("Sélectionner un athlète", athletes)
    if selected_athlete:
        show_athlete_dashboard(selected_athlete)


def show_admin_dashboard():
    st.title("Administration des données")
    st.markdown("Importez un fichier Qualtrics ou un fichier de données d'entraînement. Seuls les rôles `admin` ou `data_manager` peuvent importer des données.")
    
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
                new_df = pd.read_excel(uploaded_file)
        except Exception as exc:
            st.error(f"Impossible de lire le fichier : {exc}")
            return

        st.write("Aperçu du fichier importé")
        st.dataframe(new_df.head())

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
                    athlete = str(row.get('Id', '?'))
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
            
            st.markdown("**Modifier ou supprimer des lignes** : Cochez les cases pour supprimer, éditez les cellules directement, puis cliquez sur **Sauvegarder les modifications**.")
            
            # Tableau éditable avec colonne de sélection pour suppression
            edited_df = st.data_editor(
                all_data,
                width='stretch',
                num_rows="dynamic",
                key="admin_data_editor"
            )
            
            col_save, col_info = st.columns([1, 3])
            with col_save:
                if st.button("💾 Sauvegarder les modifications", key="save_data"):
                    if save_data_file(edited_df):
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
