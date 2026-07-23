# Le Hub Ascension FR

Application **optionnelle** qui accompagne la traduction :

- installe / met à jour l'addon de traduction en un clic ;
- propose un **catalogue d'addons communautaires français** à installer et
  mettre à jour d'un bouton ;
- installe les **voix françaises** (doublages d'époque des PNJ) ;
- envoie votre **rapport de contribution** en un clic (avec repli
  copier/coller si vous préférez).

Le Hub remplace l'ancien Compagnon ; si vous l'aviez, il se met à jour tout
seul vers le Hub.

## Transparence

Le programme est du Python lisible :

- [`interface_hub.py`](interface_hub.py) — l'interface (fenêtre façon *World
  of Warcraft*) ;
- [`compagnon.py`](compagnon.py) — le moteur : téléchargement des versions,
  installation, lecture des statistiques, envoi du rapport ;
- [`parser_wdb.py`](parser_wdb.py) — le lecteur des caches du jeu ;
- [`compagnon_hub.py`](compagnon_hub.py) — le point d'entrée.

Il ne contacte que **GitHub** (téléchargement des versions et du catalogue)
et le **salon Discord** du projet (envoi du rapport, uniquement quand VOUS
cliquez). Tout ce qui part est du texte du jeu — quêtes, PNJ, objets croisés
en jouant — jamais de pseudo, de conversation ni de fichier personnel.

## Aucun fichier du jeu redistribué

Les **décors** de la fenêtre sont générés par
[`fabriquer_decor_hub.py`](fabriquer_decor_hub.py) **à partir des textures de
votre propre installation du jeu** : aucune image du jeu n'est redistribuée
ici, fidèle au principe du projet.

## Reconstruire l'exe soi-même

```
pip install customtkinter pyinstaller lupa pillow certifi
python -m PyInstaller AscensionFR_Hub.spec
```

L'exe distribué en release s'appelle `AscensionFR_Compagnon.exe` (ce nom
permet aux anciens Compagnons de se mettre à jour vers le Hub) ; le `.spec`
qui le produit est dans ce dossier.
