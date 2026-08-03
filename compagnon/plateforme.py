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
import shutil
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
    éparpillée et perdue au prochain lancement depuis un autre dossier.

    Le repli sur "." vient de la version de Dan (programme 23) et couvre un cas
    que celle-ci ne voyait pas : `expanduser` rend "~" TEL QUEL quand il n'a
    pas su résoudre le foyer (ni HOME, ni entrée passwd — cela arrive dans un
    service ou un conteneur). Sans lui, on fabriquerait un dossier réellement
    nommé « ~ » à l'endroit d'où l'application a été lancée."""
    maison = os.path.expanduser("~")
    if maison == "~":                       # foyer non résolu
        maison = None
    if EST_WINDOWS:
        base = os.environ.get("APPDATA") or maison or "."
    elif EST_MAC:
        base = (os.path.join(maison, "Library", "Application Support")
                if maison else ".")
    else:
        base = (os.environ.get("XDG_CONFIG_HOME")
                or (os.path.join(maison, ".config") if maison else "."))
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


# --------------------------------------------------------------------------- #
# Mise à jour de l'application elle-même
# --------------------------------------------------------------------------- #
# La release publie DEUX applications : l'exe Windows et le binaire Linux
# construit par le workflow Actions. Sans la résolution ci-dessous, le Hub
# cherche « AscensionFR_Compagnon.exe » quelle que soit la plateforme — donc
# un joueur Linux se voit proposer, et télécharger, un programme Windows.
ASSET_APPLICATION_LINUX = "AscensionFR_Hub-linux-x86_64"


def nom_asset_application(nom_windows):
    """Nom de l'asset de release qui contient L'APPLICATION pour cette
    plateforme. Sous Windows, rend exactement le nom d'origine — le
    comportement historique est strictement conservé."""
    if EST_LINUX:
        return ASSET_APPLICATION_LINUX
    return nom_windows


def suffixe_application():
    """Suffixe du fichier temporaire de téléchargement. Il n'est pas
    cosmétique : verifier_telechargement s'en sert pour choisir le contrôle
    de FORME (« ce fichier est-il vraiment un programme, ou une page d'erreur
    servie à sa place ? »). Un binaire Linux n'est pas un .exe et ne commence
    pas par MZ, d'où un suffixe distinct plutôt qu'un contrôle désactivé."""
    return ".bin" if EST_LINUX else ".exe"


def peut_remplacer_sur_place():
    """Ce système sait-il échanger le binaire de l'application PENDANT qu'elle
    tourne ?

    C'est une question de SYSTÈME, pas de politique : elle dit ce que la
    machine sait faire, pas ce que l'application doit proposer au joueur. La
    décision, elle, appartient à `compagnon.remplacement_possible()`, qui
    interroge cette fonction — d'où deux noms distincts pour deux questions
    distinctes.

    Non hors Linux (Windows a son relais, qu'on ne touche pas), et non quand
    on tourne depuis les sources : `sys.executable` désigne alors
    l'interpréteur, et on écraserait /usr/bin/python3. Dans ce dernier cas
    l'appelant doit dire au joueur de mettre à jour son dépôt."""
    return EST_LINUX and bool(getattr(sys, "frozen", False))


def remplacer_application(nouveau, cible):
    """Installe `nouveau` à la place de `cible`, puis relance l'application.

    Ne rend la main QUE si quelque chose a échoué (voir la relance, en fin de
    fonction) ; lève alors une exception au message lisible.

    Pourquoi c'est plus court que le relais Windows, et pas moins sûr :
    Windows verrouille l'exécutable d'un processus en cours, d'où le script
    relais qui attend la fermeture, échange les fichiers et relance. Sous
    Linux un processus tient son INODE, pas son chemin : on peut remplacer le
    fichier pendant qu'il tourne, le processus vivant n'est pas dérangé et le
    lancement suivant prend la nouvelle version.

    Les quatre pièges traités, dans l'ordre où ils mordent :

    1. `os.replace` n'est atomique que SUR LE MÊME SYSTÈME DE FICHIERS. Le
       téléchargement vit dans /tmp, qui est très souvent une partition
       distincte (tmpfs, ou /home chiffré à part) — l'échange direct
       échouerait par EXDEV. On amène donc d'abord le fichier à côté de sa
       cible, seule opération qui a le droit d'être lente.

    2. Un fichier de `tempfile.mkstemp` naît en 0600 : SANS DROIT
       D'EXÉCUTION. Remplacer le binaire sans rétablir ses droits produit une
       mise à jour qui « réussit » et une application qui ne démarre plus
       jamais. On recopie donc les droits de l'ancien binaire.

    3. Il ne doit exister AUCUN instant sans application sur le disque —
       c'est le défaut corrigé côté Windows, et il serait absurde de le
       réintroduire ici. D'où un lien dur vers l'ancien binaire (instantané,
       ne copie pas les 39 Mo) AVANT l'unique remplacement atomique. Si les
       liens durs sont refusés (certains montages FUSE), on recopie.

    4. La nouvelle version peut être cassée. `.ancien` reste sur le disque :
       le joueur récupère son application d'un simple renommage, et la mise à
       jour suivante l'écrase de toute façon.
    """
    if not peut_remplacer_sur_place():
        raise RuntimeError(
            "cette copie n'est pas un programme autonome : mets-la à jour "
            "avec « git pull » dans le dossier du dépôt.")
    cible = os.path.realpath(cible)
    dossier = os.path.dirname(cible)
    if not os.access(dossier, os.W_OK):
        raise PermissionError(
            "le dossier « %s » est en lecture seule : déplace l'application "
            "dans un dossier qui t'appartient, ou télécharge la nouvelle "
            "version à la main." % dossier)

    # 1. amener le nouveau fichier sur le système de fichiers de la cible
    provisoire = os.path.join(dossier, "." + os.path.basename(cible) + ".neuf")
    shutil.move(nouveau, provisoire)
    try:
        # 2. droits d'exécution — repris de l'ancien binaire
        os.chmod(provisoire, os.stat(cible).st_mode & 0o7777)

        # 3. filet AVANT l'échange, jamais après
        ancien = cible + ".ancien"
        if os.path.exists(ancien):
            os.remove(ancien)
        try:
            os.link(cible, ancien)
        except OSError:
            shutil.copy2(cible, ancien)

        os.replace(provisoire, cible)      # l'unique instant qui compte
    except BaseException:
        try:
            os.remove(provisoire)
        except OSError:
            pass
        raise

    _relancer(cible, ancien)


def _relancer(cible, ancien):
    """Remplace le processus courant par la nouvelle application.

    Le nettoyage d'environnement ci-dessous n'est pas une précaution de
    principe : SANS LUI, LA NOUVELLE VERSION NE DÉMARRE PAS. Constaté à
    l'essai, sur de vrais binaires empaquetés.

    Une application empaquetée en un seul fichier, c'est en réalité DEUX
    processus : un lanceur, qui déballe le contenu dans un dossier temporaire,
    puis l'application elle-même. Le lanceur transmet au second, par variables
    d'environnement (_PYI_APPLICATION_HOME_DIR, _PYI_PARENT_PROCESS_LEVEL…),
    l'endroit du déballage et le fait qu'il a déjà eu lieu.

    Si on relance la NOUVELLE version en lui laissant ces variables, elle se
    croit l'ancienne : elle va chercher ses fichiers dans le déballage de la
    précédente, et meurt sur « Failed to load Python shared library ». On les
    retire donc pour qu'elle se déballe normalement, comme à un lancement
    ordinaire.

    Corollaire, dans l'autre sens : il ne faut PAS effacer soi-même le dossier
    de déballage. Le lanceur, lui, n'est pas remplacé par os.execve — il reste
    vivant et fait le ménage quand l'application se termine.

    os.execve ne revient jamais quand il réussit : la suite de cette fonction
    n'est atteinte QUE si la nouvelle version refuse de démarrer. C'est donc
    exactement là qu'il faut remettre l'ancienne."""
    env = {cle: valeur for cle, valeur in os.environ.items()
           if not cle.startswith("_PYI") and not cle.startswith("_MEIPASS")}
    try:
        os.execve(cible, [cible] + sys.argv[1:], env)
    except OSError as err:
        try:
            os.replace(ancien, cible)      # la nouvelle ne démarre pas
        except OSError:
            pass
        raise RuntimeError(
            "la nouvelle version n'a pas pu être lancée (%s). L'ancienne a "
            "été remise en place — relance l'application." % err)
