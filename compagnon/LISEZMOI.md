# Le Compagnon Ascension FR

Petite application **optionnelle** qui accompagne la traduction :
installe/met à jour l'addon en un clic, et envoie votre rapport de
contribution en un clic (avec repli copier/coller si vous préférez).

**Transparence totale** : tout le programme tient dans
[`compagnon.py`](compagnon.py) (plus [`parser_wdb.py`](parser_wdb.py), le
lecteur des caches du jeu) — du Python lisible. Il ne contacte que GitHub
(téléchargement des versions) et le salon Discord du projet (envoi du
rapport, uniquement quand VOUS cliquez). Tout ce qui part est du texte du
jeu — quêtes, PNJ, objets croisés en jouant — jamais de pseudo, de
conversation ni de fichier personnel.

## Reconstruire l'exe soi-même

```
pip install customtkinter pyinstaller lupa pillow
python -m PyInstaller AscensionFR_Compagnon.spec
```

L'exe distribué en release est produit exactement ainsi (le fichier `.spec`
est dans ce dossier : PyInstaller onefile fenêtré, icône du projet, modules
customtkinter + lupa + parser_wdb embarqués).
