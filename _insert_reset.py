path = 'c:/Visual_Code/app.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

reset_block = (
    "\n# \u2500\u2500 R\u00e9initialisation via lien courriel (token dans l'URL) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    "_reset_token_param = st.query_params.get('reset_token')\n"
    "if _reset_token_param:\n"
    "    _email_from_token = verify_reset_token(_reset_token_param)\n"
    "    if _email_from_token is None:\n"
    "        st.error('Ce lien de r\u00e9initialisation est invalide ou a expir\u00e9. Demande un nouveau lien.')\n"
    "    else:\n"
    "        st.title('Choisir un nouveau mot de passe')\n"
    "        st.info(f'R\u00e9initialisation pour : **{_email_from_token}**')\n"
    "        with st.form('new_password_form'):\n"
    "            new_pw1 = st.text_input('Nouveau mot de passe', type='password', key='new_pw1')\n"
    "            new_pw2 = st.text_input('Confirmer le mot de passe', type='password', key='new_pw2')\n"
    "            if st.form_submit_button('Enregistrer le mot de passe'):\n"
    "                if not new_pw1 or not new_pw2:\n"
    "                    st.error('Les deux champs sont requis.')\n"
    "                elif new_pw1 != new_pw2:\n"
    "                    st.error('Les mots de passe ne correspondent pas.')\n"
    "                else:\n"
    "                    _updated, _msg = update_password_in_file(_email_from_token, new_pw1)\n"
    "                    if _updated:\n"
    "                        consume_reset_token(_reset_token_param)\n"
    "                        st.success('Mot de passe mis \u00e0 jour. Tu peux maintenant te connecter.')\n"
    "                        st.query_params.clear()\n"
    "                        st.rerun()\n"
    "                    elif _msg == 'permission':\n"
    "                        st.error(\"Impossible d'\u00e9crire le fichier des identifiants. V\u00e9rifie les permissions.\")\n"
    "                    else:\n"
    "                        st.error('Erreur lors de la mise \u00e0 jour. R\u00e9essaie ou contacte un administrateur.')\n"
    "    st.stop()\n"
    "\n"
)

insert_at = 1118
new_lines = lines[:insert_at] + [reset_block] + lines[insert_at:]
with open(path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Done. Total lines:', len(new_lines))
