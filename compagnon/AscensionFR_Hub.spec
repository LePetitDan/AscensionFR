# -*- mode: python ; coding: utf-8 -*-
# Recette PyInstaller du HUB (interface v3 paysage, compagnon_hub.py).
# DÉCISION DE DAN (23/07/2026) : le Hub REMPLACE le Compagnon — à sa sortie,
# cette recette devient LA recette de release, à la place de
# AscensionFR_Compagnon_v2.spec (qui reste valable pour un correctif v2
# d'urgence tant que le Hub n'est pas publié).
#
# Même mécanique que la v2, point par point :
#   - WEBHOOK_RAPPORTS vit dans compagnon.py (renseigné uniquement dans la
#     copie qui sert à construire l'exe distribué) et se retrouve baké dans
#     l'exe par l'Analysis ;
#   - assets/ embarqué en entier (dont assets/hub : décors + polices du jeu
#     + catalogue_hub.json) ;
#   - parser_wdb via le pathex vers traduction\outils ;
#   - customtkinter reste collecté : compagnon.py l'importe en tête de
#     fichier (sa vieille interface de secours) — sans lui, l'import plante ;
#   - lupa (lecture des stats de contribution) et certifi (contexte SSL
#     hybride) collectés comme en v2.
#
# NOTE distribution : l'exe sort en AscensionFR_Hub.exe pour les essais.
# Au moment de publier, l'asset de release doit s'appeler
# AscensionFR_Compagnon.exe (EXE_ATTENDU dans compagnon.py) : c'est ce nom
# que les Compagnons v2 des joueurs téléchargent en se mettant à jour —
# ils deviendront le Hub tout seuls. VERSION_COMPAGNON doit ÉGALER le tag.
import os
from PyInstaller.utils.hooks import collect_all

datas = [('assets', 'assets')]
binaries = []
hiddenimports = ['parser_wdb']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('lupa')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('certifi')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['compagnon_hub.py'],
    pathex=[os.path.abspath(os.path.join(SPECPATH, '..', 'outils'))],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AscensionFR_Hub',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir='%LOCALAPPDATA%\\\\AscensionFR_Compagnon',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\logo.ico'],
)
