# -*- coding: utf-8 -*-
"""
plateforme.py — couche d'abstraction système du Compagnon / Hub AscensionFR.
============================================================================
But : rendre l'outil utilisable sous Linux (Ascension tourne alors via un
runner Wine/Proton — Faugus, Lutris, Steam Proton, Bottles…) SANS toucher au
comportement Windows.

Principe : sur Windows, chaque fonction délègue aux appels d'origine (résultat
STRICTEMENT identique à avant). Sur Linux, elle fournit l'équivalent natif. Le
code Windows historique (winreg, ctypes.windll, os.startfile) n'est pas
supprimé de compagnon.py / interface_hub.py : il reste appelé, simplement
derrière un garde de plateforme.

Aucune dépendance tierce : ce module se contente de la bibliothèque standard.
"""
import glob
import json
import os
import subprocess
import sys

EST_WINDOWS = sys.platform.startswith("win")
EST_MAC = sys.platform == "darwin"
EST_LINUX = sys.platform.startswith("linux")


# --------------------------------------------------------------------------- #
# Dossier de configuration persistant
# --------------------------------------------------------------------------- #
def dossier_config(app):
    """Dossier où l'appli range sa config, par convention de chaque OS.

    Windows : %APPDATA%\\<app> — inchangé. Linux : $XDG_CONFIG_HOME/<app> ou
    ~/.config/<app>. macOS : ~/Library/Application Support/<app>.

    Corrige un vrai piège : le code d'origine faisait
    `os.environ.get("APPDATA", ".")` — or APPDATA est ABSENT sous Linux, donc
    la config atterrissait dans le dossier courant (là où l'appli est lancée),
    éparpillée et perdue au prochain lancement depuis un autre dossier."""
    if EST_WINDOWS:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif EST_MAC:
        base = os.path.join(os.path.expanduser("~"), "Library",
                            "Application Support")
    else:
        base = (os.environ.get("XDG_CONFIG_HOME")
                or os.path.join(os.path.expanduser("~"), ".config"))
    return os.path.join(base, app)


# --------------------------------------------------------------------------- #
# Détection du jeu sous Linux (Wine/Proton)
# --------------------------------------------------------------------------- #
# Côté Windows, le launcher se déclare via %APPDATA% et le registre
# (voir compagnon._pistes_launcher). Rien de tout ça n'existe sous Linux : le
# jeu vit DANS un prefixe Wine/Proton, sous <prefixe>/drive_c/…  On interroge
# donc les gestionnaires de prefixes courants, puis on balaie.

# Racines où les runners Linux posent leurs prefixes. Chacun contient un
# sous-dossier par jeu, lui-même contenant un drive_c/.
_RACINES_PREFIXES = (
    "~/Games",                                     # Faugus (défaut), Lutris
    "~/Faugus",                                    # Faugus (autre défaut vu)
    "~/Jeux",
    "~/.local/share/umu",                          # umu-launcher direct
    "~/.steam/steam/steamapps/compatdata",         # Steam Proton
    "~/.local/share/Steam/steamapps/compatdata",
    "~/Games/Heroic/Prefixes",                     # Heroic
    "~/.var/app/com.usebottles.bottles/data/bottles/bottles",  # Bottles flatpak
)


def _pistes_faugus():
    """Faugus range ses jeux dans ~/.config/faugus-launcher/games.json, avec
    pour chaque entrée le `prefix` (racine du prefixe Proton) et le `path` de
    l'exe lancé. C'est la source la PLUS fiable sous Linux — l'équivalent exact
    du registre / de la config Electron côté Windows."""
    fichier = os.path.expanduser("~/.config/faugus-launcher/games.json")
    pistes = []
    try:
        with open(fichier, encoding="utf-8") as f:
            jeux = json.load(f)
    except (OSError, ValueError):
        return pistes
    for jeu in jeux if isinstance(jeux, list) else ():
        blob = " ".join(str(jeu.get(k, "")) for k in
                        ("gameid", "title", "path", "prefix")).lower()
        if "ascension" not in blob and "wow" not in blob:
            continue
        chemin = jeu.get("path") or ""
        if chemin:                       # dossier du launcher (…/resources/… à côté)
            pistes.append(os.path.dirname(chemin))
        prefixe = jeu.get("prefix") or ""
        if prefixe:                      # le prefixe entier, à balayer
            pistes.append(prefixe)
    return pistes


def _scanner_prefixe(drive_c):
    """Dans un prefixe (son drive_c/), trouve le(s) dossier(s) client Ascension
    — ceux qui contiennent Ascension.exe. On vise en priorité la disposition
    du launcher officiel (Program Files/Ascension Launcher/resources/
    ascension-live), puis on balaie prudemment sur quelques niveaux."""
    resultats = []
    canon = os.path.join(drive_c, "Program Files", "Ascension Launcher",
                         "resources", "ascension-live")
    if os.path.isdir(canon):
        resultats.append(canon)
    for motif in ("*/ascension-live",
                  "*/*/ascension-live",
                  "*/*/*/ascension-live",
                  "*/*/*/*/ascension-live"):
        resultats += glob.glob(os.path.join(drive_c, motif))
    return resultats


def _sous_dossiers(racine, limite=300):
    try:
        noms = sorted(os.listdir(racine))[:limite]
    except OSError:
        return []
    return [os.path.join(racine, n) for n in noms
            if os.path.isdir(os.path.join(racine, n))]


def pistes_jeu_linux():
    """Dossiers CANDIDATS à tester comme racine du jeu, sous Linux. Ne valide
    rien (c'est compagnon.chercher_jeu qui applique racine_jeu dessus) : on se
    contente de proposer, du plus fiable (Faugus) au plus large (balayage des
    prefixes connus). No-op — liste vide — hors Linux."""
    if not EST_LINUX:
        return []
    pistes = list(_pistes_faugus())
    for modele in _RACINES_PREFIXES:
        racine = os.path.expanduser(modele)
        if not os.path.isdir(racine):
            continue
        # La racine peut être elle-même un prefixe, ou contenir des prefixes.
        for prefixe in [racine] + _sous_dossiers(racine):
            drive_c = os.path.join(prefixe, "drive_c")
            if os.path.isdir(drive_c):
                pistes += _scanner_prefixe(drive_c)
    vus, propres = set(), []
    for p in pistes:
        if p and p not in vus:
            vus.add(p)
            propres.append(p)
    return propres


# --------------------------------------------------------------------------- #
# Lancer un fichier / le jeu
# --------------------------------------------------------------------------- #
def _which(nom):
    from shutil import which
    return which(nom)


def _essayer(cmd, env=None):
    try:
        subprocess.Popen(cmd, env=env,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


def prefixe_de(chemin):
    """Racine du prefixe Wine/Proton contenant `chemin` (le dossier PARENT de
    drive_c), ou None. Sert de WINEPREFIX pour lancer un exe via umu/wine.
    None sous Windows / hors prefixe."""
    if not chemin or EST_WINDOWS:
        return None
    p = os.path.abspath(chemin)
    while True:
        if os.path.isdir(os.path.join(p, "drive_c")):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def lancer(chemin, prefixe_hint=None):
    """Lance un fichier comme le ferait un double-clic. Renvoie True si le
    lancement a pu être tenté.

    Windows : os.startfile — inchangé. Linux : un document via xdg-open ; un
    .exe via le runner Proton/Wine. Nuance importante : lancer proprement le
    CLIENT de jeu sous Linux demanderait de reconstituer l'invocation Proton
    exacte (umu-run + WINEPREFIX + version de Proton précise) — fragile et
    propre à chaque runner. On privilégie donc, pour un .exe, d'ouvrir le
    lanceur Faugus (qui, lui, connaît le bon prefixe/Proton) ; à défaut on
    tente wine. Le confort « lancer le jeu » reste secondaire pour un outil de
    traduction : l'essentiel est de ne jamais planter."""
    if EST_WINDOWS:
        try:
            os.startfile(chemin)                   # comportement d'origine…
            return True
        except OSError:                            # …y compris son échec géré
            return False
    if not chemin or not os.path.exists(chemin):
        return False
    if not chemin.lower().endswith(".exe"):
        return _essayer(["xdg-open", chemin])
    faugus = _which("faugus-launcher")
    if faugus:
        return _essayer([faugus])
    umu = os.path.expanduser("~/.local/share/faugus-launcher/umu-run")
    if os.path.isfile(umu) and prefixe_hint:
        return _essayer([umu, chemin],
                        env=dict(os.environ, WINEPREFIX=prefixe_hint))
    wine = _which("wine")
    if wine:
        return _essayer([wine, chemin])
    return False
