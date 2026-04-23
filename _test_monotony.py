# -*- coding: utf-8 -*-
import pandas as pd

def calculate_monotony(df):
    if df.empty:
        return 0
    df = df.copy()
    df['_date'] = pd.to_datetime(df['Date']).dt.normalize()
    daily_load = df.groupby('_date')['charge_totale'].sum()
    if len(daily_load) >= 2:
        full_range = pd.date_range(daily_load.index.min(), daily_load.index.max(), freq='D')
        daily_load = daily_load.reindex(full_range, fill_value=0)
    if len(daily_load) < 7:
        return 0
    rolling_mean = daily_load.rolling(7).mean()
    rolling_std  = daily_load.rolling(7).std()
    safe_std = rolling_std.where(rolling_std > 0, other=float('nan'))
    monotony = rolling_mean / safe_std
    valid = monotony.dropna()
    if valid.empty:
        return 0
    return float(valid.iloc[-1])

df = pd.read_excel('private_data/trainings.xlsx')
df['Date'] = pd.to_datetime(df['Date'])
load_cols = [c for c in df.columns if c.lower().endswith('load') and c not in ['Total load','charge_totale','Hockey load']]
print('load_cols:', load_cols)
df['charge_totale'] = df[load_cols].fillna(0).sum(axis=1)

for athlete_id in df['Id'].dropna().unique():
    a = df[df['Id'] == str(athlete_id).strip()].copy()
    total = a['charge_totale'].sum()
    m = calculate_monotony(a)
    print(f"{athlete_id}: nb_jours={len(a)}, charge_totale={total:.0f}, monotonie={m:.3f}")
