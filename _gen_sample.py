# -*- coding: utf-8 -*-
import pandas as pd
from datetime import date, timedelta

start_date = date(2026, 4, 8)

STATUS_REPOS    = "Non j'ai pris une journée de repos / No I needed recovery"
STATUS_BLESSURE = "Non j'ai été blessé(e) / No I was injured"
STATUS_VACANCES = "Non j'ai été en vacances / No I was on vacation"
STATUS_TEMPS    = "Non j'ai manqué de temps / No lack of time"
STATUS_OUI      = "Oui / Yes"

def row(athlete_id, day_offset, activites,
        pratique_dur=0, pratique_int=0,
        muscu_dur=0,    muscu_int=0,
        match_dur=0,    match_int=0,
        skills_dur=0,   skills_int=0,
        cardio_dur=0,   cardio_int=0,
        sport_dur=0,    sport_int=0, sport_type='',
        douleur=0,      douleur_loc=''):
    pratique_load = pratique_dur * pratique_int
    muscu_load    = muscu_dur    * muscu_int
    match_load    = match_dur    * match_int
    skills_load   = skills_dur   * skills_int
    cardio_load   = cardio_dur   * cardio_int
    sport_load    = sport_dur    * sport_int
    return {
        'Id':   athlete_id,
        'Date': pd.Timestamp(start_date + timedelta(days=day_offset)),
        'Activités': activites,
        'Entraînement sur glace':             'oui / yes' if pratique_dur > 0 else '',
        'Intensité (entraînement sur glace)': pratique_int if pratique_dur > 0 else '',
        'Durée (entraînement sur glace)':     pratique_dur if pratique_dur > 0 else '',
        'Skills coach (entraînement sur glace)': 'oui / yes' if pratique_dur > 0 else '',
        'Musculation':             'oui / yes' if muscu_dur > 0 else '',
        'Intensité (musculation)': muscu_int if muscu_dur > 0 else '',
        'Durée (musculation)':     muscu_dur if muscu_dur > 0 else '',
        'Skills coach (musculation)': '',
        'Match':             'oui / yes' if match_dur > 0 else '',
        'Intensité (match)': match_int if match_dur > 0 else '',
        'Durée (match)':     match_dur if match_dur > 0 else '',
        'Skills':             'oui / yes' if skills_dur > 0 else '',
        'Intensité (skills)': skills_int if skills_dur > 0 else '',
        'Durée (skills)':     skills_dur if skills_dur > 0 else '',
        'Skills coach (skills)': '',
        'Cardio':             'oui / yes' if cardio_dur > 0 else '',
        'Intensité (cardio)': cardio_int if cardio_dur > 0 else '',
        'Durée (cardio)':     cardio_dur if cardio_dur > 0 else '',
        'Douleur':              douleur,
        'Localisation (douleur)': douleur_loc,
        'Autres sports':            'oui / yes' if sport_dur > 0 else '',
        'Précisez le sport':        sport_type,
        'Intensité (autres sports)': sport_int if sport_dur > 0 else '',
        'Durée (autres sports)':     sport_dur if sport_dur > 0 else '',
        'Pratique load': pratique_load,
        'Muscu load':    muscu_load,
        'Match load':    match_load,
        'Skills load':   skills_load,
        'Cardio load':   cardio_load,
        'Sport load':    sport_load,
        'Hockey load':   pratique_load + match_load + skills_load,
    }

rows = []


def extend_schedule(athlete_id, start_offset, total_days, pattern):
    generated_rows = []
    for offset in range(start_offset, total_days):
        day_cfg = dict(pattern[(offset - start_offset) % len(pattern)])
        generated_rows.append(row(athlete_id, offset, **day_cfg))
    return generated_rows

# --- Marie Tremblay (athlete_001) ---
rows += [
    row('athlete_001', 0,  STATUS_OUI,      pratique_dur=90, pratique_int=6, muscu_dur=60, muscu_int=5),
    row('athlete_001', 1,  STATUS_OUI,      pratique_dur=75, pratique_int=5, cardio_dur=30, cardio_int=4),
    row('athlete_001', 2,  STATUS_REPOS),
    row('athlete_001', 3,  STATUS_OUI,      pratique_dur=90, pratique_int=7, match_dur=60, match_int=8),
    row('athlete_001', 4,  STATUS_OUI,      muscu_dur=75, muscu_int=6, skills_dur=45, skills_int=5),
    row('athlete_001', 5,  STATUS_OUI,      pratique_dur=80, pratique_int=6, douleur=3, douleur_loc='genou'),
    row('athlete_001', 6,  STATUS_REPOS),
    row('athlete_001', 7,  STATUS_OUI,      pratique_dur=90, pratique_int=7, muscu_dur=60, muscu_int=6),
    row('athlete_001', 8,  STATUS_OUI,      cardio_dur=40, cardio_int=5, sport_dur=30, sport_int=3, sport_type='vélo'),
    row('athlete_001', 9,  STATUS_BLESSURE, douleur=6, douleur_loc='épaule'),
    row('athlete_001', 10, STATUS_BLESSURE, douleur=5, douleur_loc='épaule'),
    row('athlete_001', 11, STATUS_OUI,      pratique_dur=60, pratique_int=4, douleur=2, douleur_loc='épaule'),
    row('athlete_001', 12, STATUS_OUI,      pratique_dur=90, pratique_int=6, match_dur=60, match_int=7),
    row('athlete_001', 13, STATUS_REPOS),
]

rows += extend_schedule('athlete_001', 14, 38, [
    dict(activites=STATUS_OUI,      pratique_dur=85, pratique_int=6, muscu_dur=55, muscu_int=5),
    dict(activites=STATUS_OUI,      cardio_dur=35, cardio_int=5, sport_dur=30, sport_int=4, sport_type='vélo'),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI,      pratique_dur=95, pratique_int=7, match_dur=55, match_int=8),
    dict(activites=STATUS_OUI,      muscu_dur=70, muscu_int=6, skills_dur=40, skills_int=5),
    dict(activites=STATUS_BLESSURE, douleur=4, douleur_loc='épaule'),
    dict(activites=STATUS_OUI,      pratique_dur=60, pratique_int=4, douleur=2, douleur_loc='épaule'),
])

# Derniers 7 jours volontairement trop stables et trop chargés:
# monotonie élevée (faible variation quotidienne) + ACWR élevé (grosse hausse aiguë)
rows += [
    row('athlete_001', 38, STATUS_OUI, pratique_dur=110, pratique_int=6, muscu_dur=50, muscu_int=4),
    row('athlete_001', 39, STATUS_OUI, pratique_dur=108, pratique_int=6, muscu_dur=52, muscu_int=4),
    row('athlete_001', 40, STATUS_OUI, pratique_dur=112, pratique_int=6, muscu_dur=48, muscu_int=4),
    row('athlete_001', 41, STATUS_OUI, pratique_dur=109, pratique_int=6, muscu_dur=51, muscu_int=4),
    row('athlete_001', 42, STATUS_OUI, pratique_dur=111, pratique_int=6, muscu_dur=49, muscu_int=4),
    row('athlete_001', 43, STATUS_OUI, pratique_dur=110, pratique_int=6, muscu_dur=50, muscu_int=4),
    row('athlete_001', 44, STATUS_OUI, pratique_dur=109, pratique_int=6, muscu_dur=50, muscu_int=4),
]

# --- Alex Bouchard (athlete_002) ---
rows += [
    row('athlete_002', 0,  STATUS_OUI,      pratique_dur=85, pratique_int=7, skills_dur=40, skills_int=6),
    row('athlete_002', 1,  STATUS_OUI,      muscu_dur=70, muscu_int=7, cardio_dur=25, cardio_int=4),
    row('athlete_002', 2,  STATUS_OUI,      pratique_dur=90, pratique_int=8),
    row('athlete_002', 3,  STATUS_REPOS),
    row('athlete_002', 4,  STATUS_OUI,      pratique_dur=80, pratique_int=6, match_dur=65, match_int=8),
    row('athlete_002', 5,  STATUS_OUI,      muscu_dur=60, muscu_int=5),
    row('athlete_002', 6,  STATUS_VACANCES),
    row('athlete_002', 7,  STATUS_VACANCES),
    row('athlete_002', 8,  STATUS_OUI,      pratique_dur=75, pratique_int=5, skills_dur=35, skills_int=5),
    row('athlete_002', 9,  STATUS_OUI,      muscu_dur=80, muscu_int=7, cardio_dur=30, cardio_int=5),
    row('athlete_002', 10, STATUS_REPOS),
    row('athlete_002', 11, STATUS_OUI,      pratique_dur=90, pratique_int=7, match_dur=55, match_int=7),
    row('athlete_002', 12, STATUS_OUI,      skills_dur=50, skills_int=6, cardio_dur=20, cardio_int=3),
    row('athlete_002', 13, STATUS_TEMPS),
]

rows += extend_schedule('athlete_002', 14, 45, [
    dict(activites=STATUS_OUI,      pratique_dur=80, pratique_int=6, skills_dur=35, skills_int=5),
    dict(activites=STATUS_OUI,      muscu_dur=75, muscu_int=6, cardio_dur=25, cardio_int=4),
    dict(activites=STATUS_OUI,      pratique_dur=90, pratique_int=7),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI,      pratique_dur=75, pratique_int=5, match_dur=60, match_int=8),
    dict(activites=STATUS_VACANCES),
    dict(activites=STATUS_TEMPS),
])

# --- Camille Lavoie (athlete_003) ---
rows += [
    row('athlete_003', 0,  STATUS_OUI,      muscu_dur=65, muscu_int=6, pratique_dur=80, pratique_int=5),
    row('athlete_003', 1,  STATUS_REPOS),
    row('athlete_003', 2,  STATUS_OUI,      cardio_dur=45, cardio_int=6, sport_dur=60, sport_int=4, sport_type='natation'),
    row('athlete_003', 3,  STATUS_OUI,      pratique_dur=90, pratique_int=6, match_dur=70, match_int=7),
    row('athlete_003', 4,  STATUS_OUI,      muscu_dur=55, muscu_int=5, skills_dur=40, skills_int=4),
    row('athlete_003', 5,  STATUS_TEMPS),
    row('athlete_003', 6,  STATUS_OUI,      pratique_dur=85, pratique_int=7, douleur=2, douleur_loc='cheville'),
    row('athlete_003', 7,  STATUS_OUI,      muscu_dur=70, muscu_int=6, cardio_dur=35, cardio_int=5),
    row('athlete_003', 8,  STATUS_REPOS),
    row('athlete_003', 9,  STATUS_OUI,      pratique_dur=90, pratique_int=8, skills_dur=45, skills_int=6),
    row('athlete_003', 10, STATUS_OUI,      match_dur=65, match_int=8, douleur=1, douleur_loc='dos'),
    row('athlete_003', 11, STATUS_OUI,      cardio_dur=40, cardio_int=4),
    row('athlete_003', 12, STATUS_REPOS),
    row('athlete_003', 13, STATUS_OUI,      pratique_dur=80, pratique_int=6, muscu_dur=50, muscu_int=5),
]

rows += extend_schedule('athlete_003', 14, 45, [
    dict(activites=STATUS_OUI,      muscu_dur=60, muscu_int=5, pratique_dur=85, pratique_int=6),
    dict(activites=STATUS_OUI,      cardio_dur=40, cardio_int=5, sport_dur=50, sport_int=4, sport_type='natation'),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI,      pratique_dur=90, pratique_int=7, match_dur=65, match_int=7),
    dict(activites=STATUS_OUI,      skills_dur=45, skills_int=5, muscu_dur=50, muscu_int=5),
    dict(activites=STATUS_TEMPS),
    dict(activites=STATUS_OUI,      pratique_dur=75, pratique_int=6, douleur=2, douleur_loc='cheville'),
])

# --- Samuel Roy (athlete_004) : surentraînement ---
# Base déjà chargée, puis dernier bloc de 7 jours très élevé et très stable.
rows += extend_schedule('athlete_004', 0, 38, [
    dict(activites=STATUS_OUI, pratique_dur=80, pratique_int=5, muscu_dur=45, muscu_int=4),
    dict(activites=STATUS_OUI, cardio_dur=30, cardio_int=4, skills_dur=35, skills_int=4),
    dict(activites=STATUS_OUI, pratique_dur=85, pratique_int=5),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI, pratique_dur=75, pratique_int=5, match_dur=50, match_int=6),
    dict(activites=STATUS_OUI, muscu_dur=50, muscu_int=5),
    dict(activites=STATUS_OUI, cardio_dur=25, cardio_int=4),
])

rows += [
    row('athlete_004', 38, STATUS_OUI, pratique_dur=120, pratique_int=6, muscu_dur=60, muscu_int=4),
    row('athlete_004', 39, STATUS_OUI, pratique_dur=119, pratique_int=6, muscu_dur=61, muscu_int=4),
    row('athlete_004', 40, STATUS_OUI, pratique_dur=121, pratique_int=6, muscu_dur=59, muscu_int=4),
    row('athlete_004', 41, STATUS_OUI, pratique_dur=120, pratique_int=6, muscu_dur=60, muscu_int=4),
    row('athlete_004', 42, STATUS_OUI, pratique_dur=122, pratique_int=6, muscu_dur=58, muscu_int=4),
    row('athlete_004', 43, STATUS_OUI, pratique_dur=120, pratique_int=6, muscu_dur=60, muscu_int=4),
    row('athlete_004', 44, STATUS_OUI, pratique_dur=121, pratique_int=6, muscu_dur=59, muscu_int=4),
]

# --- Julien Gagnon (athlete_005) : sous-entraînement puis grosse semaine ---
# 38 premiers jours très faibles, puis saut brutal sur 7 jours.
rows += extend_schedule('athlete_005', 0, 38, [
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI, cardio_dur=20, cardio_int=3),
    dict(activites=STATUS_TEMPS),
    dict(activites=STATUS_REPOS),
    dict(activites=STATUS_OUI, muscu_dur=25, muscu_int=3),
    dict(activites=STATUS_REPOS),
])

rows += [
    row('athlete_005', 38, STATUS_OUI, pratique_dur=110, pratique_int=6, muscu_dur=55, muscu_int=4),
    row('athlete_005', 39, STATUS_OUI, pratique_dur=109, pratique_int=6, muscu_dur=56, muscu_int=4),
    row('athlete_005', 40, STATUS_OUI, pratique_dur=111, pratique_int=6, muscu_dur=54, muscu_int=4),
    row('athlete_005', 41, STATUS_OUI, pratique_dur=110, pratique_int=6, muscu_dur=55, muscu_int=4),
    row('athlete_005', 42, STATUS_OUI, pratique_dur=112, pratique_int=6, muscu_dur=53, muscu_int=4),
    row('athlete_005', 43, STATUS_OUI, pratique_dur=110, pratique_int=6, muscu_dur=55, muscu_int=4),
    row('athlete_005', 44, STATUS_OUI, pratique_dur=111, pratique_int=6, muscu_dur=54, muscu_int=4),
]

df = pd.DataFrame(rows)
df.to_excel('data/exemple_14jours.xlsx', index=False)
print(f'Fichier généré : data/exemple_14jours.xlsx ({len(df)} lignes, {len(df.columns)} colonnes)')
