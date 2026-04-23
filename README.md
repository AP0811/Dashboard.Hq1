# Dashboard Charges de Travail Athlètes

Application Streamlit pour visualiser les charges de travail des athlètes, avec authentification pour respecter la loi 25.

## Installation

1. Installer Python 3.8+ depuis https://python.org
2. Cloner ou télécharger le projet
3. Installer les dépendances: `pip install -r requirements.txt`
4. Placer votre fichier de données dans `data/Activités.xlsx`
5. Placer le fichier de comptes utilisateurs dans `data/credentials/users.csv` ou `data/credentials/users.xlsx`
   - `users.csv` est recommandé car il évite les problèmes de verrouillage de fichier Excel.
6. Lancer l'application: `streamlit run app.py`

## Utilisation

- Se connecter avec un compte athlète ou coach
- Un athlète voit uniquement son propre dashboard
- Un coach peut sélectionner n'importe quel athlète dans le fichier
- Les athlètes peuvent créer leur propre mot de passe depuis la barre latérale
- Les comptes `admin` / `data_manager` peuvent importer de nouvelles données via l'interface d'administration


## Sécurité et Conformité Loi 25

- Authentification requise pour accéder aux données
- Données chiffrées en transit (HTTPS recommandé en production)
- Accès limité selon le rôle (athlète voit seulement ses données, coach voit tous)
- En production, utiliser une base de données sécurisée et chiffrée
- Obtenir le consentement des athlètes pour le traitement des données
- Implémenter les droits d'accès, rectification et suppression des données

## Format des Données

Fichier Excel `data/Activités.xlsx` avec colonnes principales:
- `Id` : identifiant de l'athlète (par exemple un email)
- `Date` : date de l'entraînement
- `Total load` : charge totale du jour
- `Muscu load` : charge musculation
- `Cardio load` : charge cardio
- `Hockey load` : charge hockey
- `Sport load` : charge autres sports
- `Pratique load` : charge entraînement/utile
- `Match load` : charge match
- `Skills load` : charge skills

Le script supporte également un ancien format avec `data/trainings.xlsx` si présent.

Chaque ligne représente une journée d'entraînement pour un athlète.

## Calcul de la Charge Totale

Charge totale par jour = `Total load` si disponible, sinon somme des colonnes `* load`.

## Calcul de la Monotonie

Monotonie = Moyenne des charges hebdomadaires / Écart-type des charges quotidiennes

Une monotonie élevée indique une charge régulière et peu de variation.
