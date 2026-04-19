import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta

# Générer des données d'exemple pour tous les athlètes
dates = [datetime(2023, 1, 1) + timedelta(days=i) for i in range(30)]
athletes = ['athlete1', 'athlete2']
all_data = []

for athlete in athletes:
    for date in dates:
        row = {
            'athlete_id': athlete,
            'date': date,
            'musculation': np.random.choice([True, False]),
            'durée_muscu': np.random.randint(30, 120) if np.random.choice([True, False]) else 0,
            'intensité_muscu': np.random.uniform(0.5, 1.0),
            'charge_muscu': 0,  # calculer
            'cardio': np.random.choice([True, False]),
            'durée_cardio': np.random.randint(20, 60) if np.random.choice([True, False]) else 0,
            'intensité_cardio': np.random.uniform(0.3, 0.8),
            'charge_cardio': 0,
            'autres_sports': np.random.choice([True, False]),
            'durée_autres': np.random.randint(30, 90) if np.random.choice([True, False]) else 0,
            'intensité_autres': np.random.uniform(0.4, 0.9),
            'charge_autres': 0,
            'entrainement_hockey': np.random.choice([True, False]),
            'durée_hockey': np.random.randint(60, 120) if np.random.choice([True, False]) else 0,
            'intensité_hockey': np.random.uniform(0.6, 1.0),
            'charge_hockey': 0,
            'skills': np.random.choice([True, False]),
            'durée_skills': np.random.randint(30, 60) if np.random.choice([True, False]) else 0,
            'intensité_skills': np.random.uniform(0.5, 0.9),
            'charge_skills': 0,
            'match': np.random.choice([True, False]),
            'durée_match': 90 if np.random.choice([True, False]) else 0,
            'intensité_match': 0.8,
            'charge_match': 0
        }
        # Calculer charges
        row['charge_muscu'] = row['durée_muscu'] * row['intensité_muscu']
        row['charge_cardio'] = row['durée_cardio'] * row['intensité_cardio']
        row['charge_autres'] = row['durée_autres'] * row['intensité_autres']
        row['charge_hockey'] = row['durée_hockey'] * row['intensité_hockey']
        row['charge_skills'] = row['durée_skills'] * row['intensité_skills']
        row['charge_match'] = row['durée_match'] * row['intensité_match']
        all_data.append(row)

df = pd.DataFrame(all_data)
os.makedirs('private_data', exist_ok=True)
df.to_excel('private_data/trainings.xlsx', index=False)