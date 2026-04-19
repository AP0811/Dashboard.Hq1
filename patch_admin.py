content = open('app.py', encoding='utf-8').read()

lines = content.splitlines(keepends=True)

# Find line 720 (index 719) - the button line
start_idx = None
for i, line in enumerate(lines):
    if 'if st.button("Ajouter ces donn' in line:
        start_idx = i
        break

if start_idx is None:
    print("Bouton non trouvé")
    exit()

print(f"Bouton trouvé à la ligne {start_idx+1}")

# Find end of this block (next st.subheader at indent 4)
end_idx = start_idx + 1
while end_idx < len(lines):
    line = lines[end_idx]
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    if stripped and indent <= 4 and not stripped.startswith('#'):
        break
    end_idx += 1

new_block = '''        if st.button("Ajouter ces données au fichier principal"):
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
                st.dataframe(pd.DataFrame(report_rows), use_container_width=True)

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
'''

new_lines = lines[:start_idx] + [new_block] + lines[end_idx:]
open('app.py', 'w', encoding='utf-8').write(''.join(new_lines))
print("Modification réussie!")

old = '''        if st.button("Ajouter ces données au fichier principal"):
            existing_df = pd.read_excel(file_path) if os.path.exists(file_path) else pd.DataFrame()
            
            # Dédupliquer les données importées (enlever les doublons Id + Date)
            df_deduplicated = deduplicate_data(df_normalized, existing_df)
            
            # Combiner les données existantes avec les nouvelles données dédupliquées
            combined = pd.concat([existing_df, df_deduplicated], ignore_index=True)
            
            if save_data_file(combined):
                # Sauvegarder la date max
                if save_max_data_date(max_data_date):
                    st.success(f"Données importées dans {file_path}. Date limite définie au {max_data_date}.")
                else:
                    st.success(f"Données importées dans {file_path}. (Attention: impossible de sauvegarder la date limite)")
            else:
                st.error('Impossible d\\'écrire le fichier principal. Ferme-le dans Excel ou vérifie les permissions.')'''

new = '''        if st.button("Ajouter ces données au fichier principal"):
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
                st.dataframe(pd.DataFrame(report_rows), use_container_width=True)
            
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
                st.error('Impossible d\\'écrire le fichier principal. Ferme-le dans Excel ou vérifie les permissions.')'''

if old in content:
    new_content = content.replace(old, new, 1)
    open('app.py', 'w', encoding='utf-8').write(new_content)
    print("Modification réussie!")
else:
    # Debug: show what's actually around line 720
    lines = content.splitlines()
    for i in range(718, 740):
        print(f"{i+1}: {repr(lines[i])}")
    print("PATTERN NON TROUVÉ")
