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
import re
import tomllib
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Wedge, Circle
from collections.abc import Mapping

try:
    import fitz  # PyMuPDF
except Exception:
    fitz = None

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
    'Q29':    'Sommeil (questionnaire)',
    'Q30':    'Fatigue (questionnaire)',
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
APP_DIR = Path(__file__).resolve().parent
PRIVATE_DATA_DIR = APP_DIR / 'private_data'
LEGACY_DATA_DIR = APP_DIR / 'data'


# Détermine où lire/écrire les données de l'application.
def resolve_data_root():
    # Priorité: variable d'environnement > private_data > data (legacy)
    env_data_dir = os.getenv('APP_DATA_DIR')
    if env_data_dir:
        env_path = Path(env_data_dir)
        if not env_path.is_absolute():
            env_path = APP_DIR / env_path
        return str(env_path.resolve())

    private_path = PRIVATE_DATA_DIR
    legacy_path = LEGACY_DATA_DIR

    private_has_data = (private_path / 'Activités.xlsx').exists() or (private_path / 'trainings.xlsx').exists()
    legacy_has_data = (legacy_path / 'Activités.xlsx').exists() or (legacy_path / 'trainings.xlsx').exists()

    if private_has_data:
        return str(private_path)
    if legacy_has_data:
        return str(legacy_path)
    return str(private_path)


DATA_ROOT = resolve_data_root()
AUTH_COOKIE_KEY = os.getenv('APP_AUTH_COOKIE_KEY', 'workout_dashboard_cookie_key_change_me_2026_32_plus_chars')

# Configuration SMTP — priorité: st.secrets > variables d'environnement
# Récupère une variable de config depuis st.secrets ou les variables d'environnement.
def _secret(key, default=''):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)

AUTH_COOKIE_KEY = _secret('APP_AUTH_COOKIE_KEY', AUTH_COOKIE_KEY)
SMTP_HOST     = _secret('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT     = int(_secret('SMTP_PORT', '587'))
SMTP_USER     = _secret('SMTP_USER', '')
SMTP_PASSWORD = _secret('SMTP_PASSWORD', '')
SMTP_FROM     = _secret('SMTP_FROM', SMTP_USER)
APP_BASE_URL  = _secret('APP_BASE_URL', 'http://localhost:8501')
RESET_TOKEN_SECRET = _secret('APP_RESET_TOKEN_SECRET', AUTH_COOKIE_KEY)
RESET_TOKEN_EXPIRY = 1800  # 30 minutes

# Configuration Cloudflare R2 (compatible API S3)
R2_ENABLED = _secret('R2_ENABLED', 'false').lower() == 'true'
R2_ACCOUNT_ID = _secret('R2_ACCOUNT_ID', '')
R2_BUCKET = _secret('R2_BUCKET', '')
R2_ACCESS_KEY_ID = _secret('R2_ACCESS_KEY_ID', '')
R2_SECRET_ACCESS_KEY = _secret('R2_SECRET_ACCESS_KEY', '')
R2_ENDPOINT_URL = _secret('R2_ENDPOINT_URL', '')


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
ATHLETE_DOCS_FOLDER = os.path.join(DATA_ROOT, 'documents')
ATHLETE_DOCS_INDEX = os.path.join(ATHLETE_DOCS_FOLDER, 'athlete_docs_index.json')

DEFAULT_USERS = {
    "coach1": {"name": "Coach 1", "password": "coachpass", "role": "coach", "id": "coach1"},
    "admin": {"name": "Admin", "password": "adminpass", "role": "admin", "id": "admin"}
}

file_path = os.path.join(DATA_ROOT, 'Activités.xlsx') if os.path.exists(os.path.join(DATA_ROOT, 'Activités.xlsx')) else os.path.join(DATA_ROOT, 'trainings.xlsx')

# Clés objets R2 (personnalisables)
R2_ACTIVITIES_OBJECT_KEY = _secret('R2_ACTIVITIES_OBJECT_KEY', f"private_data/{os.path.basename(file_path)}")
R2_CREDENTIALS_OBJECT_KEY = _secret('R2_CREDENTIALS_OBJECT_KEY', 'private_data/credentials/users.csv')
R2_DOCUMENTS_PREFIX = _secret('R2_DOCUMENTS_PREFIX', 'private_data/documents').rstrip('/')
R2_ATHLETE_DOCS_INDEX_OBJECT_KEY = _secret('R2_ATHLETE_DOCS_INDEX_OBJECT_KEY', f"{R2_DOCUMENTS_PREFIX}/athlete_docs_index.json")


def _r2_is_configured():
    return all([
        R2_ENABLED,
        R2_BUCKET,
        R2_ACCESS_KEY_ID,
        R2_SECRET_ACCESS_KEY,
        R2_ENDPOINT_URL or R2_ACCOUNT_ID,
    ])


def _get_r2_client():
    if not _r2_is_configured():
        return None
    try:
        import importlib
        boto3 = importlib.import_module('boto3')
        endpoint_url = R2_ENDPOINT_URL or f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return boto3.client(
            's3',
            endpoint_url=endpoint_url,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name='auto',
        )
    except Exception:
        return None


def _r2_download_object_to_path(object_key, local_path):
    client = _get_r2_client()
    if client is None:
        return False
    try:
        response = client.get_object(Bucket=R2_BUCKET, Key=object_key)
        data = response['Body'].read()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(data)
        return True
    except Exception:
        return False


def _r2_upload_path(object_key, local_path):
    client = _get_r2_client()
    if client is None or not os.path.exists(local_path):
        return False
    try:
        client.upload_file(local_path, R2_BUCKET, object_key)
        return True
    except Exception:
        return False


def _r2_delete_object(object_key):
    client = _get_r2_client()
    if client is None:
        return False
    try:
        client.delete_object(Bucket=R2_BUCKET, Key=object_key)
        return True
    except Exception:
        return False


def _r2_document_object_key(stored_name):
    safe_name = str(stored_name).strip().lstrip('/')
    return f"{R2_DOCUMENTS_PREFIX}/{safe_name}"


def _r2_restore_documents_from_index():
    if not _r2_is_configured():
        return
    if not _r2_download_object_to_path(R2_ATHLETE_DOCS_INDEX_OBJECT_KEY, ATHLETE_DOCS_INDEX):
        return

    try:
        with open(ATHLETE_DOCS_INDEX, 'r', encoding='utf-8') as f:
            index_payload = json.load(f)
    except Exception:
        return

    if not isinstance(index_payload, dict):
        return

    for entry in index_payload.values():
        if not isinstance(entry, Mapping):
            continue
        stored_name = str(entry.get('stored_name', '')).strip()
        if not stored_name:
            continue
        local_pdf_path = os.path.join(ATHLETE_DOCS_FOLDER, stored_name)
        if os.path.exists(local_pdf_path):
            continue
        _r2_download_object_to_path(_r2_document_object_key(stored_name), local_pdf_path)


def _r2_backfill_local_documents_to_r2():
    if not _r2_is_configured() or not os.path.exists(ATHLETE_DOCS_INDEX):
        return

    try:
        with open(ATHLETE_DOCS_INDEX, 'r', encoding='utf-8') as f:
            index_payload = json.load(f)
    except Exception:
        return

    if not isinstance(index_payload, dict):
        return

    for entry in index_payload.values():
        if not isinstance(entry, Mapping):
            continue
        stored_name = str(entry.get('stored_name', '')).strip()
        if not stored_name:
            continue
        local_pdf_path = os.path.join(ATHLETE_DOCS_FOLDER, stored_name)
        if os.path.exists(local_pdf_path):
            _r2_upload_path(_r2_document_object_key(stored_name), local_pdf_path)

    _r2_upload_path(R2_ATHLETE_DOCS_INDEX_OBJECT_KEY, ATHLETE_DOCS_INDEX)


def _bootstrap_from_r2():
    """Synchronise les fichiers persistants depuis R2 au démarrage (si configuré)."""
    if not _r2_is_configured():
        return
    # Toujours tenter une synchro au démarrage pour refléter les dernières données partagées.
    _r2_download_object_to_path(R2_ACTIVITIES_OBJECT_KEY, file_path)
    _r2_download_object_to_path(R2_CREDENTIALS_OBJECT_KEY, CREDENTIALS_CSV)
    _r2_restore_documents_from_index()
    _r2_backfill_local_documents_to_r2()


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


# Normalise un identifiant athlète pour un appariement tolérant.
def normalize_athlete_identifier(value):
    if pd.isna(value):
        return ''
    raw = str(value).strip().lower()
    if not raw:
        return ''

    # Supprimer les accents pour aligner "Prénom" et "Prenom".
    raw = unicodedata.normalize('NFKD', raw)
    raw = ''.join(ch for ch in raw if not unicodedata.combining(ch))

    # Uniformiser la ponctuation et conserver seulement alphanumérique + espaces.
    raw = raw.replace(',', ' ')
    raw = re.sub(r'[^a-z0-9 ]+', ' ', raw)
    tokens = [token for token in raw.split() if token]
    if not tokens:
        return ''

    # Tri des tokens pour reconnaître "Nom, Prénom" et "Prénom Nom" comme équivalents.
    return ' '.join(sorted(tokens))


# Trouve le meilleur identifiant athlète à partir d'un nom, avec tolérance aux petites variantes.
def find_best_athlete_id_by_name(raw_name, candidate_ids):
    target_norm = normalize_athlete_identifier(raw_name)
    if not target_norm or not candidate_ids:
        return None

    exact_matches = [
        candidate
        for candidate in candidate_ids
        if normalize_athlete_identifier(candidate) == target_norm
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    target_tokens = set(target_norm.split())
    scored_matches = []
    for candidate in candidate_ids:
        candidate_norm = normalize_athlete_identifier(candidate)
        if not candidate_norm:
            continue
        candidate_tokens = set(candidate_norm.split())
        if target_tokens and not (target_tokens & candidate_tokens):
            continue

        similarity = SequenceMatcher(None, target_norm, candidate_norm).ratio()
        token_overlap = len(target_tokens & candidate_tokens) / max(len(target_tokens), 1)
        score = similarity + (0.15 * token_overlap)
        scored_matches.append((score, similarity, candidate))

    if not scored_matches:
        return None

    scored_matches.sort(key=lambda item: item[0], reverse=True)
    best_score, best_similarity, best_candidate = scored_matches[0]
    second_score = scored_matches[1][0] if len(scored_matches) > 1 else 0.0

    # Seuils prudents pour éviter de lier au mauvais athlète.
    if best_similarity < 0.84:
        return None
    if (best_score - second_score) < 0.05:
        return None
    return best_candidate


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
    wellness_cols = [
        c for c in df.columns
        if any(k in str(c).strip().lower() for k in ['sommeil', 'sleep', 'dormi', 'fatigue'])
    ]
    keep_cols = keep_cols + wellness_cols
    # Dédupliquer la liste des colonnes à conserver (en gardant le premier ordre d'apparition).
    keep_cols = list(dict.fromkeys(keep_cols))
    df = df[[c for c in keep_cols if c in df.columns]]
    # Sécurité: si des doublons de noms subsistent, garder la première occurrence.
    df = df.loc[:, ~df.columns.duplicated()]

    return df


# Formate une date au format lisible en français.
def format_date_fr(value):
    dt = pd.to_datetime(value)
    return f"{dt.day:02d} {FRENCH_MONTHS[dt.month]} {dt.year}"


# Convertit une réponse sommeil en heures approximatives.
def parse_sleep_hours(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip().lower()
    if not s:
        return np.nan

    mapping = {
        'moins de 5': 4.5,
        'entre 5h et 6h': 5.5,
        'entre 6h et 7h': 6.5,
        'entre 7h et 8h': 7.5,
        'entre 8h et 9h': 8.5,
        'entre 9h et 10h': 9.5,
        'plus de 10': 10.5,
    }
    for key, hours in mapping.items():
        if key in s:
            return hours

    # Fallback: extraire 1 ou 2 nombres et prendre leur moyenne.
    nums = re.findall(r'\d+(?:[\.,]\d+)?', s)
    if len(nums) >= 2:
        a = float(nums[0].replace(',', '.'))
        b = float(nums[1].replace(',', '.'))
        return (a + b) / 2.0
    if len(nums) == 1:
        return float(nums[0].replace(',', '.'))
    return np.nan


# Convertit une réponse fatigue en score ordinal (1=faible fatigue, 3=fatigue élevée).
def parse_fatigue_score(value):
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip().lower()
    if not s:
        return np.nan

    if 'repos' in s or 'prête' in s or 'prete' in s:
        return 1.0
    if 'peu fatigu' in s or 'un peu' in s:
        return 2.0
    if 'plus fatigu' in s:
        return 3.0
    return np.nan


# Charge le fichier de comptes (CSV prioritaire, XLSX en fallback).
def _github_credentials_api_url():
    """Retourne l'URL de l'API GitHub pour le fichier users.csv, ou None si non configuré."""
    token = _secret('GITHUB_TOKEN', '')
    repo  = _secret('GITHUB_REPO', 'AP0811/Dashboard.Hq1')
    path  = _secret('GITHUB_CREDENTIALS_PATH', 'private_data/credentials/users.csv')
    if not token or not repo:
        return None, None, None
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'Dashboard-Hq1',
    }
    return url, headers, path


def _fetch_credentials_from_github():
    """Télécharge users.csv depuis GitHub et le cache localement. Retourne un DataFrame ou None."""
    import urllib.request as _ur
    url, headers, _ = _github_credentials_api_url()
    if url is None:
        return None
    try:
        req = _ur.Request(url, headers=headers)
        with _ur.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        csv_bytes = base64.b64decode(data['content'])
        import io
        df = pd.read_csv(io.StringIO(csv_bytes.decode('utf-8')))
        # Cache local pour la session en cours
        os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)
        with open(CREDENTIALS_CSV, 'wb') as f:
            f.write(csv_bytes)
        return df
    except Exception:
        return None


def _push_credentials_to_github(csv_content: str) -> bool:
    """Pousse le fichier users.csv vers GitHub pour persistance entre redémarrages."""
    import urllib.request as _ur
    url, headers, _ = _github_credentials_api_url()
    if url is None:
        return False
    # Récupérer le SHA actuel (requis pour le PUT)
    sha = ''
    try:
        req = _ur.Request(url, headers=headers)
        with _ur.urlopen(req, timeout=10) as resp:
            sha = json.loads(resp.read()).get('sha', '')
    except Exception:
        pass
    content_b64 = base64.b64encode(csv_content.encode('utf-8')).decode('utf-8')
    body = {'message': 'Update credentials [skip ci]', 'content': content_b64}
    if sha:
        body['sha'] = sha
    put_headers = {**headers, 'Content-Type': 'application/json'}
    put_req = _ur.Request(url, data=json.dumps(body).encode('utf-8'), method='PUT', headers=put_headers)
    try:
        with _ur.urlopen(put_req, timeout=15) as resp:
            return resp.status in (200, 201)
    except Exception:
        return False


def _file_signature(path):
    """Retourne une signature stable d'un fichier pour invalider le cache quand il change."""
    try:
        stat = os.stat(path)
        return True, stat.st_mtime_ns, stat.st_size
    except OSError:
        return False, 0, 0


@st.cache_data(show_spinner=False)
def _read_dataframe_cached(path, signature):
    """Lit un CSV/XLSX avec cache Streamlit indexé par signature de fichier."""
    file_exists, _, _ = signature
    if not file_exists:
        return pd.DataFrame()
    if str(path).lower().endswith('.xlsx'):
        return pd.read_excel(path)
    return pd.read_csv(path)


def read_main_data_df():
    """Charge le fichier principal de données avec cache et fallback R2."""
    if not os.path.exists(file_path):
        _r2_download_object_to_path(R2_ACTIVITIES_OBJECT_KEY, file_path)
    if not os.path.exists(file_path):
        return pd.DataFrame()

    signature = _file_signature(file_path)
    df = _read_dataframe_cached(file_path, signature)
    return df.copy()


def read_credentials_df():
    if os.path.exists(CREDENTIALS_CSV):
        signature = _file_signature(CREDENTIALS_CSV)
        return _read_dataframe_cached(CREDENTIALS_CSV, signature).copy()
    if os.path.exists(CREDENTIALS_XLSX):
        try:
            signature = _file_signature(CREDENTIALS_XLSX)
            return _read_dataframe_cached(CREDENTIALS_XLSX, signature).copy()
        except PermissionError:
            st.warning('Le fichier des identifiants est ouvert dans une autre application. Ferme-le pour charger les comptes.')
            return pd.DataFrame()
    # Fichier absent — restaurer depuis R2
    if _r2_download_object_to_path(R2_CREDENTIALS_OBJECT_KEY, CREDENTIALS_CSV):
        try:
            signature = _file_signature(CREDENTIALS_CSV)
            return _read_dataframe_cached(CREDENTIALS_CSV, signature).copy()
        except Exception:
            pass
    # Fichier absent (ex. reboot Streamlit Cloud) — restaurer depuis GitHub
    df = _fetch_credentials_from_github()
    if df is not None:
        return df
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
            username = str(row[email_col]).strip().lower()
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


_bootstrap_from_r2()
users = load_user_credentials()


# Écrit les comptes utilisateurs dans le fichier CSV sécurisé (écriture atomique + sauvegarde GitHub).
def write_credentials_df(df):
    os.makedirs(CREDENTIALS_FOLDER, exist_ok=True)
    tmp_path = CREDENTIALS_CSV + '.tmp'
    try:
        df.to_csv(tmp_path, index=False)
        os.replace(tmp_path, CREDENTIALS_CSV)
    except PermissionError:
        return False
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        return False
    # Pousser vers R2 pour survivre aux redémarrages
    _r2_upload_path(R2_CREDENTIALS_OBJECT_KEY, CREDENTIALS_CSV)
    # Pousser vers GitHub pour survivre aux reboots (silencieux si non configuré)
    _push_credentials_to_github(df.to_csv(index=False))
    _read_dataframe_cached.clear()
    return True


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
        _r2_upload_path(R2_ACTIVITIES_OBJECT_KEY, file_path)
        _read_dataframe_cached.clear()
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


# Retourne une version sûre d'un texte pour un nom de fichier.
def sanitize_filename_component(value):
    normalized = normalize_athlete_identifier(value)
    if not normalized:
        return 'athlete'
    safe = re.sub(r'[^a-z0-9]+', '_', normalized).strip('_')
    return safe or 'athlete'


# Lit l'index JSON des documents PDF par athlète.
def read_athlete_documents_index():
    if not os.path.exists(ATHLETE_DOCS_INDEX) and _r2_is_configured():
        _r2_download_object_to_path(R2_ATHLETE_DOCS_INDEX_OBJECT_KEY, ATHLETE_DOCS_INDEX)

    if not os.path.exists(ATHLETE_DOCS_INDEX):
        return {}
    try:
        with open(ATHLETE_DOCS_INDEX, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if isinstance(payload, dict):
            return payload
    except Exception:
        return {}
    return {}


# Sauvegarde l'index JSON des documents PDF par athlète de manière atomique.
def write_athlete_documents_index(index_payload):
    os.makedirs(ATHLETE_DOCS_FOLDER, exist_ok=True)
    tmp_path = ATHLETE_DOCS_INDEX + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(index_payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, ATHLETE_DOCS_INDEX)
        return True
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        return False


# Enregistre/remplace le PDF associé à un athlète.
def save_athlete_pdf_document(athlete_id, uploaded_pdf):
    athlete_id = str(athlete_id).strip()
    if not athlete_id:
        return False, 'missing_athlete', None
    if uploaded_pdf is None:
        return False, 'missing_file', None

    ext = os.path.splitext(uploaded_pdf.name or '')[1].lower()
    if ext != '.pdf':
        ext = '.pdf'

    os.makedirs(ATHLETE_DOCS_FOLDER, exist_ok=True)
    index_payload = read_athlete_documents_index()

    safe_id = sanitize_filename_component(athlete_id)
    timestamp = int(time.time())
    stored_name = f"{safe_id}_{timestamp}{ext}"
    stored_path = os.path.join(ATHLETE_DOCS_FOLDER, stored_name)

    file_bytes = uploaded_pdf.getbuffer()
    with open(stored_path, 'wb') as f:
        f.write(file_bytes)

    if _r2_is_configured() and not _r2_upload_path(_r2_document_object_key(stored_name), stored_path):
        try:
            os.remove(stored_path)
        except OSError:
            pass
        return False, 'r2_upload_pdf_failed', None

    old_entry = index_payload.get(athlete_id, {})
    old_stored_name = str(old_entry.get('stored_name', '')).strip()

    index_payload[athlete_id] = {
        'original_name': uploaded_pdf.name,
        'stored_name': stored_name,
        'uploaded_at': pd.Timestamp.now().isoformat(),
    }

    if not write_athlete_documents_index(index_payload):
        try:
            os.remove(stored_path)
        except OSError:
            pass
        return False, 'write_index_failed', None

    if _r2_is_configured() and not _r2_upload_path(R2_ATHLETE_DOCS_INDEX_OBJECT_KEY, ATHLETE_DOCS_INDEX):
        # Revenir à l'index précédent localement pour éviter un état divergent non signalé.
        if old_entry:
            index_payload[athlete_id] = old_entry
        else:
            index_payload.pop(athlete_id, None)
        write_athlete_documents_index(index_payload)
        try:
            os.remove(stored_path)
        except OSError:
            pass
        return False, 'r2_upload_index_failed', None

    if old_stored_name and old_stored_name != stored_name:
        old_path = os.path.join(ATHLETE_DOCS_FOLDER, old_stored_name)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass
        if _r2_is_configured():
            _r2_delete_object(_r2_document_object_key(old_stored_name))

    return True, None, index_payload[athlete_id]


# Supprime le PDF associé à un athlète (fichier local, index, et objet R2 si configuré).
def delete_athlete_pdf_document(athlete_id):
    athlete_id = str(athlete_id).strip()
    if not athlete_id:
        return False, 'missing_athlete'

    index_payload = read_athlete_documents_index()
    if not index_payload:
        return False, 'not_found'

    target_key = None
    entry = index_payload.get(athlete_id)
    if entry is not None:
        target_key = athlete_id
    else:
        requested_norm = normalize_athlete_identifier(athlete_id)
        for indexed_id, indexed_entry in index_payload.items():
            if normalize_athlete_identifier(indexed_id) == requested_norm:
                target_key = indexed_id
                entry = indexed_entry
                break

    if target_key is None or not isinstance(entry, Mapping):
        return False, 'not_found'

    stored_name = str(entry.get('stored_name', '')).strip()
    removed_entry = index_payload.pop(target_key, None)
    if removed_entry is None:
        return False, 'not_found'

    if not write_athlete_documents_index(index_payload):
        return False, 'write_index_failed'

    if _r2_is_configured() and not _r2_upload_path(R2_ATHLETE_DOCS_INDEX_OBJECT_KEY, ATHLETE_DOCS_INDEX):
        # Rollback local pour garder la cohérence si la sync index échoue.
        index_payload[target_key] = entry
        write_athlete_documents_index(index_payload)
        return False, 'r2_upload_index_failed'

    if stored_name:
        local_pdf_path = os.path.join(ATHLETE_DOCS_FOLDER, stored_name)
        if os.path.exists(local_pdf_path):
            try:
                os.remove(local_pdf_path)
            except OSError:
                pass
        if _r2_is_configured():
            _r2_delete_object(_r2_document_object_key(stored_name))

    return True, None


# Trouve le PDF d'un athlète (correspondance exacte puis normalisée).
def get_athlete_pdf_document(athlete_id):
    athlete_id = str(athlete_id).strip()
    if not athlete_id:
        return None

    index_payload = read_athlete_documents_index()
    entry = index_payload.get(athlete_id)

    if entry is None:
        requested_norm = normalize_athlete_identifier(athlete_id)
        for indexed_id, indexed_entry in index_payload.items():
            if normalize_athlete_identifier(indexed_id) == requested_norm:
                entry = indexed_entry
                athlete_id = indexed_id
                break

    if not entry:
        return None

    stored_name = str(entry.get('stored_name', '')).strip()
    if not stored_name:
        return None

    file_path = os.path.join(ATHLETE_DOCS_FOLDER, stored_name)
    if not os.path.exists(file_path) and _r2_is_configured():
        _r2_download_object_to_path(_r2_document_object_key(stored_name), file_path)
    if not os.path.exists(file_path):
        return None

    original_name = str(entry.get('original_name', stored_name)).strip() or stored_name
    return {
        'athlete_id': athlete_id,
        'file_path': file_path,
        'stored_name': stored_name,
        'original_name': original_name,
        'uploaded_at': entry.get('uploaded_at'),
    }


# Retourne la liste des PDFs disponibles pour l'admin.
def list_athlete_pdf_documents():
    index_payload = read_athlete_documents_index()
    rows = []
    for athlete_id in sorted(index_payload.keys(), key=str.lower):
        document = get_athlete_pdf_document(athlete_id)
        if document is None:
            continue
        rows.append({
            'Athlète': athlete_id,
            'Fichier': document['original_name'],
            'Téléversé le': document.get('uploaded_at', ''),
        })
    return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def render_pdf_preview_pages(pdf_bytes, max_pages=10, zoom=1.25):
    """Rend les premières pages d'un PDF en PNG pour un aperçu compatible tous navigateurs."""
    if fitz is None:
        return [], 0

    pages = []
    total_pages = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as pdf_doc:
        total_pages = pdf_doc.page_count
        render_count = min(total_pages, max_pages)
        matrix = fitz.Matrix(zoom, zoom)

        for page_index in range(render_count):
            page = pdf_doc.load_page(page_index)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            pages.append(pixmap.tobytes("png"))

    return pages, total_pages


# Affiche la section de consultation PDF pour un athlète.
def render_athlete_pdf_section(athlete_id, title, widget_key_prefix):
    st.subheader(title)
    document = get_athlete_pdf_document(athlete_id)
    if document is None:
        st.info("Aucun document PDF n'est encore associé à cet athlète.")
        return

    try:
        with open(document['file_path'], 'rb') as f:
            pdf_bytes = f.read()
    except Exception as exc:
        st.error(f"Impossible de lire le document PDF: {exc}")
        return

    uploaded_at = document.get('uploaded_at')
    uploaded_label = ''
    if uploaded_at:
        try:
            uploaded_label = pd.to_datetime(uploaded_at).strftime('%Y-%m-%d %H:%M')
        except Exception:
            uploaded_label = str(uploaded_at)

    st.write(f"Document: **{document['original_name']}**")
    if uploaded_label:
        st.caption(f"Téléversé le {uploaded_label}")

    st.download_button(
        "Télécharger le PDF",
        data=pdf_bytes,
        file_name=document['original_name'],
        mime='application/pdf',
        key=f"{widget_key_prefix}_download_pdf",
    )

    with st.expander("Aperçu PDF", expanded=True):
        try:
            preview_pages, total_pages = render_pdf_preview_pages(pdf_bytes, max_pages=10, zoom=1.2)
            if not preview_pages:
                if fitz is None:
                    st.info("Aperçu indisponible: PyMuPDF n'est pas installé. Utilisez le bouton de téléchargement.")
                else:
                    st.info("Aperçu indisponible pour ce fichier. Utilisez le bouton de téléchargement.")
                return

            for idx, image_bytes in enumerate(preview_pages, start=1):
                st.image(image_bytes, caption=f"Page {idx}", width='stretch')

            if total_pages > len(preview_pages):
                st.caption(f"Aperçu limité aux {len(preview_pages)} premières pages sur {total_pages}.")
        except Exception as exc:
            st.info("Aperçu indisponible pour ce fichier. Utilisez le bouton de téléchargement.")
            st.caption(f"Détail technique: {exc}")


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
    email = str(email).strip().lower()
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


# Retourne les identifiants athlètes présents dans le fichier de données principal.
def get_data_athlete_ids():
    df = read_main_data_df()
    if df.empty:
        return []

    athlete_col = find_column(df.columns, ['Id', 'athlete_id', 'utilisateur', 'Utilisateur'])
    if athlete_col is None:
        return []

    athlete_ids = (
        df[athlete_col]
        .dropna()
        .astype(str)
        .str.strip()
    )
    athlete_ids = [value for value in athlete_ids.tolist() if value and value.lower() != 'nan']
    return sorted(set(athlete_ids), key=str.lower)


# Tente de corriger automatiquement un identifiant athlète mal associé au compte.
def resolve_account_athlete_id(username, user_info, persist=True):
    current_id = str(user_info.get('id', '')).strip()
    athlete_name = str(user_info.get('name', '')).strip()
    username_norm = normalize_athlete_identifier(username)
    name_norm = normalize_athlete_identifier(athlete_name)

    data_ids = get_data_athlete_ids()
    if not data_ids:
        return current_id, False

    # Conserver l'identifiant actuel s'il existe déjà dans les données.
    current_norm = normalize_athlete_identifier(current_id)
    if current_norm and any(normalize_athlete_identifier(candidate) == current_norm for candidate in data_ids):
        return current_id, False

    username_matches = [
        candidate for candidate in data_ids
        if username_norm and normalize_athlete_identifier(candidate) == username_norm
    ]
    name_matches = [
        candidate for candidate in data_ids
        if name_norm and normalize_athlete_identifier(candidate) == name_norm
    ]

    selected = None
    if len(username_matches) == 1:
        selected = username_matches[0]
    elif len(name_matches) == 1:
        selected = name_matches[0]

    if not selected:
        selected = find_best_athlete_id_by_name(athlete_name, data_ids)

    if not selected:
        return current_id, False

    users['usernames'][username]['id'] = selected
    if persist:
        save_user_credentials(users)
    return selected, True


# Corrige en lot les comptes athlètes déjà existants pour éviter les doublons (courriel vs nom réel).
def reconcile_all_athlete_account_ids():
    updated_count = 0
    for username, info in users.get('usernames', {}).items():
        role = str(info.get('role', '')).strip().lower()
        if role != 'athlete':
            continue
        _, was_relinked = resolve_account_athlete_id(username, info, persist=False)
        if was_relinked:
            updated_count += 1

    if updated_count > 0:
        save_user_credentials(users)
    return updated_count


reconcile_all_athlete_account_ids()


# Applique un mapping athlete_id basé sur le nom pour les lignes éditées en admin.
def apply_admin_name_based_mapping(df_users):
    if df_users is None or df_users.empty:
        return df_users, 0

    df_mapped = df_users.copy()
    email_col = find_column(df_mapped.columns, ['email', 'courriel', 'adresse courriel', 'Id'])
    role_col = find_column(df_mapped.columns, ['role', 'rôle'])
    name_col = find_column(df_mapped.columns, ['name', 'nom'])
    athlete_id_col = find_column(df_mapped.columns, ['athlete_id', 'id', 'utilisateur'])

    if role_col is None or name_col is None or athlete_id_col is None:
        return df_mapped, 0

    if email_col and email_col in df_mapped.columns:
        df_mapped[email_col] = df_mapped[email_col].astype(str).str.strip().str.lower()

    data_ids = get_data_athlete_ids()
    if not data_ids:
        return df_mapped, 0

    mapped_count = 0
    data_ids_norm = {normalize_athlete_identifier(candidate) for candidate in data_ids}

    for idx, row in df_mapped.iterrows():
        role_value = str(row.get(role_col, '')).strip().lower()
        if role_value != 'athlete':
            continue

        current_name = str(row.get(name_col, '')).strip()
        current_id = str(row.get(athlete_id_col, '')).strip()

        # Priorité: si le nom correspond de façon fiable à un ID des données, utiliser ce format canonique.
        matched_id_by_name = find_best_athlete_id_by_name(current_name, data_ids)
        if matched_id_by_name and matched_id_by_name != current_id:
            df_mapped.at[idx, athlete_id_col] = matched_id_by_name
            mapped_count += 1
            continue

        # Remapper quand l'id est vide, ressemble à un courriel, ou n'existe pas dans les IDs des données.
        current_norm = normalize_athlete_identifier(current_id)
        needs_mapping = (
            not current_id
            or '@' in current_id
            or current_norm not in data_ids_norm
        )
        if not needs_mapping:
            continue

        matched_id = find_best_athlete_id_by_name(current_name, data_ids)
        if matched_id and matched_id != current_id:
            df_mapped.at[idx, athlete_id_col] = matched_id
            mapped_count += 1

    return df_mapped, mapped_count


with st.sidebar.expander('Créer un compte'):
    with st.form('register_form', clear_on_submit=True):
        existing_athlete_ids = get_data_athlete_ids()
        new_email = st.text_input('Adresse courriel')
        new_name = st.text_input('Nom complet')
        new_password = st.text_input('Mot de passe', type='password')
        selected_athlete_id = st.selectbox(
            "Associer à l'identifiant athlète existant",
            options=[''] + existing_athlete_ids,
            format_func=lambda value: 'Sélectionner...' if value == '' else value
        )
        manual_athlete_id = st.text_input("Identifiant athlète (si absent de la liste)")
        if st.form_submit_button('Créer un compte'):
            if not new_email or not new_password:
                st.error('Adresse courriel et mot de passe sont requis.')
            else:
                resolved_athlete_id = str(selected_athlete_id).strip() if selected_athlete_id else ''
                if not resolved_athlete_id:
                    resolved_athlete_id = str(manual_athlete_id).strip()

                if not resolved_athlete_id and new_name and existing_athlete_ids:
                    resolved_athlete_id = find_best_athlete_id_by_name(new_name, existing_athlete_ids) or ''

                if not resolved_athlete_id and existing_athlete_ids:
                    st.error("Sélectionne ton identifiant athlète existant (ou saisis-le) pour éviter la création d'un nouveau profil.")
                else:
                    if not resolved_athlete_id:
                        resolved_athlete_id = str(new_email).strip().lower()
                        st.info("Aucun identifiant athlète existant détecté: le courriel sera utilisé comme identifiant.")

                    created, msg = append_user_to_file(
                        new_email,
                        new_name or new_email,
                        new_password,
                        'athlete',
                        resolved_athlete_id
                    )
                    if created:
                        st.success(f"Compte créé et associé à l'identifiant: {resolved_athlete_id}. Recharge la page pour te connecter.")
                        st.rerun()
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
    df = read_main_data_df()
    if df.empty:
        st.error("Fichier de données non trouvé.")
        return pd.DataFrame()

    athlete_id = str(athlete_id).strip()
    athlete_id_norm = normalize_athlete_identifier(athlete_id)
    if 'Id' in df.columns:
        df['Id'] = df['Id'].astype(str).str.strip()
        exact_mask = df['Id'] == athlete_id
        if exact_mask.any():
            df = df[exact_mask].copy()
        else:
            df_norm = df['Id'].apply(normalize_athlete_identifier)
            df = df[df_norm == athlete_id_norm].copy()
    elif 'athlete_id' in df.columns:
        df['athlete_id'] = df['athlete_id'].astype(str).str.strip()
        exact_mask = df['athlete_id'] == athlete_id
        if exact_mask.any():
            df = df[exact_mask].copy()
        else:
            df_norm = df['athlete_id'].apply(normalize_athlete_identifier)
            df = df[df_norm == athlete_id_norm].copy()
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


# Prépare une table de progression exploitable par les coachs.
def build_coach_progression_frame(df_all):
    athlete_column = find_column(df_all.columns, ['Id', 'athlete_id', 'utilisateur', 'Utilisateur'])
    if athlete_column is None or 'Date' not in df_all.columns:
        return pd.DataFrame(), athlete_column, {'sleep_column': None, 'fatigue_column': None, 'injury_column': None, 'load_columns': []}

    sleep_column = find_column(df_all.columns, [
        'Sommeil', 'sleep', 'sommeil', 'hours slept', 'sleep hours',
        'combien d’heures as-tu dormi', 'combien d\'heures as-tu dormi', 'dormi lors de la nuit passée',
    ])
    fatigue_column = find_column(df_all.columns, [
        'Fatigue', 'fatigue', 'niveau de fatigue',
        'aujourd\'hui, à quel niveau estimes-tu ton niveau de fatigue',
        'aujourd\'hui, a quel niveau estimes-tu ton niveau de fatigue',
    ])
    injury_column = find_column(df_all.columns, ['Blessure', 'injury', 'injur', 'is injured', 'hurt'])

    all_load_columns = [
        col for col in df_all.columns
        if str(col).strip().lower().endswith('load')
        and str(col).strip().lower() not in {'total load', 'charge_totale'}
    ]

    hockey_parts = [c for c in ['Pratique load', 'Match load', 'Skills load'] if c in df_all.columns]
    if hockey_parts:
        # Si les sous-activités hockey existent, on exclut Hockey load pour éviter le double comptage.
        load_columns = [col for col in all_load_columns if str(col).strip().lower() != 'hockey load']
    else:
        load_columns = all_load_columns

    if not load_columns:
        total_load_col = find_column(df_all.columns, ['Total load', 'charge_totale'])
        if total_load_col:
            load_columns = [total_load_col]

    if not load_columns:
        return pd.DataFrame(), athlete_column, {
            'sleep_column': sleep_column,
            'fatigue_column': fatigue_column,
            'injury_column': injury_column,
            'load_columns': load_columns,
        }

    activity_share_map = {
        'Muscu load': 'Muscu %',
        'Cardio load': 'Cardio %',
        'Sport load': 'Autres sports %',
    }

    df = df_all.copy()
    df[athlete_column] = df[athlete_column].astype(str).str.strip()
    df['Date'] = pd.to_datetime(df['Date'], format='mixed', errors='coerce')
    df = df.dropna(subset=['Date'])
    df = df[df[athlete_column].astype(str).str.strip() != '']

    frames = []
    for athlete_id, athlete_df in df.groupby(athlete_column, sort=False):
        working = athlete_df.copy()
        working['_day'] = working['Date'].dt.normalize()

        agg_map = {col: 'sum' for col in load_columns if col in working.columns}
        if sleep_column and sleep_column in working.columns:
            working['_sleep_hours'] = working[sleep_column].apply(parse_sleep_hours)
            agg_map['_sleep_hours'] = 'mean'
        if fatigue_column and fatigue_column in working.columns:
            working['_fatigue_score'] = working[fatigue_column].apply(parse_fatigue_score)
            agg_map['_fatigue_score'] = 'mean'
        if injury_column and injury_column in working.columns:
            agg_map[injury_column] = 'max'

        if not agg_map:
            continue

        daily = working.groupby('_day', as_index=True).agg(agg_map).sort_index()
        if daily.empty:
            continue

        full_index = pd.date_range(daily.index.min(), daily.index.max(), freq='D')
        daily = daily.reindex(full_index)
        daily.index.name = 'Date'

        for col in load_columns:
            if col in daily.columns:
                daily[col] = pd.to_numeric(daily[col], errors='coerce').fillna(0)

        if load_columns:
            daily['charge_totale'] = daily[load_columns].fillna(0).sum(axis=1)
        else:
            daily['charge_totale'] = 0.0

        if '_sleep_hours' in daily.columns:
            daily = daily.rename(columns={'_sleep_hours': 'Sommeil (h)'})
            daily['Sommeil (h)'] = pd.to_numeric(daily['Sommeil (h)'], errors='coerce')

        if '_fatigue_score' in daily.columns:
            daily = daily.rename(columns={'_fatigue_score': 'Fatigue score'})
            daily['Fatigue score'] = pd.to_numeric(daily['Fatigue score'], errors='coerce')

        if injury_column and injury_column in daily.columns:
            daily = daily.rename(columns={injury_column: 'Blessure'})
            daily['Blessure'] = pd.to_numeric(daily['Blessure'], errors='coerce').fillna(0)

        if {'Pratique load', 'Match load', 'Skills load'} & set(daily.columns):
            parts = [c for c in ['Pratique load', 'Match load', 'Skills load'] if c in daily.columns]
            daily['Hockey load'] = daily[parts].fillna(0).sum(axis=1)
        elif 'Hockey load' in daily.columns:
            daily['Hockey load'] = pd.to_numeric(daily['Hockey load'], errors='coerce').fillna(0)
        else:
            daily['Hockey load'] = 0.0

        for source_col, target_col in activity_share_map.items():
            if source_col in daily.columns:
                daily[target_col] = np.where(
                    daily['charge_totale'] > 0,
                    (pd.to_numeric(daily[source_col], errors='coerce').fillna(0) / daily['charge_totale']) * 100.0,
                    0.0,
                )
            else:
                daily[target_col] = 0.0

        daily['Hockey %'] = np.where(
            daily['charge_totale'] > 0,
            (pd.to_numeric(daily['Hockey load'], errors='coerce').fillna(0) / daily['charge_totale']) * 100.0,
            0.0,
        )

        daily['Athlète'] = athlete_id
        daily['charge_7j'] = daily['charge_totale'].rolling(window=7, min_periods=7).sum()
        daily['charge_28j'] = daily['charge_totale'].rolling(window=28, min_periods=28).sum()
        daily['charge_42j'] = daily['charge_totale'].rolling(window=42, min_periods=42).sum()
        daily['acwr_7_28'] = daily['charge_7j'] / (daily['charge_28j'] / 4.0)
        daily['acwr_7_42'] = daily['charge_7j'] / (daily['charge_42j'] / 6.0)
        daily['variation_7j'] = daily['charge_7j'] - daily['charge_7j'].shift(7)
        daily = daily.reset_index()

        frames.append(daily)

    if not frames:
        return pd.DataFrame(), athlete_column, {
            'sleep_column': sleep_column,
            'fatigue_column': fatigue_column,
            'injury_column': injury_column,
            'load_columns': load_columns,
        }

    result = pd.concat(frames, ignore_index=True)
    result = result.sort_values(['Athlète', 'Date']).reset_index(drop=True)
    return result, athlete_column, {
        'sleep_column': sleep_column,
        'fatigue_column': fatigue_column,
        'injury_column': injury_column,
        'load_columns': load_columns,
    }

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
def show_athlete_dashboard(athlete_id, show_pdf_section=True):
    st.title("Préparation estivales Maitres chez nous")
    st.subheader(f"Tableau de bord - {name}")

    if show_pdf_section:
        render_athlete_pdf_section(
            athlete_id,
            "Document PDF personnel",
            f"athlete_{sanitize_filename_component(athlete_id)}",
        )
        st.divider()

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
    df_all = read_main_data_df()
    if df_all.empty:
        st.error("Fichier de données non trouvé.")
        return

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

    st.subheader("Analyse simple et export")
    progression_df, progression_athlete_column, progression_meta = build_coach_progression_frame(df_all)
    if progression_df.empty:
        st.info("Pas assez de données pour calculer une table de progression. Le suivi détaillé reste disponible dans le dashboard athlète.")
    else:
        if not pd.isna(progression_df['Date']).all():
            latest_progress_date = progression_df['Date'].max().date()
        else:
            latest_progress_date = pd.Timestamp.now().date()

        default_anchor = pd.Timestamp('2026-07-06').date()
        if default_anchor > latest_progress_date:
            default_anchor = latest_progress_date

        default_end = min(default_anchor + pd.Timedelta(days=6), pd.Timestamp(latest_progress_date).to_pydatetime().date())
        window_start = st.date_input("Date pivot des tests", value=default_anchor)
        window_end = st.date_input("Fin de fenêtre d'analyse", value=default_end)

        analysis_options = ['Tous les athlètes'] + athletes
        analysis_choice = st.selectbox("Vue d'analyse", analysis_options, key="coach_analysis_scope")
        if analysis_choice == 'Tous les athlètes':
            analysis_df = progression_df.copy()
        else:
            analysis_df = progression_df[progression_df['Athlète'] == analysis_choice].copy()

        analysis_df = analysis_df[
            (analysis_df['Date'].dt.date >= window_start) &
            (analysis_df['Date'].dt.date <= window_end)
        ].copy()

        analysis_df = analysis_df.sort_values(['Athlète', 'Date']).reset_index(drop=True)

        # Pour les métriques 7j/28j/42j/ACWR: prendre la dernière date saisie par athlète
        # (jusqu'à la fin de fenêtre), même s'il n'y a rien le jour pivot.
        metrics_source_df = progression_df[
            progression_df['Date'].dt.date <= window_end
        ].copy()
        metrics_source_df = metrics_source_df.sort_values(['Athlète', 'Date']).reset_index(drop=True)

        latest_rows = pd.DataFrame()
        if not metrics_source_df.empty:
            selected_rows = []
            for athlete_id, athlete_df in metrics_source_df.groupby('Athlète', sort=False):
                athlete_df = athlete_df.sort_values('Date')
                last_date = athlete_df['Date'].max().date()

                if last_date > window_start:
                    # Règle demandée: si dernière date après le 6 juillet, utiliser le 6 juillet
                    # (ou la plus proche date antérieure si aucune saisie ce jour-là).
                    eligible = athlete_df[athlete_df['Date'].dt.date <= window_start]
                    chosen = eligible.tail(1) if not eligible.empty else athlete_df.tail(1)
                else:
                    chosen = athlete_df.tail(1)

                selected_rows.append(chosen)

            if selected_rows:
                latest_rows = pd.concat(selected_rows, ignore_index=True)

        # Fallback: si un athlète n'a aucune saisie avant la fin de fenêtre,
        # utiliser sa dernière saisie connue pour éviter les None inutiles.
        fallback_latest = progression_df.sort_values(['Athlète', 'Date']).groupby('Athlète', as_index=False).tail(1)
        if latest_rows.empty:
            latest_rows = fallback_latest.copy()
        else:
            missing_athletes = set(fallback_latest['Athlète']) - set(latest_rows['Athlète'])
            if missing_athletes:
                latest_rows = pd.concat(
                    [latest_rows, fallback_latest[fallback_latest['Athlète'].isin(missing_athletes)]],
                    ignore_index=True,
                )

        if analysis_df.empty:
            st.warning("Aucune donnée disponible pour cette vue.")
        else:
            metric_cols = st.columns(4)
            with metric_cols[0]:
                st.metric("Athlètes suivis", int(analysis_df['Athlète'].nunique()))
            with metric_cols[1]:
                st.metric("Dernière date", format_date_fr(analysis_df['Date'].max()))
            with metric_cols[2]:
                mean_acwr_28 = latest_rows['acwr_7_28'].dropna().mean()
                st.metric("ACWR 7/28 moyen", "N/A" if pd.isna(mean_acwr_28) else f"{mean_acwr_28:.2f}")
            with metric_cols[3]:
                mean_acwr_42 = latest_rows['acwr_7_42'].dropna().mean()
                st.metric("ACWR 7/42 moyen", "N/A" if pd.isna(mean_acwr_42) else f"{mean_acwr_42:.2f}")

            extra_metrics = []
            if progression_meta.get('sleep_column') and 'Sommeil (h)' in analysis_df.columns:
                sleep_mean = analysis_df['Sommeil (h)'].dropna().mean()
                extra_metrics.append(("Sommeil moyen", "N/A" if pd.isna(sleep_mean) else f"{sleep_mean:.1f} h"))
            if progression_meta.get('fatigue_column') and 'Fatigue score' in analysis_df.columns:
                fatigue_mean = analysis_df['Fatigue score'].dropna().mean()
                extra_metrics.append(("Fatigue moyenne", "N/A" if pd.isna(fatigue_mean) else f"{fatigue_mean:.2f}/3"))
            if progression_meta.get('injury_column') and 'Blessure' in analysis_df.columns:
                injury_days = int((analysis_df['Blessure'].fillna(0) > 0).sum())
                extra_metrics.append(("Jours blessure", str(injury_days)))

            if extra_metrics:
                extra_cols = st.columns(len(extra_metrics))
                for col, (label, value) in zip(extra_cols, extra_metrics):
                    with col:
                        st.metric(label, value)

            st.caption(
                f"Fenêtre analysée: {window_start.isoformat()} à {window_end.isoformat()} "
                "avec un pivot centré sur la date des tests physiques."
            )
            st.caption("Cette table est prête à être exportée puis fusionnée avec vos autres données pour suivre les progressions.")

            display_columns = [
                'Athlète', 'Date', 'charge_totale', 'charge_7j', 'charge_28j', 'charge_42j',
                'acwr_7_28', 'acwr_7_42', 'Muscu %', 'Cardio %', 'Hockey %', 'Autres sports %'
            ]
            export_df = pd.DataFrame()
            if 'Sommeil (h)' in analysis_df.columns:
                display_columns.append('Sommeil (h)')
            if 'Fatigue score' in analysis_df.columns:
                display_columns.append('Fatigue score')
            if 'Blessure' in analysis_df.columns:
                display_columns.append('Blessure')

            if analysis_choice == 'Tous les athlètes':
                # charge_totale du tableau = cumul de toutes les journées d'entraînement disponibles.
                cumulative_df = progression_df.copy()
                agg_map = {'charge_totale': 'sum'}
                for col in ['Muscu load', 'Cardio load', 'Hockey load', 'Sport load']:
                    if col in cumulative_df.columns:
                        agg_map[col] = 'sum'

                aggregated = cumulative_df.groupby('Athlète', as_index=False).agg(agg_map)
                sessions_total = (
                    cumulative_df.assign(_session=(pd.to_numeric(cumulative_df['charge_totale'], errors='coerce').fillna(0) > 0).astype(int))
                    .groupby('Athlète', as_index=False)['_session']
                    .sum()
                    .rename(columns={'_session': 'Séances entraînement (total)'})
                )
                aggregated = aggregated.merge(sessions_total, on='Athlète', how='left')

                for col in ['Muscu load', 'Cardio load', 'Hockey load', 'Sport load']:
                    if col not in aggregated.columns:
                        aggregated[col] = 0.0

                aggregated['Muscu %'] = np.where(
                    aggregated['charge_totale'] > 0,
                    (aggregated['Muscu load'] / aggregated['charge_totale']) * 100.0,
                    0.0,
                )
                aggregated['Cardio %'] = np.where(
                    aggregated['charge_totale'] > 0,
                    (aggregated['Cardio load'] / aggregated['charge_totale']) * 100.0,
                    0.0,
                )
                aggregated['Hockey %'] = np.where(
                    aggregated['charge_totale'] > 0,
                    (aggregated['Hockey load'] / aggregated['charge_totale']) * 100.0,
                    0.0,
                )
                aggregated['Autres sports %'] = np.where(
                    aggregated['charge_totale'] > 0,
                    (aggregated['Sport load'] / aggregated['charge_totale']) * 100.0,
                    0.0,
                )

                latest_metrics = latest_rows[['Athlète', 'Date', 'charge_7j', 'charge_28j', 'charge_42j', 'acwr_7_28', 'acwr_7_42']].copy()
                latest_metrics = latest_metrics.rename(columns={'Date': 'Dernière date'})
                latest_metrics['Dernière date'] = pd.to_datetime(latest_metrics['Dernière date'], errors='coerce').dt.date
                if 'Sommeil (h)' in latest_rows.columns:
                    latest_metrics['Sommeil (h)'] = latest_rows['Sommeil (h)'].values
                if 'Fatigue score' in latest_rows.columns:
                    latest_metrics['Fatigue score'] = latest_rows['Fatigue score'].values
                summary_table = aggregated.merge(latest_metrics, on='Athlète', how='left')
                summary_table['Basé sur date pivot'] = summary_table['Dernière date'] == window_start
                summary_table['Référence calcul'] = np.where(summary_table['Basé sur date pivot'], 'Date pivot', 'Autre date')

                summary_columns = [
                    'Athlète', 'Dernière date', 'Séances entraînement (total)', 'charge_totale', 'charge_7j', 'charge_28j', 'charge_42j',
                    'acwr_7_28', 'acwr_7_42', 'Muscu %', 'Cardio %', 'Hockey %', 'Autres sports %'
                ]
                if 'Sommeil (h)' in summary_table.columns:
                    summary_columns.append('Sommeil (h)')
                if 'Fatigue score' in summary_table.columns:
                    summary_columns.append('Fatigue score')
                st.caption("Tableau synthèse par athlète: volumes cumulés, charges récentes (7/28/42 jours), ratios ACWR et répartition par type d'activité.")
                st.dataframe(summary_table[summary_columns], width='stretch', hide_index=True)
                export_df = summary_table[summary_columns].rename(columns={'Dernière date': 'Date'}).copy()

                pivot_ref_columns = ['Athlète', 'Dernière date', 'Référence calcul', 'charge_7j', 'charge_28j', 'charge_42j', 'acwr_7_28', 'acwr_7_42']
                based_on_pivot_df = summary_table[summary_table['Basé sur date pivot']][pivot_ref_columns].copy()
                not_based_on_pivot_df = summary_table[~summary_table['Basé sur date pivot']][pivot_ref_columns].copy()

                c_pivot, c_non_pivot = st.columns(2)
                c_pivot.metric("Calculs basés sur la date pivot", len(based_on_pivot_df))
                c_non_pivot.metric("Calculs basés sur une autre date", len(not_based_on_pivot_df))

                with st.expander("Qui est calculé sur la date pivot et qui ne l'est pas"):
                    st.markdown("**Basé sur la date pivot**")
                    st.caption("Athlètes dont les indicateurs sont calculés sur la date de référence du camp.")
                    if based_on_pivot_df.empty:
                        st.info("Aucun athlète avec calcul basé sur la date pivot.")
                    else:
                        st.dataframe(based_on_pivot_df, width='stretch', hide_index=True)

                    st.markdown("**Basé sur une autre date**")
                    st.caption("Athlètes dont le calcul utilise une autre date, généralement faute de données suffisantes autour de la date pivot.")
                    if not_based_on_pivot_df.empty:
                        st.info("Tous les athlètes sont calculés sur la date pivot.")
                    else:
                        st.dataframe(not_based_on_pivot_df, width='stretch', hide_index=True)

                ranking_df = summary_table[['Athlète', 'charge_totale', 'Dernière date']].copy()
                ranking_df = ranking_df.sort_values('charge_totale', ascending=False).reset_index(drop=True)
                ranking_df['Rang charge'] = ranking_df.index + 1
                ranking_df = ranking_df[['Rang charge', 'Athlète', 'charge_totale', 'Dernière date']]

                st.markdown("**Classement de la charge totale (du plus élevé au plus faible)**")
                st.caption("Ce classement compare la charge cumulée totale de chaque athlète sur la période analysée.")

                fig_ranking = px.bar(
                    ranking_df,
                    x='Athlète',
                    y='charge_totale',
                    title='Charge totale par athlète (ordre décroissant)',
                    category_orders={'Athlète': ranking_df['Athlète'].tolist()},
                )
                fig_ranking.update_layout(showlegend=False)
                st.plotly_chart(fig_ranking, width='stretch')

                problem_rows = []
                for _, row in summary_table.iterrows():
                    athlete = row.get('Athlète')
                    acwr_28 = row.get('acwr_7_28')
                    acwr_42 = row.get('acwr_7_42')
                    charge_7j = row.get('charge_7j')
                    charge_28j = row.get('charge_28j')
                    charge_42j = row.get('charge_42j')

                    def add_problem(metric, value, reason, severity):
                        problem_rows.append({
                            'Athlète': athlete,
                            'Métrique': metric,
                            'Valeur': value,
                            'Problème': reason,
                            'Sévérité': severity,
                        })

                    if pd.isna(charge_7j) or pd.isna(charge_28j) or pd.isna(charge_42j):
                        add_problem('Fenêtres de charge', 'N/A', 'Historique insuffisant pour 7j/28j/42j', 'Moyenne')

                    if pd.notna(acwr_28):
                        if acwr_28 > 1.5:
                            add_problem('ACWR 7/28', f"{acwr_28:.2f}", 'Surcharge élevée', 'Élevée')
                        elif acwr_28 < 0.5:
                            add_problem('ACWR 7/28', f"{acwr_28:.2f}", 'Sous-charge marquée', 'Moyenne')

                    if pd.notna(acwr_42):
                        if acwr_42 > 1.5:
                            add_problem('ACWR 7/42', f"{acwr_42:.2f}", 'Surcharge élevée', 'Élevée')
                        elif acwr_42 < 0.5:
                            add_problem('ACWR 7/42', f"{acwr_42:.2f}", 'Sous-charge marquée', 'Moyenne')

                    for pct_col, label in [('Muscu %', 'Musculation'), ('Cardio %', 'Cardio'), ('Hockey %', 'Hockey'), ('Autres sports %', 'Autres sports')]:
                        pct_value = row.get(pct_col)
                        if pd.notna(pct_value) and pct_value >= 85:
                            add_problem(pct_col, f"{pct_value:.1f}%", f'Charge très concentrée en {label.lower()}', 'Moyenne')

                st.markdown("**Valeurs problématiques**")
                st.caption("Repérage automatique des situations à surveiller: ACWR élevé/bas, historiques incomplets et répartition de charge trop concentrée.")
                if problem_rows:
                    problems_df = pd.DataFrame(problem_rows)
                    severity_order = {'Élevée': 0, 'Moyenne': 1, 'Faible': 2}
                    problems_df['_severity_rank'] = problems_df['Sévérité'].map(severity_order).fillna(99)
                    problems_df = problems_df.sort_values(['_severity_rank', 'Athlète', 'Métrique']).drop(columns=['_severity_rank'])
                    st.dataframe(problems_df, width='stretch', hide_index=True)
                else:
                    st.success("Aucune valeur problématique détectée selon les seuils actuels.")

                # Variabilité en se rapprochant du camp (avant la date pivot).
                pivot_ts = pd.Timestamp(window_start)
                if 'Sommeil (h)' in progression_df.columns or 'Fatigue score' in progression_df.columns:
                    pre_camp_df = progression_df[progression_df['Date'] < pivot_ts].copy()
                    recent_start = pivot_ts - pd.Timedelta(days=14)
                    prev_start = pivot_ts - pd.Timedelta(days=28)

                    variability_rows = []
                    for athlete_id, athlete_hist in pre_camp_df.groupby('Athlète', sort=False):
                        recent = athlete_hist[(athlete_hist['Date'] >= recent_start) & (athlete_hist['Date'] < pivot_ts)]
                        prev = athlete_hist[(athlete_hist['Date'] >= prev_start) & (athlete_hist['Date'] < recent_start)]

                        row = {
                            'Athlète': athlete_id,
                            'Séances entraînement (J-14 à J-1)': int((pd.to_numeric(recent['charge_totale'], errors='coerce').fillna(0) > 0).sum()) if 'charge_totale' in recent.columns else 0,
                        }

                        if 'Sommeil (h)' in pre_camp_df.columns:
                            s_recent = pd.to_numeric(recent['Sommeil (h)'], errors='coerce')
                            s_prev = pd.to_numeric(prev['Sommeil (h)'], errors='coerce')
                            std_recent = float(s_recent.std()) if s_recent.notna().sum() >= 2 else np.nan
                            std_prev = float(s_prev.std()) if s_prev.notna().sum() >= 2 else np.nan
                            delta = std_recent - std_prev if pd.notna(std_recent) and pd.notna(std_prev) else np.nan
                            mean_recent = float(s_recent.mean()) if s_recent.notna().any() else np.nan
                            mean_prev = float(s_prev.mean()) if s_prev.notna().any() else np.nan
                            sleep_delta = mean_recent - mean_prev if pd.notna(mean_recent) and pd.notna(mean_prev) else np.nan

                            if pd.isna(sleep_delta):
                                sleep_trend = 'Données insuffisantes'
                            elif sleep_delta > 0.3:
                                sleep_trend = 'Sommeil augmente'
                            elif sleep_delta < -0.3:
                                sleep_trend = 'Sommeil diminue'
                            else:
                                sleep_trend = 'Sommeil stable'

                            row.update({
                                'Sommeil moyen (J-28 à J-15)': mean_prev,
                                'Sommeil moyen (J-14 à J-1)': mean_recent,
                                'Delta sommeil (h)': sleep_delta,
                                'Tendance sommeil': sleep_trend,
                                'Variabilité sommeil (J-14 à J-1)': std_recent,
                                'Variabilité sommeil (J-28 à J-15)': std_prev,
                                'Delta variabilité sommeil': delta,
                            })

                        if 'Fatigue score' in pre_camp_df.columns:
                            f_recent = pd.to_numeric(recent['Fatigue score'], errors='coerce')
                            f_prev = pd.to_numeric(prev['Fatigue score'], errors='coerce')
                            f_std_recent = float(f_recent.std()) if f_recent.notna().sum() >= 2 else np.nan
                            f_std_prev = float(f_prev.std()) if f_prev.notna().sum() >= 2 else np.nan
                            row.update({
                                'Fatigue moyenne (J-14 à J-1)': float(f_recent.mean()) if f_recent.notna().any() else np.nan,
                                'Variabilité fatigue (J-14 à J-1)': f_std_recent,
                                'Variabilité fatigue (J-28 à J-15)': f_std_prev,
                            })

                        variability_rows.append(row)

                    variability_df = pd.DataFrame(variability_rows)
                    if not variability_df.empty:
                        st.markdown("**Sommeil en se rapprochant du camp (simple à lire)**")
                        st.caption("Comparaison des 14 derniers jours avant le camp (J-14 à J-1) avec les 14 jours précédents (J-28 à J-15).")

                        if 'Delta sommeil (h)' in variability_df.columns:
                            variability_df = variability_df.sort_values('Delta sommeil (h)', ascending=True)

                        simple_cols = [c for c in [
                            'Athlète',
                            'Séances entraînement (J-14 à J-1)',
                            'Sommeil moyen (J-28 à J-15)',
                            'Sommeil moyen (J-14 à J-1)',
                            'Delta sommeil (h)',
                            'Tendance sommeil',
                            'Variabilité sommeil (J-14 à J-1)',
                        ] if c in variability_df.columns]
                        st.caption("Ce tableau aide à voir rapidement si le sommeil monte, baisse ou devient plus irrégulier à l'approche du camp.")
                        st.dataframe(variability_df[simple_cols], width='stretch', hide_index=True)

                        if 'Delta sommeil (h)' in variability_df.columns:
                            chart_df = variability_df[['Athlète', 'Delta sommeil (h)']].dropna().copy()
                            if not chart_df.empty:
                                fig_var = px.bar(
                                    chart_df,
                                    x='Athlète',
                                    y='Delta sommeil (h)',
                                    title='Évolution du sommeil en approchant le camp (J-14 à J-1 vs J-28 à J-15)',
                                    category_orders={'Athlète': chart_df.sort_values('Delta sommeil (h)', ascending=False)['Athlète'].tolist()},
                                )
                                fig_var.add_hline(y=0, line_dash='dash', line_color='#666666')
                                fig_var.update_layout(showlegend=False)
                                st.plotly_chart(fig_var, width='stretch')

                with st.expander("Voir le détail par date (optionnel)"):
                    st.caption("Série chronologique complète de la période filtrée, utile pour vérifier un athlète jour par jour.")
                    st.dataframe(analysis_df[display_columns], width='stretch', hide_index=True)
            else:
                athlete_df = analysis_df.sort_values('Date').copy()
                if not athlete_df.empty:
                    export_df = athlete_df[display_columns].copy()
                    tab_charge, tab_risque, tab_sante = st.tabs(['Charge', 'Risque', 'Sommeil / Blessure'])
                    with tab_charge:
                        fig_charge = px.line(
                            athlete_df,
                            x='Date',
                            y=['charge_totale'],
                            title='Charge quotidienne',
                            markers=True,
                        )
                        st.plotly_chart(fig_charge, width='stretch')
                    with tab_risque:
                        fig_risk = px.line(
                            athlete_df,
                            x='Date',
                            y=['acwr_7_28', 'acwr_7_42'],
                            title='ACWR 7/28 et 7/42',
                            markers=True,
                        )
                        st.plotly_chart(fig_risk, width='stretch')
                    with tab_sante:
                        if 'Sommeil (h)' in athlete_df.columns:
                            fig_sleep = px.line(
                                athlete_df,
                                x='Date',
                                y='Sommeil (h)',
                                title='Sommeil',
                                markers=True,
                            )
                            st.plotly_chart(fig_sleep, width='stretch')
                        else:
                            st.info("Aucune colonne sommeil détectée dans les données.")

                        if 'Fatigue score' in athlete_df.columns:
                            fig_fatigue = px.line(
                                athlete_df,
                                x='Date',
                                y='Fatigue score',
                                title='Fatigue (score)',
                                markers=True,
                            )
                            st.plotly_chart(fig_fatigue, width='stretch')
                        else:
                            st.info("Aucune colonne fatigue détectée dans les données.")

                        if 'Blessure' in athlete_df.columns:
                            injury_count = int((athlete_df['Blessure'].fillna(0) > 0).sum())
                            st.metric("Jours blessure détectés", injury_count)
                        else:
                            st.info("Aucune colonne blessure détectée dans les données.")

                    with st.expander("Voir le tableau détaillé"):
                        st.caption("Historique complet de l'athlète sélectionné sur la période, incluant charge, ACWR et indicateurs de santé disponibles.")
                        st.dataframe(athlete_df[display_columns], width='stretch', hide_index=True)

            export_name = f"progression_{analysis_choice.replace(' ', '_').lower()}.csv"
            export_payload = export_df if not export_df.empty else analysis_df.copy()
            st.download_button(
                "Télécharger la table de progression",
                export_payload.to_csv(index=False).encode('utf-8'),
                file_name=export_name,
                mime='text/csv',
            )

    selected_athlete = st.selectbox("Sélectionner un athlète", athletes)
    if selected_athlete:
        render_athlete_pdf_section(
            selected_athlete,
            f"Document PDF de {selected_athlete}",
            f"coach_{sanitize_filename_component(selected_athlete)}",
        )
        st.divider()
        show_athlete_dashboard(selected_athlete, show_pdf_section=False)


# Vue admin: gestion des utilisateurs, import et édition des données.
def show_admin_dashboard():
    st.title("Administration des données")
    st.markdown("Importez un fichier Qualtrics ou un fichier de données d'entraînement. Seuls les rôles `admin` ou `data_manager` peuvent importer des données.")
    st.caption("Identifiants athlètes masqués dans la vue admin. Réidentification possible via les codes définis dans APP_REID_CODEBOOK / APP_REID_SECRET_KEY (secrets).")
    st.info(
        "Stockage actif: "
        + str(Path(DATA_ROOT).resolve())
        + "\nSi votre hébergeur met l'application en veille puis relance un nouveau conteneur, "
        + "les fichiers modifiés localement peuvent être perdus. Configure APP_DATA_DIR vers un stockage persistant."
    )
    
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
                    prepared_users, mapped_count = apply_admin_name_based_mapping(edited_users)
                    write_credentials_df(prepared_users)
                    if mapped_count > 0:
                        st.success(f"Participants sauvegardés ({len(prepared_users)} utilisateurs). {mapped_count} identifiant(s) athlète corrigé(s) automatiquement via le nom.")
                    else:
                        st.success(f"Participants sauvegardés ({len(prepared_users)} utilisateurs).")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la sauvegarde : {e}")
        with col_users_info:
            st.info(f"Total : {len(credentials_df)} utilisateurs | Après modification : {len(edited_users)} utilisateurs")
    else:
        st.warning("Aucun participant trouvé.")
    
    st.divider()

    st.subheader("📄 Documents PDF par athlète")
    all_known_athletes = sorted(
        set(get_data_athlete_ids()).union(set(get_registered_athlete_ids())),
        key=str.lower
    )
    if not all_known_athletes:
        st.info("Aucun identifiant athlète disponible pour l'instant.")
    else:
        with st.form("admin_upload_athlete_pdf"):
            selected_doc_athlete = st.selectbox(
                "Athlète à associer au PDF",
                all_known_athletes,
                key="admin_pdf_athlete_select",
            )
            uploaded_pdf = st.file_uploader(
                "Choisir un document PDF",
                type=['pdf'],
                key="admin_pdf_file_uploader",
            )
            submitted_pdf = st.form_submit_button("Téléverser / Remplacer le PDF")

            if submitted_pdf:
                saved, error_code, _ = save_athlete_pdf_document(selected_doc_athlete, uploaded_pdf)
                if saved:
                    st.success(f"PDF enregistré pour {selected_doc_athlete}.")
                    st.rerun()
                elif error_code == 'missing_file':
                    st.error("Sélectionne un fichier PDF avant de valider.")
                elif error_code in ('r2_upload_pdf_failed', 'r2_upload_index_failed'):
                    st.error("PDF non synchronisé vers Cloudflare R2. Vérifie la configuration R2 et réessaie.")
                else:
                    st.error("Impossible d'enregistrer le PDF. Vérifie les permissions du dossier de données.")

    docs_df = list_athlete_pdf_documents()
    if docs_df.empty:
        st.caption("Aucun PDF associé pour le moment.")
    else:
        st.markdown("**PDF déjà associés**")
        st.dataframe(docs_df, width='stretch', hide_index=True)

        st.markdown("**Supprimer un PDF**")
        st.caption("Supprime le document associé à un athlète (local et Cloudflare R2 si activé).")
        available_doc_athletes = docs_df['Athlète'].dropna().astype(str).tolist()
        delete_col_1, delete_col_2 = st.columns([2, 1])
        with delete_col_1:
            delete_athlete_id = st.selectbox(
                "Athlète à supprimer",
                available_doc_athletes,
                key="admin_pdf_delete_athlete_select",
            )
        with delete_col_2:
            confirm_delete = st.checkbox("Confirmer", key="admin_pdf_delete_confirm")

        if st.button("Supprimer le PDF sélectionné", key="admin_pdf_delete_button", type="secondary"):
            if not confirm_delete:
                st.warning("Coche 'Confirmer' avant de supprimer.")
            else:
                deleted, delete_error = delete_athlete_pdf_document(delete_athlete_id)
                if deleted:
                    st.success(f"PDF supprimé pour {delete_athlete_id}.")
                    st.rerun()
                elif delete_error == 'not_found':
                    st.warning("Aucun PDF trouvé pour cet athlète.")
                elif delete_error == 'r2_upload_index_failed':
                    st.error("Suppression locale faite, mais la synchronisation de l'index vers Cloudflare R2 a échoué.")
                else:
                    st.error("Impossible de supprimer le PDF. Vérifie les permissions et la configuration R2.")

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
            existing_df = read_main_data_df() if os.path.exists(file_path) else pd.DataFrame()

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
            all_data = read_main_data_df()
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
            'Username': 'Adresse courriel',
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
        athlete_id, was_relinked = resolve_account_athlete_id(username, users['usernames'][username])
        if was_relinked:
            st.info(f"Ton compte a été relié automatiquement à l'identifiant athlète: {athlete_id}")
        show_athlete_dashboard(athlete_id)
    elif user_role == 'coach':
        show_coach_dashboard()
    elif user_role in ['admin', 'data_manager']:
        show_admin_dashboard()
elif authentication_status == False:
    st.error("Nom d'utilisateur ou mot de passe incorrect")
elif authentication_status is None:
    st.warning("Veuillez entrer votre nom d'utilisateur et votre mot de passe")
