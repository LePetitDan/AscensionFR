# Le Compagnon Ascension FR

Petite application **optionnelle** qui accompagne la traduction :
installe/met à jour l'addon en un clic, et copie votre rapport de
contribution pour le Discord.

**Transparence totale** : tout le programme tient dans [`compagnon.py`](compagnon.py)
— un seul fichier Python lisible. Il ne contacte que GitHub (téléchargement
des versions) et n'envoie aucune donnée : le rapport est copié dans VOTRE
presse-papiers, c'est vous qui le collez.

## Reconstruire l'exe soi-même

```
pip install customtkinter pyinstaller lupa pillow
python -m PyInstaller --onefile --windowed --name AscensionFR_Compagnon ^
  --icon assets/logo.ico --add-data "assets;assets" ^
  --collect-all customtkinter compagnon.py
```

L'exe distribué en release est produit exactement ainsi.
