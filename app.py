import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import os
import plotly.express as px

# Configuration des utilisateurs
# En production, utiliser une base de données sécurisée et une gestion des rôles centralisée
CREDENTIALS_FOLDER = os.path.join('data', 'credentials')
CREDENTIALS_XLSX = os.path.join(CREDENTIALS_FOLDER, 'users.xlsx')
CREDENTIALS_CSV = os.path.join(CREDENTIALS_FOLDER, 'users.csv')

DEFAULT_USERS = {
    "laulo.foster@icloud.com": {"name": "Laulo", "password": "pass1", "role": "athlete", "id": "laulo.foster@icloud.com"},
    "laurie.aubin87@gmail.com": {"name": "Laurie", "password": "pass2", "role": "athlete", "id": "laurie.aubin87@gmail.com"},
    "coach1": {"name": "Coach 1", "password": "coachpass", "role": "coach", "id": "coach1"},
    "admin": {"name": "Admin", "password": "adminpass", "role": "admin", "id": "admin"}
}

file_path = 'data/Activités.xlsx' if os.path.exists('data/Activités.xlsx') else 'data/trainings.xlsx'


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


def read_credentials_df():
    if os.path.exists(CREDENTIALS_CSV):
        return pd.read_csv(CREDENTIALS_CSV)
    if os.path.exists(CREDENTIALS_XLSX):
        try:
            return pd.read_excel(CREDENTIALS_XLSX)
        except PermissionError:
            st.warning('Le fichier credentials Excel est ouvert dans une autre application. Ferme-le pour charger les comptes.')
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
            st.warning('Le fichier de credentials doit contenir au moins les colonnes email et password.')
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


def normalize_uploaded_data(df):
    date_col = find_column(df.columns, ['date', 'Date'])
    athlete_id_col = find_column(df.columns, ['athlete_id', 'Id', 'utilisateur', 'Utilisateur'])
    if date_col is None or athlete_id_col is None:
        return None, None, 'Le fichier doit contenir au moins une colonne date et une colonne Id / athlete_id.'

    if date_col != 'Date':
        df = df.rename(columns={date_col: 'Date'})
    if athlete_id_col != 'Id':
        df = df.rename(columns={athlete_id_col: 'Id'})

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
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


with st.sidebar.expander('Créer un compte'):
    with st.form('register_form', clear_on_submit=True):
        new_email = st.text_input('Adresse courriel')
        new_name = st.text_input('Nom complet')
        new_password = st.text_input('Mot de passe', type='password')
        athlete_id = st.text_input('Identifiant athlète (facultatif)')
        if st.form_submit_button('Créer un compte'):
            if not new_email or not new_password:
                st.error('Email et mot de passe sont requis.')
            else:
                if not athlete_id:
                    athlete_id = new_email
                created, msg = append_user_to_file(new_email, new_name or new_email, new_password, 'athlete', athlete_id)
                if created:
                    st.success('Compte créé. Recharge la page pour te connecter.')
                    st.experimental_rerun()
                elif msg == 'exists':
                    st.warning('Cet email existe déjà. Utilise la récupération de mot de passe si nécessaire.')
                elif msg == 'permission':
                    st.error('Impossible d’écrire le fichier de credentials. Ferme le fichier Excel ou vérifie les permissions.')
                else:
                    st.error('Impossible de créer le compte. Vérifie les informations et réessaie.')

with st.sidebar.expander('Mot de passe oublié'):
    with st.form('reset_form', clear_on_submit=True):
        reset_email = st.text_input('Adresse courriel', key='reset_email')
        reset_password = st.text_input('Nouveau mot de passe', type='password', key='reset_password')
        if st.form_submit_button('Réinitialiser le mot de passe'):
            if not reset_email or not reset_password:
                st.error('Email et nouveau mot de passe sont requis.')
            else:
                updated, msg = update_password_in_file(reset_email, reset_password)
                if updated:
                    st.success('Mot de passe mis à jour. Recharge la page pour te connecter.')
                    st.experimental_rerun()
                elif msg == 'not_found':
                    st.error('Aucun compte trouvé pour cet email.')
                elif msg == 'permission':
                    st.error('Impossible d’écrire le fichier de credentials. Ferme le fichier Excel ou vérifie les permissions.')
                else:
                    st.error('Impossible de réinitialiser le mot de passe.')

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

    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
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
    weekly_load = daily_load.resample('W').sum()
    mean_weekly = weekly_load.mean()
    std_daily = daily_load.std()
    if std_daily == 0:
        return float('inf')
    return mean_weekly / std_daily


def show_athlete_dashboard(athlete_id):
    st.title(f"Dashboard - {athlete_id}")
    df = load_athlete_data(athlete_id)
    if df.empty:
        st.warning("Aucune donnée disponible pour cet athlète.")
        return

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

    st.subheader("Charge par Activité")
    if activity_cols:
        plot_df = df[['Date'] + list(activity_cols.values())].melt(
            id_vars=['Date'],
            value_vars=list(activity_cols.values()),
            var_name='charge_column',
            value_name='Charge'
        )
        plot_df['Activité'] = plot_df['charge_column'].map({v: k for k, v in activity_cols.items()})
        fig = px.bar(plot_df, x='Date', y='Charge', color='Activité', title="Charge par Activité")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucune colonne de charge d'activité détectée dans le fichier.")

    st.subheader("Charge Totale")
    fig2 = px.line(df, x='Date', y='charge_totale', title="Charge Totale Quotidienne")
    st.plotly_chart(fig2, use_container_width=True)

    monotony = calculate_monotony(df)
    st.subheader("Monotonie")
    st.metric("Monotonie", "∞" if monotony == float('inf') else f"{monotony:.2f}")


def show_coach_dashboard():
    st.title("Dashboard Coach - Tous les Athlètes")
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

        if st.button("Ajouter ces données au fichier principal"):
            existing_df = pd.read_excel(file_path) if os.path.exists(file_path) else pd.DataFrame()
            combined = pd.concat([existing_df, df_normalized], ignore_index=True)
            if save_data_file(combined):
                st.success(f"Données importées dans {file_path}.")
            else:
                st.error('Impossible d’écrire le fichier principal. Ferme-le dans Excel ou vérifie les permissions.')


authenticator = stauth.Authenticate(
    credentials=users,
    cookie_name='workout_dashboard',
    key='some_key',
    cookie_expiry_days=30
)

authenticator.login('main')

authentication_status = st.session_state.get('authentication_status')
name = st.session_state.get('name')
username = st.session_state.get('username')

if authentication_status:
    authenticator.logout('Logout', 'main')
    st.write(f'Welcome *{name}*')
    user_role = users['usernames'][username]['role']
    if user_role == 'athlete':
        athlete_id = users['usernames'][username]['id']
        show_athlete_dashboard(athlete_id)
    elif user_role == 'coach':
        show_coach_dashboard()
    elif user_role in ['admin', 'data_manager']:
        show_admin_dashboard()
elif authentication_status == False:
    st.error('Username/password is incorrect')
elif authentication_status is None:
    st.warning('Please enter your username and password')