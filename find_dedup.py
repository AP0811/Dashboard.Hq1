lines = open('C:/Visual_Code/app.py', encoding='utf-8').readlines()
for i, l in enumerate(lines, 1):
    if any(w in l for w in ['deduplicate', 'drop_duplicates', 'combined', '_key']):
        print(i, l.rstrip())
