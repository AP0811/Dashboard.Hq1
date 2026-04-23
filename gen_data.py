# -*- coding: utf-8 -*-
import pandas as pd
import numpy as np
from datetime import date, timedelta
import random

start_date = date(2026, 4, 8)
S_REPOS = "Non j'ai pris une journee de repos / No I needed recovery"
S_BLESSURE = "Non j'ai ete blesse / No I was injured"
S_VACANCES = "Non j'ai ete en vacances / No I was on vacation"
S_TEMPS = "Non j'ai manque de temps / No lack of time"
S_OUI = "Oui / Yes"

rows = []

def make_row(athlete_id, day_offset, activites, pratique_dur=0, pratique_int=0, muscu_dur=0, muscu_int=0, match_dur=0, match_int=0, skills_dur=0, skills_int=0, cardio_dur=0, cardio_int=0, sport_dur=0, sport_int=0, sport_type="", douleur=0, douleur_loc=""):
    d = start_date + timedelta(days=day_offset)
    row = {
        "Id": athlete_id, "Date": pd.Timestamp(d), "Activites": activites,
        "Pratique load": pratique_dur * pratique_int, "Muscu load": muscu_dur * muscu_int,
        "Match load": match_dur * match_int, "Skills load": skills_dur * skills_int,
        "Cardio load": cardio_dur * cardio_int, "Sport load": sport_dur * sport_int
    }
    row["Hockey load"] = row["Pratique load"] + row["Match load"] + row["Skills load"]
    return row

schedules = {
    "athlete_001": [
        dict(activites=S_OUI, pratique_dur=90, pratique_int=6, muscu_dur=60, muscu_int=5),
        dict(activites=S_OUI, pratique_dur=75, pratique_int=5, cardio_dur=30, cardio_int=4),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=7, match_dur=60, match_int=8),
        dict(activites=S_OUI, muscu_dur=75, muscu_int=6, skills_dur=45, skills_int=5),
        dict(activites=S_OUI, pratique_dur=80, pratique_int=6, douleur=3, douleur_loc="genou"),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=7, muscu_dur=60, muscu_int=6),
        dict(activites=S_OUI, cardio_dur=40, cardio_int=5, sport_dur=30, sport_int=3, sport_type="velo"),
        dict(activites=S_BLESSURE, douleur=6, douleur_loc="epaule"),
        dict(activites=S_BLESSURE, douleur=5, douleur_loc="epaule"),
        dict(activites=S_OUI, pratique_dur=60, pratique_int=4, douleur=2, douleur_loc="epaule"),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=6, match_dur=60, match_int=7),
        dict(activites=S_REPOS),
    ],
    "athlete_002": [
        dict(activites=S_OUI, pratique_dur=85, pratique_int=7, skills_dur=40, skills_int=6),
        dict(activites=S_OUI, muscu_dur=70, muscu_int=7, cardio_dur=25, cardio_int=4),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=8),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=80, pratique_int=6, match_dur=65, match_int=8),
        dict(activites=S_OUI, muscu_dur=60, muscu_int=5),
        dict(activites=S_VACANCES),
        dict(activites=S_VACANCES),
        dict(activites=S_OUI, pratique_dur=75, pratique_int=5, skills_dur=35, skills_int=5),
        dict(activites=S_OUI, muscu_dur=80, muscu_int=7, cardio_dur=30, cardio_int=5),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=7, match_dur=55, match_int=7),
        dict(activites=S_OUI, skills_dur=50, skills_int=6, cardio_dur=20, cardio_int=3),
        dict(activites=S_TEMPS),
    ],
    "athlete_003": [
        dict(activites=S_OUI, muscu_dur=65, muscu_int=6, pratique_dur=80, pratique_int=5),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, cardio_dur=45, cardio_int=6, sport_dur=60, sport_int=4, sport_type="natation"),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=6, match_dur=70, match_int=7),
        dict(activites=S_OUI, muscu_dur=55, muscu_int=5, skills_dur=40, skills_int=4),
        dict(activites=S_TEMPS),
        dict(activites=S_OUI, pratique_dur=85, pratique_int=7, douleur=2, douleur_loc="cheville"),
        dict(activites=S_OUI, muscu_dur=70, muscu_int=6, cardio_dur=35, cardio_int=5),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=90, pratique_int=8, skills_dur=45, skills_int=6),
        dict(activites=S_OUI, match_dur=65, match_int=8, douleur=1, douleur_loc="dos"),
        dict(activites=S_OUI, cardio_dur=40, cardio_int=4),
        dict(activites=S_REPOS),
        dict(activites=S_OUI, pratique_dur=80, pratique_int=6, muscu_dur=50, muscu_int=5),
    ],
}

for aid, days in schedules.items():
    for i, cfg in enumerate(days):
        rows.append(make_row(aid, i, **cfg))

df = pd.DataFrame(rows)
df.to_excel("C:/Visual_Code/data/exemple_14jours.xlsx", index=False)
print("Done", df.shape)
