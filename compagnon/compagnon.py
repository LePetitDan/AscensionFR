# -*- coding: utf-8 -*-
"""
Ascension FR — Compagnon
========================
Petite application OPTIONNELLE qui accompagne l'addon de traduction française
de Project Ascension (https://github.com/LePetitDan/AscensionFR) :

  1. vérifie si une nouvelle version de la traduction existe et l'installe
     en un clic (téléchargée depuis les releases GitHub officielles) ;
  2. prépare ton rapport de contribution (textes rencontrés en anglais,
     notés par l'addon dans ta sauvegarde) et l'envoie aider la traduction —
     accompagné des textes anglais que ton jeu garde en cache (quêtes, PNJ,
     objets croisés en jouant), la matière première des traducteurs.

TRANSPARENCE : ce fichier est TOUT le programme. Il ne lit que le dossier du
jeu, n'écrit que les fichiers de l'addon, et ne contacte que api.github.com /
github.com (téléchargement des versions) et le salon Discord du projet (envoi
du rapport, uniquement quand TU cliques). Tout ce qui part est du texte DU
JEU — jamais de pseudo, de conversation ni de fichier personnel.
"""
import ctypes
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import webbrowser
import zipfile

import customtkinter as ctk

# parser_wdb (lecture des caches WDB du client) vit dans traduction\outils et
# est embarqué tel quel dans l'exe (voir AscensionFR_Compagnon.spec). En
# développement, on va le chercher dans le dépôt. Sans lui, le rapport part
# simplement sans la pièce jointe des caches.
try:
    import parser_wdb
except ImportError:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "outils"))
    try:
        import parser_wdb
    except ImportError:
        parser_wdb = None

DEPOT = "LePetitDan/AscensionFR"
API_RELEASE = "https://api.github.com/repos/" + DEPOT + "/releases/latest"
PAGE_RELEASES = "https://github.com/" + DEPOT + "/releases"
# Version de CETTE application. DOCTRINE (Dan, 28/07/2026) : une mise à jour
# = UN numéro — VERSION_COMPAGNON, le « ## Version: » du .toc vivant et le tag
# de la release sont TOUJOURS égaux, même quand seul le Hub change. C'est la
# dissociation (Hub 3.3.1 sur addon 3.3.0) qui a créé la boucle de mise à jour
# infinie du 25-28/07 : le Hub comparait le .toc au tag et proposait la mise à
# jour pour toujours. verifier_tout.py et publier_github.py refusent tout
# écart, sans option pour passer outre.
VERSION_COMPAGNON = "3.5.0"

# Salon des rapports : URL du webhook Discord (fournie par le mainteneur).
# VIDE -> le bouton « Envoyer » n'existe pas, seul « Copier » reste (aucun
# envoi réseau). Quand il est renseigné, « Envoyer » poste le rapport en pièce
# jointe .txt dans le salon — le rapport ne contient QUE des textes du jeu et
# des numéros de sorts/objets, jamais d'information personnelle.
def _lire_webhook():
    """L'URL du webhook des rapports — HORS du code (programme 33, bloc 0).

    Une URL de webhook EST le droit d'écrire dans le salon : elle ne doit
    plus jamais entrer dans un fichier suivi par git (elle y était en dur, et
    le dépôt devient poussable). Trois sources, dans l'ordre :
      1. la variable d'environnement ASCENSIONFR_WEBHOOK (build, cloud, dev) ;
      2. un fichier EMBARQUÉ dans l'exe : assets/webhook.local.txt, écrit au
         build depuis cette même variable par outils/injecter_webhook.py
         (gitignoré via *.local.txt) — c'est lui que lit l'exe distribué ;
      3. rien -> "" : « Envoyer » disparaît, « Copier » reste (aucun réseau).
    """
    valeur = os.environ.get("ASCENSIONFR_WEBHOOK", "").strip()
    if valeur:
        return valeur
    base = sys._MEIPASS if getattr(sys, "frozen", False) \
        else os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base, "assets", "webhook.local.txt"),
                  encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


WEBHOOK_RAPPORTS = _lire_webhook()
DISCORD = "https://discord.gg/kFJGDJbeay"
# Soutien au créateur. La traduction reste gratuite : le bouton est volontaire-
# ment secondaire (contour seul) pour ne pas concurrencer l'envoi de rapport.
SOUTIEN = "https://buymeacoffee.com/lepetitdan"
# Réseaux du créateur : de simples liens texte, jamais des boutons — ce n'est
# pas l'objet de l'application, ils ne doivent attirer l'œil que si on les
# cherche.
TWITCH = "https://www.twitch.tv/lepetitdan"
YOUTUBE = "https://www.youtube.com/@LePetitDan"

# Dépôt SÉPARÉ des voix françaises (2.1) : JAMAIS dans le dépôt principal —
# si une réclamation de droits le fait retirer, l'addon et ses mises à jour
# ne doivent pas pouvoir être touchés.
DEPOT_VOIX = "LePetitDan/AscensionFR-Voix"
VOIX_URL = ("https://github.com/" + DEPOT_VOIX
            + "/releases/latest/download/AscensionFR_Voix.zip")
# Fichier-témoin : présent dans le dossier du jeu = voix déjà installées.
# 1.1 (22/07/2026) : le témoin est un fichier NOUVEAU de la 1.1 (les 4 748
# voix récupérées — Sylvanas, boss...) : chez un joueur resté en 1.0, le
# bouton redevient « à télécharger » et le zip cumulatif complète tout.
TEMOIN_VOIX = os.path.join("Sound", "CREATURE", "SylvanasWindrunner",
                           "Sylvanas_WoundCritical01.wav")
ZIP_ATTENDU = "AscensionFR_manuel.zip"
EXE_ATTENDU = "AscensionFR_Compagnon.exe"
UA = {"User-Agent": "AscensionFR-Compagnon"}

# Palette « launcher moderne » : sombre, plat, une seule touche d'or — le
# style choisi par Dan sur maquettes (18/07/2026). L'or vient du logo mais ne
# sert que d'accent (bouton principal, chevron).
FOND = "#0e1013"            # fenêtre
PANNEAU = "#16191d"         # cadres
LISERE = "#23272d"          # bordure discrète des cadres
ACCENT = "#e8c25a"          # l'or du logo — bouton principal, petites touches
ACCENT_SURVOL = "#d9b44e"
ENCRE_ACCENT = "#15130c"    # texte sombre posé sur l'or
TEXTE = "#eceff3"           # texte courant
DISCRET = "#8b929c"         # texte secondaire, en-têtes de section
FANTOME_BORD = "#3a4048"    # boutons secondaires (contour seul)
FANTOME_SURVOL = "#1d2126"
VERT = "#2fb46a"
ORANGE = "#e8a33d"
ROUGE = "#e05252"

def _dossier_config():
    """Où vivent la configuration et les traces d'échec.

    Sous Windows : %APPDATA%\\AscensionFR — inchangé, au caractère près, pour
    les 274 installations existantes.

    Ailleurs (Linux, depuis le programme 21) : `os.environ.get("APPDATA", ".")`
    rendait "." — la configuration atterrissait donc dans le dossier COURANT,
    c'est-à-dire à un endroit différent selon la façon dont le joueur a lancé
    le programme (double-clic, terminal, raccourci). Un joueur qui choisissait
    son dossier de jeu le reperdait au lancement suivant, et une trace d'erreur
    écrite là serait introuvable. On suit la convention du système."""
    base = os.environ.get("APPDATA")
    if base:
        return os.path.join(base, "AscensionFR")
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base:
        maison = os.path.expanduser("~")
        # expanduser rend "~" tel quel quand il n'a pas su : on ne fabrique
        # pas un dossier nommé « ~ », on retombe sur le dossier courant.
        base = os.path.join(maison, ".config") if maison != "~" else "."
    return os.path.join(base, "AscensionFR")


CONFIG_DIR = _dossier_config()
CONFIG = os.path.join(CONFIG_DIR, "compagnon.json")

# --------------------------------------------------------------------------- #
# Journal d'incident — « ça a raté, et voilà où c'est écrit »
# --------------------------------------------------------------------------- #
# POURQUOI (programme 23, 02/08/2026). Mesuré, pas supposé : dans un exe figé
# en mode fenêtré, `sys.stdout` ET `sys.stderr` valent None. Tkinter attrape
# toute exception de rappel et l'envoie à `traceback.print_exception`, qui
# écrit dans le vide sans rien lever. Résultat : un bouton du Hub qui plante
# ne fait RIEN — pas un message, pas une trace, et l'application se ferme
# normalement. C'est vrai sous Linux ET sous Windows.
#
# ⚠️ CE QU'UNE TRACE NE DOIT JAMAIS PORTER. Un journal d'erreur finit collé
# sur le Discord par un joueur qui veut aider. Il est donc écrit en partant de
# là : `_anonymiser` retire le webhook, le nom d'utilisateur du système, le
# nom de compte WoW et le dossier temporaire du paquet. Rien n'y entre qui ne
# puisse être lu par n'importe qui.
FICHIER_INCIDENT = "AscensionFR_incident.log"
TAILLE_INCIDENT_MAX = 200_000        # au-delà, on repart de zéro


def dossier_journal():
    """Le dossier où poser une trace d'échec.

    Le projet en a DÉJÀ un : le relais de mise à jour écrit
    `AscensionFR_maj_echec.log` À CÔTÉ DU PROGRAMME (voir
    `lancer_remplacement`). On reprend le même endroit — c'est là que le
    joueur qui vient de double-cliquer ira regarder — avec CONFIG_DIR en
    repli quand ce dossier n'est pas inscriptible (Program Files, /opt, un
    binaire posé sur une clé en lecture seule)."""
    if getattr(sys, "frozen", False):
        candidats = [os.path.dirname(os.path.abspath(sys.executable))]
    else:
        candidats = [os.path.dirname(os.path.abspath(__file__))]
    candidats.append(CONFIG_DIR)
    for dossier in candidats:
        try:
            os.makedirs(dossier, exist_ok=True)
            temoin = os.path.join(dossier, ".afr_ecriture")
            with open(temoin, "w") as f:
                f.write("")
            os.remove(temoin)
            return dossier
        except OSError:
            continue
    return None


_RE_WEBHOOK = re.compile(
    r"https?://(?:\w+\.)?discord(?:app)?\.com/api/webhooks/\S*",
    re.IGNORECASE)
# …\WTF\Account\<COMPTE>\… : le nom de compte WoW EST un identifiant de joueur.
_RE_COMPTE_WOW = re.compile(r"(?i)(WTF[\\/]+Account[\\/]+)[^\\/\r\n\"']+")


def _anonymiser(texte):
    """Retire d'une trace tout ce qui ne doit jamais voyager.

    Ordre volontaire : du plus long au plus court, sinon un remplacement
    court coupe un chemin en deux et le suivant ne reconnaît plus rien
    (le piège des passes de vocabulaire, appliqué ici)."""
    if not texte:
        return texte
    if WEBHOOK_RAPPORTS:
        texte = texte.replace(WEBHOOK_RAPPORTS, "<webhook>")
    # …et tout autre webhook Discord, y compris un que nous n'aurions pas posé.
    texte = _RE_WEBHOOK.sub("<webhook>", texte)
    texte = _RE_COMPTE_WOW.sub(r"\1<compte>", texte)
    # Le dossier temporaire du paquet PyInstaller contient le nom de session.
    paquet = getattr(sys, "_MEIPASS", "")
    if paquet:
        texte = texte.replace(paquet, "<paquet>")
    maison = os.path.expanduser("~")
    if maison and maison != "~":
        texte = texte.replace(maison, "<maison>")
    # Le nom d'utilisateur tout seul (« KeyError: 'Jerome' », un chemin écrit
    # d'une autre façon). Pas de \b : après un souligné il ne voit aucune
    # frontière et raterait en silence — le piège déjà payé au programme 6.
    for cle in ("USERNAME", "USER", "LOGNAME"):
        nom = os.environ.get(cle, "")
        if len(nom) >= 3:
            texte = re.sub(re.escape(nom), "<joueur>", texte,
                           flags=re.IGNORECASE)
    return texte


def journal_incident(ou, trace=None):
    """Écrit UNE trace d'échec et rend le chemin du fichier (None si même ça
    a raté — on ne plante jamais dans le gestionnaire de plantage).

    `ou`    : ce que le joueur était en train de faire (« Lancer le jeu »).
    `trace` : le texte du traceback ; à défaut, celui de l'exception courante.
    """
    try:
        if trace is None:
            trace = traceback.format_exc()
        dossier = dossier_journal()
        if not dossier:
            return None
        chemin = os.path.join(dossier, FICHIER_INCIDENT)
        try:
            if os.path.getsize(chemin) > TAILLE_INCIDENT_MAX:
                os.remove(chemin)      # une boucle de plantages ne remplit
        except OSError:                # pas le disque du joueur
            pass
        bloc = ("\n" + "=" * 70 + "\n"
                + "[%s] Hub %s — %s\n"
                % (time.strftime("%d/%m/%Y %H:%M:%S"), VERSION_COMPAGNON,
                   platform.platform())
                + "Pendant : %s\n" % ou
                + _anonymiser(trace).rstrip() + "\n")
        with open(chemin, "a", encoding="utf-8", errors="replace") as f:
            f.write(bloc)
        return chemin
    except Exception:
        return None


def ressource(nom):
    """Chemin d'un fichier embarqué (assets/), y compris une fois figé en .exe
    par PyInstaller (les fichiers sont alors déballés dans sys._MEIPASS)."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", nom)


# --------------------------------------------------------------------------- #
# Dossier du jeu
# --------------------------------------------------------------------------- #
def jeu_valide(chemin):
    """Un dossier de jeu Ascension contient un dossier Interface."""
    return bool(chemin) and os.path.isdir(os.path.join(chemin, "Interface"))


# --------------------------------------------------------------------------- #
# La RACINE du jeu — et pourquoi « il y a un dossier Interface » ne suffit pas
# --------------------------------------------------------------------------- #
# Douze joueurs en neuf jours ont installé au mauvais endroit (veille Discord
# du 18 au 26/07/2026). Le test historique — « ce dossier contient-il un
# dossier Interface ? » — accepte au moins trois faux positifs sur une
# installation PROPRE : la vraie racine, mais aussi Data\enUS (qui contient
# Data\enUS\Interface\Cinematics) et Sound (qui contient Sound\Interface\NPC).
#
# Le piège est pire quand le joueur a déjà mal extrait le zip officiel à la
# main : sa racine étant « Interface\AddOns\… », l'extraction dans
# Interface\AddOns fabrique Interface\AddOns\Interface — et à partir de là
# Interface\AddOns passe le test POUR TOUJOURS. Le Hub y installe, y relit un
# .toc bien réel, et affiche « tu es à jour » pendant que le jeu, lui, ne
# charge rien. Un faux « tout est bon » coûte plus cher que pas de test.
#
# Ces marqueurs-là, eux, n'existent QU'À la racine (vérifié par recherche
# récursive sur une installation réelle) : Data\ (les MPQ), Ascension.exe,
# Wow.ini, WTF\.
MARQUEURS_RACINE = ("Ascension.exe", "Wow.exe", "Wow.ini")

# Noms de dossiers dans lesquels on n'installe JAMAIS : ils sont forcément
# SOUS la racine, jamais la racine elle-même.
NOMS_TROP_BAS = ("addons", "interface", "wtf", "data", "cache", "sound",
                 "sound_off", "logs", "errors")


def racine_jeu(chemin):
    """Vrai si `chemin` est la RACINE du jeu (et pas un sous-dossier qui
    contient par hasard un dossier « Interface »).

    Deux témoins suffisent et se complètent : le dossier Data (les archives
    MPQ du client, toujours présent) ou l'un des exécutables/ini de la racine
    (présents même sur une copie sans Data). WTF n'est pas exigé : il n'existe
    qu'après le premier lancement du jeu."""
    if not chemin or not os.path.isdir(os.path.join(chemin, "Interface")):
        return False
    if os.path.isdir(os.path.join(chemin, "Data")):
        return True
    return any(os.path.isfile(os.path.join(chemin, m))
               for m in MARQUEURS_RACINE)


def corriger_dossier_jeu(chemin):
    """Rend (racine, note) pour le dossier que le joueur vient de désigner.

    - racine : le dossier où installer, ou None si on ne sait pas ;
    - note   : None si le choix était déjà bon, sinon une phrase à AFFICHER
      (soit « j'ai corrigé tout seul », soit « voilà pourquoi je refuse »).

    On remonte (le joueur a cliqué trop bas : Interface, Interface\\AddOns,
    WTF…) et on descend (il a cliqué sur le dossier du launcher). Ce que le
    Compagnon v2 savait déjà faire vers le bas, le Hub ne le faisait ni dans
    un sens ni dans l'autre."""
    if not chemin:
        return None, "Aucun dossier choisi."
    chemin = os.path.normpath(chemin).rstrip("\\/")
    if racine_jeu(chemin):
        return chemin, None

    # 1. Descendre : le joueur a désigné le dossier du launcher.
    for fin in FINS_JEU:
        candidat = os.path.join(chemin, *fin)
        if racine_jeu(candidat):
            return candidat, ("Ce dossier contient le jeu un cran plus bas — "
                              "le Hub a corrigé tout seul : " + candidat)

    # 2. Remonter : le joueur est descendu trop bas (le cas des 12 joueurs).
    #    On ne remonte que tant qu'on traverse des dossiers du jeu, et au plus
    #    quatre crans (Interface\AddOns\Interface\AddOns, le pire vu).
    montee, courant = [], chemin
    for _ in range(4):
        parent = os.path.dirname(courant)
        if not parent or parent == courant:
            break
        montee.append(os.path.basename(courant))
        courant = parent
        if racine_jeu(courant):
            return courant, ("Tu étais descendu trop bas (dans « %s »). "
                             "Le dossier du jeu, c'est celui-ci : %s"
                             % ("\\".join(reversed(montee)), courant))

    # 3. Refus motivé : mieux vaut ne rien faire qu'installer à côté.
    bas = os.path.basename(chemin).lower()
    if bas in NOMS_TROP_BAS:
        return None, ("« %s » est un dossier À L'INTÉRIEUR du jeu, pas le "
                      "dossier du jeu. Remonte jusqu'à celui qui contient "
                      "Ascension.exe (souvent …\\resources\\ascension-live)."
                      % os.path.basename(chemin))
    return None, ("Ce dossier n'est pas celui du jeu : il faudrait y trouver "
                  "Ascension.exe et les dossiers Data et Interface. "
                  "Cherche …\\resources\\ascension-live.")


def installations_imbriquees(jeu):
    """Les traductions posées au mauvais endroit qui traînent SOUS la racine.

    Une extraction manuelle du zip dans Interface\\AddOns laisse un
    Interface\\AddOns\\Interface\\AddOns\\AscensionFR que le jeu ne lira
    jamais — mais qui suffit à faire croire au joueur qu'il a installé. Rend
    la liste des dossiers fautifs (vide = rien à signaler)."""
    if not jeu:
        return []
    trouves = []
    for sous in (os.path.join("Interface", "AddOns", "Interface"),
                 os.path.join("Interface", "Interface"),
                 os.path.join("Interface", "AddOns", "AddOns")):
        chemin = os.path.join(jeu, sous)
        if os.path.isdir(chemin):
            trouves.append(chemin)
    return trouves


def _que_du_notre(chemin):
    """Le sous-arbre ne contient-il QUE des dossiers à nous ?

    Avant d'effacer récursivement quoi que ce soit, on regarde dedans. Un
    joueur a très bien pu, dans le même geste maladroit, extraire d'AUTRES
    addons au même endroit — les siens ne doivent pas partir avec les
    nôtres. Un fichier ou un dossier qu'on ne reconnaît pas suffit à dire
    non ; le contrôle bascule alors en « à faire toi-même », avec la liste.
    C'est la règle de la maison : dans le doute, on ne supprime pas."""
    for dossier, sous_dossiers, fichiers in os.walk(chemin):
        for nom in list(sous_dossiers) + fichiers:
            court = nom.lower()
            if court in ("interface", "addons", "ptrxml"):
                continue
            if court.startswith("ascensionfr"):
                continue
            return False
    return True



# Deux dispositions vues en vrai : resources\ascension-live (ancienne) et
# resources\client (celle du launcher actuel — vu chez un joueur).
FINS_JEU = (("resources", "ascension-live"),
            ("resources", "client"),
            ("ascension-live",))

# Dossiers système à ne jamais fouiller : rien n'y sera, et les parcourir
# coûte des secondes (et déclenche parfois l'antivirus).
IGNORES = {"windows", "$recycle.bin", "system volume information",
           "programdata", "recovery", "perflogs", "msocache",
           "documents and settings", "onedrivetemp"}


def _pistes_launcher():
    """Le launcher Ascension sait où il a installé le jeu. On le lui demande
    plutôt que de deviner : c'est la seule source FIABLE.

    Ajouté le 24/07/2026 après les retours « le Hub ne trouve pas mon
    dossier ». L'ancienne recherche ne regardait que les disques C à H et un
    SEUL niveau de profondeur : elle trouvait D:\\resources\\ascension-live
    mais ratait D:\\Jeux\\Ascension\\resources\\… — l'installation la plus
    courante."""
    pistes = []
    # 1. La configuration du launcher (Electron : %APPDATA%\Ascension Launcher)
    for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):
        if not base:
            continue
        for nom in ("Ascension Launcher", "ascension-launcher"):
            dossier = os.path.join(base, nom)
            for fichier in ("config.json", "settings.json",
                            "preferences.json"):
                chemin = os.path.join(dossier, fichier)
                try:
                    with open(chemin, encoding="utf-8", errors="replace") as f:
                        texte = f.read(200000)
                except OSError:
                    continue
                # On ne suppose RIEN de la forme du fichier : on ramasse tout
                # ce qui ressemble à un chemin Windows et on valide ensuite.
                for brut in re.findall(r'"([A-Za-z]:\\\\[^"]{3,200})"', texte):
                    pistes.append(brut.replace("\\\\", "\\"))
                for brut in re.findall(r'"([A-Za-z]:/[^"]{3,200})"', texte):
                    pistes.append(brut)
    # 2. Le registre Windows (désinstallateur du launcher)
    try:
        import winreg
        for ruche, chemin in (
                (winreg.HKEY_CURRENT_USER,
                 r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
                (winreg.HKEY_LOCAL_MACHINE,
                 r"Software\Microsoft\Windows\CurrentVersion\Uninstall")):
            try:
                cle = winreg.OpenKey(ruche, chemin)
            except OSError:
                continue
            with cle:
                for i in range(winreg.QueryInfoKey(cle)[0]):
                    try:
                        nom = winreg.EnumKey(cle, i)
                        if "ascension" not in nom.lower():
                            continue
                        with winreg.OpenKey(cle, nom) as sous:
                            for valeur in ("InstallLocation",
                                           "DisplayIcon"):
                                try:
                                    v = winreg.QueryValueEx(sous, valeur)[0]
                                except OSError:
                                    continue
                                if v:
                                    pistes.append(os.path.dirname(str(v))
                                                  if valeur == "DisplayIcon"
                                                  else str(v))
                    except OSError:
                        continue
    except Exception:
        pass                       # pas Windows, ou registre inaccessible
    return pistes


def chercher_jeu(strict=True):
    """Trouve le dossier du jeu. Trois passes, de la plus fiable à la plus
    large — on s'arrête à la première qui mord.

    `strict` (26/07/2026) : on exige la RACINE du jeu, pas « un dossier qui
    contient Interface ». Sans ça, la recherche pouvait s'arrêter sur
    Data\\enUS ou Sound — deux dossiers qui contiennent bel et bien un
    « Interface » — et le Hub installait à côté sans un mot. Si la passe
    stricte ne trouve rien, on refait un tour à l'ancienne plutôt que de
    rendre None : mieux vaut un dossier douteux (que le contrôle
    d'installation signalera) que pas de dossier du tout."""
    def essaie(base):
        """Le dossier lui-même, ou l'une des dispositions connues dessous."""
        bon = racine_jeu if strict else jeu_valide
        if bon(base):
            return base
        for fin in FINS_JEU:
            c = os.path.join(base, *fin)
            if bon(c):
                return c
        return None

    # PASSE 1 — ce que le launcher déclare lui-même.
    for piste in _pistes_launcher():
        piste = piste.rstrip("\\/")
        for base in (piste, os.path.dirname(piste)):
            trouve = base and essaie(base)
            if trouve:
                return trouve

    # PASSE 2 — les emplacements classiques, sur TOUS les disques (et plus
    # seulement C à H : un joueur avait le jeu en I:).
    racines = []
    for code in range(ord("A"), ord("Z") + 1):
        racine = chr(code) + ":\\"
        if os.path.isdir(racine):
            racines.append(racine)
    classiques = ("Ascension Launcher", "Ascension", "AscensionLauncher",
                  "Games", "Jeux", "Program Files", "Program Files (x86)")
    for racine in racines:
        for nom in classiques:
            trouve = essaie(os.path.join(racine, nom))
            if trouve:
                return trouve
            # « D:\\Jeux\\Ascension Launcher\\… » : un cran plus bas.
            for nom2 in classiques:
                trouve = essaie(os.path.join(racine, nom, nom2))
                if trouve:
                    return trouve

    # PASSE 3 — balayage sur DEUX niveaux (c'était un seul avant, d'où les
    # échecs). On saute les dossiers système et on borne le travail.
    for racine in racines:
        try:
            premiers = sorted(os.listdir(racine))[:60]
        except OSError:
            continue
        for d1 in premiers:
            if d1.lower() in IGNORES or d1.startswith("."):
                continue
            base1 = os.path.join(racine, d1)
            if not os.path.isdir(base1):
                continue
            trouve = essaie(base1)
            if trouve:
                return trouve
            try:
                seconds = sorted(os.listdir(base1))[:40]
            except OSError:
                continue
            for d2 in seconds:
                base2 = os.path.join(base1, d2)
                if not os.path.isdir(base2):
                    continue
                trouve = essaie(base2)
                if trouve:
                    return trouve
    # Rien de strict : on refait un tour à l'ancienne. Le contrôle
    # d'installation dira au joueur ce qui cloche avec ce dossier-là.
    return chercher_jeu(strict=False) if strict else None


def charger_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def sauver_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #
def version_installee(jeu):
    """Lit « ## Version: x.y » dans le .toc de l'addon. None si absent."""
    toc = os.path.join(jeu, "Interface", "AddOns", "AscensionFR",
                       "AscensionFR.toc")
    try:
        with open(toc, encoding="utf-8") as f:
            for ligne in f:
                m = re.match(r"##\s*Version:\s*([\d.]+)", ligne)
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def _contexte_ssl():
    """Contexte HTTPS tolérant aux magasins de certificats abîmés (rapport
    joueur du 22/07/2026 : CERTIFICATE_VERIFY_FAILED au téléchargement des
    voix). On fait confiance au magasin Windows (y compris l'antivirus qui
    ré-signe le HTTPS) ET au paquet certifi embarqué (magasin incomplet).
    JAMAIS de connexion non vérifiée : si les deux échouent, on échoue."""
    import ssl
    contexte = ssl.create_default_context()
    try:
        import certifi
        contexte.load_verify_locations(certifi.where())
    except Exception:
        pass                      # sans certifi, le magasin système suffit
    return contexte


CONTEXTE_SSL = _contexte_ssl()


def en_tuple(version):
    return tuple(int(x) for x in re.findall(r"\d+", version or "0"))


def derniere_release():
    """(version, url_du_zip, url_de_l_exe) de la dernière release GitHub."""
    req = urllib.request.Request(API_RELEASE, headers=UA)
    with urllib.request.urlopen(req, timeout=20,
                                context=CONTEXTE_SSL) as r:
        infos = json.load(r)
    version = (infos.get("tag_name") or "").lstrip("vV")
    url_zip, url_exe = None, None
    for asset in infos.get("assets", []):
        if asset.get("name") == ZIP_ATTENDU:
            url_zip = asset.get("browser_download_url")
        elif asset.get("name") == EXE_ATTENDU:
            url_exe = asset.get("browser_download_url")
    return version, url_zip, url_exe


def mise_a_jour_dispo(installee, derniere):
    if not derniere:
        return False
    if not installee:
        return True
    vi, vd = en_tuple(installee), en_tuple(derniere)
    # Les toutes premières versions de l'addon portaient une numérotation
    # interne (2.2, 2.3) antérieure à l'alignement sur les releases (1.4+).
    # RESSERRÉ le 20/07/2026 : l'ancienne borne « vi >= (2, 0) » aurait fait
    # proposer un RETOUR en 1.7.5 aux joueurs de la vraie 2.0 (audit).
    if (2, 2) <= vi < (3,) and vd < (2, 0):
        return True
    return vd > vi


def reference_asset(nom_asset):
    """(sha256, taille) ANNONCÉS PAR GITHUB pour cet asset, ou (None, None).

    ⚠️ C'est le cœur du contrôle d'intégrité, et le piège qu'il évite :
    une empreinte calculée sur le fichier téléchargé, comparée à une
    empreinte calculée sur le même fichier, ne prouve rien — elle se valide
    toute seule. La référence doit venir d'AILLEURS que du fichier.

    Elle vient d'ici : l'API des release assets expose un champ « digest »
    (vérifié sur notre release du 28/07 —
    « sha256:621401050e340da8bf3032a251e19e55… », qui correspond bien à
    l'empreinte réelle de l'exe publié) et un champ « size ». Ce sont des
    MÉTADONNÉES, calculées par GitHub à la réception, servies par une autre
    requête que celle du binaire.
    """
    try:
        req = urllib.request.Request(API_RELEASE, headers=UA)
        with urllib.request.urlopen(req, timeout=20,
                                    context=CONTEXTE_SSL) as r:
            infos = json.load(r)
        for asset in infos.get("assets", []):
            if asset.get("name") == nom_asset:
                digest = (asset.get("digest") or "")
                sha = digest.split("sha256:")[-1] if "sha256:" in digest \
                    else None
                return sha, asset.get("size") or None
    except Exception:
        # Pas de référence disponible : on ne bloque pas la mise à jour pour
        # autant, les contrôles de forme ci-dessous restent actifs.
        pass
    return None, None


def telecharger_fichier(url, progres=None, suffixe=".zip",
                        sha256_attendu=None, taille_attendue=None):
    """Télécharge un fichier de release dans un fichier temporaire ; rend le
    chemin. progres(fait, total) est appelé au fil de l'eau.

    CONTRÔLE D'INTÉGRITÉ (programme 9, 01/08/2026). Jusqu'ici : aucun. Une
    coupure réseau produisait un exe tronqué, qu'on installait, qui ne
    démarrait pas — et que le Hub reproposait à chaque ouverture. C'est un
    candidat sérieux pour la « mise à jour qui ne tient jamais » signalée le
    27/07.

    Trois contrôles, du moins cher au plus sûr :
      1. l'en-tête « MZ » pour un .exe — attrape un fichier vide et surtout
         une page d'erreur HTML servie à la place du binaire ;
      2. la taille annoncée par l'API — attrape le téléchargement tronqué ;
      3. l'empreinte SHA-256 annoncée par l'API — attrape le reste.

    L'empreinte est calculée AU FIL DE L'EAU : on ne relit pas 38 Mo une
    seconde fois. En cas d'échec, le fichier temporaire est supprimé (il ne
    doit pas rester un exe corrompu qui traîne) et une exception au message
    LISIBLE est levée : l'appelant l'affiche au joueur et lui propose la
    page de téléchargement. Refuser en silence recréerait la boucle qu'on
    essaie de casser.
    """
    req = urllib.request.Request(url, headers=UA)
    fd, chemin = tempfile.mkstemp(suffix=suffixe, prefix="AscensionFR_")
    empreinte = hashlib.sha256()
    debut = b""
    try:
        with urllib.request.urlopen(req, timeout=60,
                                    context=CONTEXTE_SSL) as r, \
                os.fdopen(fd, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            fait = 0
            while True:
                bloc = r.read(65536)
                if not bloc:
                    break
                if not debut:
                    debut = bloc[:2]
                f.write(bloc)
                empreinte.update(bloc)
                fait += len(bloc)
                if progres:
                    progres(fait, total)
        verifier_telechargement(chemin, suffixe, debut, empreinte.hexdigest(),
                                sha256_attendu, taille_attendue)
    except BaseException:
        try:
            os.remove(chemin)
        except OSError:
            pass
        raise
    return chemin


def verifier_telechargement(chemin, suffixe, debut, empreinte,
                            sha256_attendu, taille_attendue):
    """Lève une exception au message lisible si le fichier n'est pas celui
    qu'on attendait. Séparée pour être éprouvable sans réseau."""
    taille = os.path.getsize(chemin)
    if taille == 0:
        raise ValueError(
            "le téléchargement est vide (0 octet). La connexion a "
            "probablement été interrompue — réessaie dans un instant.")
    if suffixe == ".exe" and debut[:2] != b"MZ":
        raise ValueError(
            "le fichier téléchargé n'est pas un programme Windows. Le "
            "téléchargement a été interrompu, ou un équipement réseau a "
            "renvoyé une page d'erreur à la place — réessaie dans un "
            "instant.")
    if taille_attendue and taille != taille_attendue:
        raise ValueError(
            "le téléchargement est incomplet (%.1f Mo reçus sur %.1f Mo "
            "attendus). Réessaie dans un instant."
            % (taille / 1e6, taille_attendue / 1e6))
    if sha256_attendu and empreinte.lower() != sha256_attendu.lower():
        raise ValueError(
            "le fichier téléchargé est abîmé (son empreinte ne correspond "
            "pas à celle annoncée par GitHub). Réessaie dans un instant ; "
            "si ça recommence, télécharge-le à la main depuis la page des "
            "versions.")


def installer_zip(chemin_zip, jeu):
    """Extrait le zip (structure Interface\\...) par-dessus le dossier du jeu."""
    with zipfile.ZipFile(chemin_zip) as z:
        z.extractall(jeu)
    os.remove(chemin_zip)


def remplacement_possible():
    """L'auto-mise à jour de l'APPLICATION est-elle praticable ici ?

    ⚠️ AJOUT URGENT DU PROGRAMME 23 (02/08/2026), trouvé par Tetardtek.
    Deux raisons, et une seule suffirait :

      1. le relais de remplacement est un **.bat lancé par cmd.exe**
         (`lancer_remplacement` ci-dessous) — il n'existe pas ailleurs ;
      2. l'asset publié sous le nom `EXE_ATTENDU` est un **exécutable
         Windows**, et `derniere_release()` ne sait pas choisir par
         plateforme : sous Linux, `url_exe` désignait donc l'exe Windows.

    Le défaut dormait : la 3.4.1 étant la dernière publiée, aucun Hub n'était
    « en retard ». Il se serait armé à la PREMIÈRE publication suivante — un
    joueur Linux se serait vu proposer la mise à jour, aurait téléchargé ~40 Mo
    d'exe Windows, et le relais l'aurait passé à `cmd`. Aujourd'hui ça échoue
    par CHANCE (`creationflags` n'existe pas hors Windows et lève un
    ValueError, rattrapé plus haut) — la chance n'est pas un garde-fou.

    Cette fonction est le seul endroit où la question se pose. Quand le choix
    de l'asset par plateforme arrivera (PR de Tetardtek), c'est ICI qu'il
    faudra élargir, pas dans l'interface."""
    return os.name == "nt"


def lancer_remplacement(nouveau, cible):
    """Auto-mise à jour du Compagnon : un programme ne peut pas s'écraser
    lui-même pendant qu'il tourne. On confie donc l'échange à un minuscule
    script relais.

    ⚠️ CE QUE FAISAIT L'ANCIEN RELAIS, et pourquoi il a été réécrit
    (programme 9, 01/08/2026). Il se servait de « del » comme test de
    verrou : tant que l'exe tournait, la suppression échouait ; dès qu'elle
    réussissait, il déplaçait le neuf à la place. Deux défauts, et le second
    est grave :

      - entre le « del » et le « move », **il n'existait aucun Compagnon sur
        la machine** ;
      - le code de retour du « move » n'était pas testé, le lancement ne
        vérifiait pas que la cible existait, et le relais s'effaçait
        lui-même — donc un « move » raté (antivirus tenant le fichier neuf,
        disque plein, droits) laissait le joueur **sans Compagnon et sans la
        moindre trace**.

    CE QUI REND LE NOUVEAU RELAIS SÛR, et c'est une mesure, pas une
    intuition : **Windows autorise à RENOMMER un exécutable en cours**
    (il interdit seulement de le supprimer). Vérifié sur un vrai processus :
    « del » échoue, « rename » réussit. On met donc l'ancien DE CÔTÉ au lieu
    de le supprimer, ce qui marche même si l'appli n'est pas encore fermée,
    et il reste récupérable à tout instant.

    Conséquence heureuse : **plus besoin de test de verrou du tout.**
    Supprimer le « .ancien » ne réussit que lorsque l'ancien processus a
    vraiment rendu la main — l'attente et le nettoyage sont la même
    opération. (Les deux tests non destructifs envisagés ont d'ailleurs été
    éprouvés et écartés : « move » d'un fichier vers lui-même échoue dans
    les DEUX états, et l'ouverture en ajout « >> » aussi.)

    Chemin d'échec : on remet l'ancien en place, on le relance, et on écrit
    un journal à côté du Compagnon. Le relais ne s'efface QUE s'il a réussi.
    """
    # Le garde-fou qui MORD, plutôt que l'échec par chance. Sans lui, ce
    # chemin ne ratait sous Linux que parce que `creationflags` lève — et
    # quiconque « corrigerait » cette ligne un jour ferait écraser le binaire
    # Linux du joueur par un .exe Windows, c'est-à-dire le laisserait sans Hub
    # du tout : exactement le défaut que le programme 9 a réparé.
    if not remplacement_possible():
        raise RuntimeError(
            "l'auto-mise à jour de l'application n'existe que sous Windows "
            "(le relais est un .bat, et l'asset publié est un .exe)")
    ancien = cible + ".ancien"
    journal = os.path.join(os.path.dirname(cible) or ".",
                           "AscensionFR_maj_echec.log")
    fd, bat = tempfile.mkstemp(suffix=".bat", prefix="AscensionFR_maj_")
    # ⚠️ LES CHEMINS PASSENT PAR L'ENVIRONNEMENT, PAS PAR LE TEXTE DU .BAT.
    # Un .bat est relu par cmd.exe dans la page de code OEM (cp850 en
    # France), alors que « mbcs » écrit en ANSI (cp1252) : un « é » écrit
    # d'un côté n'est pas celui qu'on relit de l'autre. Le banc l'a montré —
    # le scénario « Dossier de Jérôme » échouait, et en SILENCE, faute de
    # pouvoir même écrire son journal. C'était déjà vrai de l'ancien relais.
    # En passant par l'environnement, cmd.exe reçoit les chemins en natif et
    # le .bat lui-même reste PUREMENT ASCII : plus de page de code du tout.
    environnement = dict(os.environ)
    environnement["AFR_CIBLE"] = cible
    environnement["AFR_NOUVEAU"] = nouveau
    environnement["AFR_ANCIEN"] = ancien
    environnement["AFR_JOURNAL"] = journal
    contenu = (
        "@echo off\r\n"
        "setlocal\r\n"
        "set \"CIBLE=%%AFR_CIBLE%%\"\r\n"
        "set \"NOUVEAU=%%AFR_NOUVEAU%%\"\r\n"
        "set \"ANCIEN=%%AFR_ANCIEN%%\"\r\n"
        "set \"JOURNAL=%%AFR_JOURNAL%%\"\r\n"
        "\r\n"
        "rem -- 1. mettre l'ancien DE COTE (jamais le supprimer) -----------\r\n"
        "if exist \"%%ANCIEN%%\" del \"%%ANCIEN%%\" >nul 2>&1\r\n"
        "move /y \"%%CIBLE%%\" \"%%ANCIEN%%\" >nul 2>&1\r\n"
        "if errorlevel 1 goto pas_touche\r\n"
        "\r\n"
        "rem -- 2. mettre le neuf en place --------------------------------\r\n"
        "move /y \"%%NOUVEAU%%\" \"%%CIBLE%%\" >nul 2>&1\r\n"
        "if errorlevel 1 goto retour_arriere\r\n"
        "if not exist \"%%CIBLE%%\" goto retour_arriere\r\n"
        "\r\n"
        "rem -- 3. attendre que l'ancien processus rende la main. Supprimer\r\n"
        "rem       le .ancien n'y arrive QUE la : l'attente et le nettoyage\r\n"
        "rem       sont la meme operation, aucun test de verrou destructif.\r\n"
        "set /a N=0\r\n"
        ":attente\r\n"
        "set /a N+=1\r\n"
        "del \"%%ANCIEN%%\" >nul 2>&1\r\n"
        "if not exist \"%%ANCIEN%%\" goto pret\r\n"
        "if %%N%% GEQ 30 goto pret\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        "goto attente\r\n"
        "\r\n"
        ":pret\r\n"
        "rem -- 4. respiration : l'antivirus inspecte l'exe tout juste ecrit.\r\n"
        "rem       Conservee telle quelle (programme 9 : on ne change pas\r\n"
        "rem       deux choses a la fois).\r\n"
        "timeout /t 4 /nobreak >nul\r\n"
        "start \"\" \"%%CIBLE%%\"\r\n"
        "del \"%%~f0\"\r\n"
        "exit /b 0\r\n"
        "\r\n"
        ":retour_arriere\r\n"
        "move /y \"%%ANCIEN%%\" \"%%CIBLE%%\" >nul 2>&1\r\n"
        "echo [%%DATE%% %%TIME%%] Mise a jour impossible : le nouveau fichier"
        " n'a pas pu remplacer l'ancien. L'ancien Compagnon a ete remis en"
        " place. >> \"%%JOURNAL%%\"\r\n"
        "goto relancer_ancien\r\n"
        "\r\n"
        ":pas_touche\r\n"
        "echo [%%DATE%% %%TIME%%] Mise a jour impossible : l'ancien Compagnon"
        " n'a pas pu etre mis de cote. Rien n'a ete modifie."
        " >> \"%%JOURNAL%%\"\r\n"
        "\r\n"
        ":relancer_ancien\r\n"
        "if exist \"%%CIBLE%%\" start \"\" \"%%CIBLE%%\"\r\n"
        "exit /b 1\r\n") % {}
    # Le contenu est désormais 100 % ASCII (les chemins sont dans
    # l'environnement) : « ascii » plutôt que « mbcs », et l'encodage ne peut
    # plus mentir en silence — une erreur ici serait un vrai plantage, pas un
    # caractère remplacé par « ? ».
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(contenu)
    subprocess.Popen(["cmd", "/c", bat], env=environnement,
                     creationflags=0x08000000)      # CREATE_NO_WINDOW
    return bat


# --------------------------------------------------------------------------- #
# Rapport de contribution (lecture des sauvegardes de l'addon)
# --------------------------------------------------------------------------- #
def fichiers_sauvegarde(jeu):
    """La sauvegarde de l'addon pour chaque compte du jeu. Le fichier porte le
    nom de L'ADDON (AscensionFR.lua) — c'est la règle WoW —, et il contient la
    variable AscensionFRSaved."""
    base = os.path.join(jeu, "WTF", "Account")
    trouves = []
    if os.path.isdir(base):
        for compte in sorted(os.listdir(base)):
            p = os.path.join(base, compte, "SavedVariables",
                             "AscensionFR.lua")
            if os.path.isfile(p):
                trouves.append(p)
    return trouves


def lire_sauvegarde(chemin):
    """Exécute le fichier SavedVariables (du Lua pur) et rend la table."""
    from lupa import LuaRuntime
    lua = LuaRuntime(unpack_returned_tuples=True)
    with open(chemin, encoding="utf-8") as f:
        lua.execute(f.read())
    return lua.globals().AscensionFRSaved


def est_table(v):
    return hasattr(v, "items")


def lire_stats(jeu):
    """(nombre de textes traduits actifs, entrées en attente dans le rapport),
    lus dans la sauvegarde de l'addon. L'addon y note son total à chaque
    session (DernierTotal) ; l'attente est ce que « Envoyer » partirait."""
    total = None
    for chemin in fichiers_sauvegarde(jeu):
        try:
            saved = lire_sauvegarde(chemin)
            t = saved and saved["DernierTotal"]
            if t:
                total = max(total or 0, int(t))
        except Exception:
            continue
    try:
        # Ce qui reste VRAIMENT à partir : les entrées déjà envoyées ne
        # comptent plus (sinon le chiffre ne bougeait jamais).
        _, attente, _ = construire_rapport(jeu, deja_envoyees())
    except Exception:
        attente = 0
    return total, attente


def deja_envoyees():
    """Empreintes des entrées déjà parties, mémorisées par le Compagnon."""
    return set(charger_config().get("envoyees") or [])


def noter_envoyees(cfg, empreintes):
    """Ajoute les entrées qui viennent de partir. On plafonne la liste :
    elle ne sert qu'à ne pas se répéter, inutile de la garder à vie."""
    mémoire = list(cfg.get("envoyees") or []) + list(empreintes)
    cfg["envoyees"] = mémoire[-20000:]
    sauver_config(cfg)


def dossiers_caches(jeu):
    """Les dossiers de cache de TOUS les royaumes joués sur cette machine,
    toutes langues de client confondues :
    <jeu>\\Cache\\WDB\\<langue>\\<royaume>\\*.wdb.
    Avant on ne prenait que « Conquest of Azeroth » ; on collecte désormais
    TOUS les royaumes Ascension (Darkmoon Wildcard, Dawnrise Freepick,
    saisonniers…) pour pouvoir tout traduire. Rend des couples
    (nom_royaume, chemin)."""
    base = os.path.join(jeu, "Cache", "WDB")
    trouves = []
    if os.path.isdir(base):
        for langue in sorted(os.listdir(base)):
            d = os.path.join(base, langue)
            if not os.path.isdir(d):
                continue
            for royaume in sorted(os.listdir(d)):
                r = os.path.join(d, royaume)
                if os.path.isdir(r):
                    trouves.append((royaume, r))
    return trouves


def extraire_caches(jeu):
    """Extrait les textes anglais des caches du jeu (quêtes, PNJ, objets…)
    et les compresse. Rend (octets .json.gz, nombre d'entrées) ou (None, 0) :
    quoi qu'il arrive, le rapport part — au pire sans cette pièce jointe."""
    if parser_wdb is None:
        return None, 0
    try:
        fusion = {}
        royaumes = set()
        for royaume, dossier in dossiers_caches(jeu):
            tmp = tempfile.mkdtemp(prefix="afr_caches_")
            try:
                parser_wdb.parse_dir(dossier, tmp)
                apport = 0
                for f in os.listdir(tmp):
                    if not f.endswith(".json"):
                        continue
                    with open(os.path.join(tmp, f), encoding="utf-8") as g:
                        data = json.load(g)
                    apport += len(data)
                    fusion.setdefault(f[:-5], {}).update(data)
                if apport:
                    royaumes.add(royaume)
            except Exception:
                pass                       # un cache abîmé n'empêche pas le reste
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        total = sum(len(v) for v in fusion.values())
        if total == 0:
            return None, 0
        paquet = {"format": 1,
                  "royaume": ", ".join(sorted(royaumes)) or "Ascension",
                  "extraits": fusion}

        def compresser():
            return gzip.compress(json.dumps(
                paquet, ensure_ascii=False,
                separators=(",", ":")).encode("utf-8"))
        gz = compresser()
        if len(gz) > 7_500_000:            # limite Discord (~8 Mo) : on allège
            paquet["extraits"].pop("objets", None)     # la section la plus lourde
            total = sum(len(v) for v in paquet["extraits"].values())
            gz = compresser()
        if len(gz) > 7_500_000 or total == 0:
            return None, 0
        return gz, total
    except Exception:
        return None, 0


def envoyer_rapport_discord(rapport, caches=None):
    """Poste le rapport en pièce jointe .txt — et, si fournis, les caches en
    .json.gz — sur le salon des rapports (via le webhook). Lève en cas
    d'échec — l'appelant se replie alors sur la copie."""
    import uuid
    frontiere = "----AscensionFR" + uuid.uuid4().hex
    marque = uuid.uuid4().hex[:8]
    meta = json.dumps({"username": "Compagnon Ascension FR",
                       "content": "Nouveau rapport de contribution :"})
    # Corps assemblé en OCTETS : la pièce jointe des caches est binaire.
    morceaux = [
        ("--%s\r\n"
         "Content-Disposition: form-data; name=\"payload_json\"\r\n"
         "Content-Type: application/json\r\n\r\n%s\r\n"
         % (frontiere, meta)).encode("utf-8"),
        ("--%s\r\n"
         "Content-Disposition: form-data; name=\"files[0]\"; "
         "filename=\"rapport_%s.txt\"\r\n"
         "Content-Type: text/plain; charset=utf-8\r\n\r\n"
         % (frontiere, marque)).encode("utf-8")
        + rapport.encode("utf-8") + b"\r\n",
    ]
    if caches:
        morceaux.append(
            ("--%s\r\n"
             "Content-Disposition: form-data; name=\"files[1]\"; "
             "filename=\"caches_%s.json.gz\"\r\n"
             "Content-Type: application/octet-stream\r\n\r\n"
             % (frontiere, marque)).encode("utf-8")
            + caches + b"\r\n")
    morceaux.append(("--%s--\r\n" % frontiere).encode("utf-8"))
    req = urllib.request.Request(
        WEBHOOK_RAPPORTS, data=b"".join(morceaux), method="POST",
        headers={"User-Agent": UA["User-Agent"],
                 "Content-Type": "multipart/form-data; boundary=" + frontiere})
    with urllib.request.urlopen(req, timeout=60, context=CONTEXTE_SSL):
        pass                               # 2xx = envoyé ; sinon une exception


def raison_echec(exc):
    """Traduit une exception en une phrase que le joueur peut COMPRENDRE.

    Ajouté le 24/07/2026. Tout échec d'installation affichait « problème
    réseau » : un disque plein, un antivirus, un chemin trop long ou un zip
    abîmé envoyaient donc le joueur vérifier sa connexion pour rien. Une
    mauvaise piste coûte plus cher qu'un message honnête."""
    import socket
    import ssl as _ssl
    if isinstance(exc, PermissionError):
        return ("Windows a refusé l'écriture dans le dossier du jeu. "
                "Relance en administrateur (bouton ci-dessous).")
    if isinstance(exc, _ssl.SSLError):
        return ("La connexion sécurisée a échoué. C'est presque toujours un "
                "antivirus ou un pare-feu qui inspecte le trafic : mets "
                "l'application en exception, ou coupe-le le temps de "
                "l'installation.")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return ("Le téléchargement a expiré. Connexion trop lente ou coupée — "
                "réessaie.")
    if isinstance(exc, urllib.error.HTTPError):
        if exc.code == 404:
            return ("Le fichier n'existe plus à cette adresse. Signale-le sur "
                    "le Discord, c'est un souci de notre côté.")
        if exc.code in (403, 429):
            return ("GitHub a temporairement limité les téléchargements. "
                    "Attends quelques minutes et réessaie.")
        return "GitHub a répondu une erreur %s." % exc.code
    if isinstance(exc, urllib.error.URLError):
        return ("Impossible de joindre GitHub. Vérifie ta connexion, ou "
                "regarde si un antivirus bloque l'application.")
    if isinstance(exc, zipfile.BadZipFile):
        return ("Le fichier téléchargé est abîmé (téléchargement interrompu, "
                "ou antivirus qui l'a modifié). Réessaie.")
    if isinstance(exc, OSError):
        # 28 = disque plein ; 206 sous Windows = chemin trop long.
        if getattr(exc, "errno", None) == 28:
            return "Il n'y a plus assez de place sur le disque."
        texte = str(exc).lower()
        if "too long" in texte or getattr(exc, "winerror", None) == 206:
            return ("Un chemin de fichier est trop long pour Windows. "
                    "Déplace le jeu dans un dossier plus court "
                    "(par exemple D:\\Ascension).")
        return "Erreur disque : %s" % exc
    return "Erreur inattendue : %s: %s" % (type(exc).__name__, exc)


# --------------------------------------------------------------------------- #
# Contrôle d'installation — « j'ai installé, le jeu reste en anglais »
# --------------------------------------------------------------------------- #
# Douze joueurs, neuf jours, toujours les trois mêmes causes (veille Discord
# du 18 au 26/07/2026) :
#   1. mauvais dossier            -> vérifiable ET réparable (racine_jeu)
#   2. « Allow Non-Launcher AddOns » décochée  -> NI l'un NI l'autre, voir plus bas
#   3. « Activer la traduction » décochée      -> vérifiable ET réparable
#
# Règle de la maison : on ne bricole pas un test approximatif. Un contrôle
# qu'on ne sait pas faire honnêtement s'affiche « à vérifier toi-même », avec
# la phrase exacte à chercher à l'écran — jamais un vert de complaisance.

# La case n°2 s'appelle en vrai « Allow Non-Launcher AddOns » (VF :
# « Autoriser les modules complémentaires sans lanceur »). C'est la CVar
# `loadUnknownAddOns`, lue et écrite UNIQUEMENT en jeu :
#   Ascension_AddonPanel\AddonPanel.xml:189  C_CVar.GetBool("loadUnknownAddOns")
#   Ascension_AddonPanel\AddonPanel.xml:193  C_CVar.Set("loadUnknownAddOns", …)
# Elle n'est écrite dans AUCUN fichier lisible : ni Config.wtf, ni les
# config-cache.wtf, ni Wow.ini, ni les réglages du launcher. Vérifié case
# COCHÉE, disque muet. Le Hub ne peut donc ni la lire ni la cocher — il se
# contente de dire où elle est, exactement.
CASE_LANCEUR_LIBELLE = "Allow Non-Launcher AddOns"
CASE_LANCEUR_OU = ("écran de sélection des personnages → bouton « AddOns » "
                   "en bas à gauche → la case juste AU-DESSUS de « Load out "
                   "of date AddOns », en bas à droite du panneau.")
CASE_LANCEUR_TEMOIN = "Not a Launcher AddOn"

NOS_ADDONS = ("AscensionFR", "AscensionFR_Repliques")


def jeu_ouvert(jeu=None):
    """Le jeu tourne-t-il ? Rend True / False / None (on n'a pas pu savoir).

    Trois usages : ne pas écrire dans des SavedVariables que le client
    réécrira à la déconnexion, ne pas supprimer des fichiers verrouillés, et
    dater honnêtement ce qu'on lit. Le None est important : « je ne sais
    pas » n'est pas « non »."""
    noms = {"ascension.exe", "wow.exe", "project-ascension.exe"}
    if jeu and os.path.isdir(jeu):
        try:
            noms |= {n.lower() for n in os.listdir(jeu)
                     if n.lower().endswith(".exe")}
        except OSError:
            pass
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            nom = (p.info.get("name") or "").lower()
            if nom in noms:
                return True
        return False
    except Exception:
        pass
    # Repli sans psutil (l'exe figé pourrait ne pas l'embarquer un jour).
    try:
        sortie = subprocess.run(["tasklist", "/fo", "csv", "/nh"],
                                capture_output=True, text=True, timeout=15,
                                creationflags=0x08000000).stdout.lower()
    except Exception:
        return None
    return any(('"%s"' % n) in sortie for n in noms)


# --- Cause 3 : l'interrupteur « Activer la traduction » --------------------- #
# Il vit dans AscensionFRSaved.Options.desactive (AscensionFR\Core.lua:397).
# La clé est À L'ENVERS de la case, et surtout elle n'existe QUE si le joueur
# a décoché : `opt.desactive = not self:GetChecked() or nil`. Donc
# ABSENTE = TRADUCTION ACTIVE. Un Hub qui crie au problème sur une clé absente
# alarmerait tout le monde pour rien.
RE_DESACTIVE = re.compile(r'\[\s*"desactive"\s*\]\s*=\s*true', re.IGNORECASE)
RE_DESACTIVE_B = re.compile(rb'\[\s*"desactive"\s*\]\s*=\s*true', re.IGNORECASE)


def _retirer_ligne(chemin, motif_binaire):
    """Retire les lignes qui portent `motif_binaire` — EN OCTETS, jamais en
    texte décodé. Rend 1 si le fichier a changé, 0 sinon.

    Pourquoi en octets : ces fichiers appartiennent au joueur (noms de
    personnages, texte de quêtes récolté) et peuvent contenir des octets que
    WoW a écrits sans se soucier de l'UTF-8. Les lire avec errors="replace"
    puis les réécrire remplacerait chacun de ces octets par « ? » — on
    corrigerait une case à cocher en abîmant silencieusement des kilo-octets
    de données. On ne touche donc QUE la ligne visée, et on n'interprète rien.
    L'écriture passe par un fichier voisin puis un remplacement atomique : une
    coupure de courant ne laisse pas une sauvegarde à moitié écrite."""
    with open(chemin, "rb") as f:
        lignes = f.readlines()
    gardees = [l for l in lignes if not motif_binaire.search(l)]
    if len(gardees) == len(lignes):
        return 0
    tampon = chemin + ".afr_tmp"
    with open(tampon, "wb") as f:
        f.writelines(gardees)
    os.replace(tampon, chemin)
    return 1


def etat_traduction(jeu):
    """Lit l'interrupteur dans les sauvegardes de l'addon, sans exécuter le
    fichier : on ne cherche qu'un booléen, et ces fichiers grossissent (25 Ko
    aujourd'hui, bien plus chez un gros contributeur). Un simple parcours de
    texte est plus rapide et ne peut pas planter sur du Lua abîmé.

    Rend (etat, details) avec etat parmi :
      'active'      — rien à faire ;
      'desactivee'  — au moins un compte a la case décochée ;
      'jamais_joue' — aucune sauvegarde : l'addon n'a pas encore tourné ;
      'inconnu'     — illisible.
    details porte les chemins concernés et la date de dernière écriture."""
    fichiers = fichiers_sauvegarde(jeu) if jeu else []
    if not fichiers:
        return "jamais_joue", {"fichiers": [], "date": None}
    coupes, date = [], None
    for chemin in fichiers:
        try:
            with open(chemin, encoding="utf-8", errors="replace") as f:
                texte = f.read()
        except OSError:
            return "inconnu", {"fichiers": fichiers, "date": None}
        try:
            date = max(date or 0, os.path.getmtime(chemin))
        except OSError:
            pass
        if RE_DESACTIVE.search(texte):
            coupes.append(chemin)
    if coupes:
        return "desactivee", {"fichiers": coupes, "date": date}
    return "active", {"fichiers": fichiers, "date": date}


def reactiver_traduction(jeu):
    """Recoche « Activer la traduction » en retirant la clé `desactive` des
    sauvegardes. Rend (nombre_de_fichiers_corriges, message_d_erreur_ou_None).

    On ne réécrit QUE la ligne fautive (le reste du fichier — récolte,
    signalements, échecs d'alignement — n'est jamais touché), et jamais si le
    jeu tourne : WoW réécrit ses SavedVariables entières à la déconnexion et
    effacerait notre correction sans rien dire."""
    if jeu_ouvert(jeu) is True:
        return 0, ("Ferme d'abord le jeu : tant qu'il tourne, il réécrira le "
                   "fichier en se fermant et effacera la correction.")
    etat, details = etat_traduction(jeu)
    if etat != "desactivee":
        return 0, None
    corriges = 0
    for chemin in details["fichiers"]:
        try:
            corriges += _retirer_ligne(chemin, RE_DESACTIVE_B)
        except OSError as e:
            return corriges, "Écriture impossible : %s" % e
    if not corriges:
        return 0, ("La clé n'est pas sur une ligne à elle : recoche « Activer "
                   "la traduction » toi-même dans /afr.")
    return corriges, None


# --- Cousin de la cause 2 : l'addon décoché dans la liste ------------------- #
# Ce n'est PAS la case « Allow Non-Launcher AddOns » (celle-là est hors de
# portée), mais l'autre moitié de la phrase de Dan sur Discord : « regarde
# qu'il soit bien coché ». Ça, en revanche, est écrit noir sur blanc dans
# WTF\Account\<compte>\<royaume>\<perso>\AddOns.txt — PAR PERSONNAGE.
def _fichiers_addons_txt(jeu):
    base = os.path.join(jeu or "", "WTF", "Account")
    trouves = []
    if not os.path.isdir(base):
        return trouves
    for compte in sorted(os.listdir(base)):
        for royaume in sorted(_sous_dossiers(os.path.join(base, compte))):
            for perso in sorted(_sous_dossiers(royaume)):
                chemin = os.path.join(perso, "AddOns.txt")
                if os.path.isfile(chemin):
                    trouves.append(chemin)
    return trouves


def _sous_dossiers(chemin):
    try:
        return [os.path.join(chemin, n) for n in os.listdir(chemin)
                if os.path.isdir(os.path.join(chemin, n))]
    except OSError:
        return []


def etat_addons_coches(jeu):
    """Rend (etat, fichiers) : 'decoche' si au moins un personnage a
    AscensionFR sur « disabled », 'coche' si tous l'ont sur « enabled »,
    'inconnu' si aucun AddOns.txt (jeu jamais lancé depuis l'installation)."""
    fichiers = _fichiers_addons_txt(jeu)
    if not fichiers:
        return "inconnu", []
    fautifs, vu = [], False
    for chemin in fichiers:
        try:
            with open(chemin, encoding="utf-8", errors="replace") as f:
                for ligne in f:
                    nom, _, etat = ligne.partition(":")
                    if nom.strip() not in NOS_ADDONS:
                        continue
                    vu = True
                    if etat.strip().lower().startswith("disab"):
                        fautifs.append(chemin)
                        break
        except OSError:
            continue
    if fautifs:
        # « Décoché partout » et « décoché sur un perso » ne sont pas la même
        # chose. Beaucoup de joueurs (et Dan) ont un personnage d'essai sans
        # la traduction : en faire un souci mettrait le Hub au rouge en
        # permanence, et un voyant toujours rouge, plus personne ne le
        # regarde. On ne crie que si AUCUN personnage ne l'a coché.
        if len(fautifs) < len(fichiers):
            return "reserve", fautifs
        return "decoche", fautifs
    return ("coche", fichiers) if vu else ("inconnu", fichiers)


def recocher_addons(jeu):
    """Repasse nos addons sur « enabled » dans les AddOns.txt fautifs.
    Rend (nombre_de_fichiers_corriges, message_d_erreur_ou_None)."""
    if jeu_ouvert(jeu) is True:
        return 0, ("Ferme d'abord le jeu : il réécrit cette liste en se "
                   "fermant.")
    etat, fautifs = etat_addons_coches(jeu)
    if etat != "decoche":
        return 0, None
    # Même précaution que pour les sauvegardes : en OCTETS. On garde la fin de
    # ligne d'origine du fichier (WoW écrit en CRLF ; réécrire en LF ferait
    # d'un simple « recocher » une réécriture de tout le fichier).
    noms = tuple(n.encode("ascii") for n in NOS_ADDONS)
    corriges = 0
    for chemin in fautifs:
        try:
            with open(chemin, "rb") as f:
                lignes = f.readlines()
            neuves, change = [], False
            for ligne in lignes:
                nom, sep, etat_ligne = ligne.partition(b":")
                if (sep and nom.strip() in noms
                        and etat_ligne.strip().lower().startswith(b"disab")):
                    fin = (b"\r\n" if ligne.endswith(b"\r\n")
                           else (b"\n" if ligne.endswith(b"\n") else b""))
                    ligne = nom.strip() + b": enabled" + fin
                    change = True
                neuves.append(ligne)
            if change:
                tampon = chemin + ".afr_tmp"
                with open(tampon, "wb") as f:
                    f.writelines(neuves)
                os.replace(tampon, chemin)
                corriges += 1
        except OSError as e:
            return corriges, "Écriture impossible : %s" % e
    return corriges, None


# --- Le contrôle complet --------------------------------------------------- #
# Chaque point rend un dictionnaire :
#   cle       identifiant stable
#   titre     ce que le joueur lit
#   etat      'ok' | 'souci' | 'inconnu'
#   detail    une phrase, toujours ; l'action à faire quand c'est un souci
#   reparable nom de la réparation automatique disponible, ou None
def controler_installation(jeu):
    """Les quatre points d'entrée, dans l'ordre où ils bloquent un joueur.
    Aucun « tout est bon » n'est rendu tant qu'un point est en souci ou
    inconnu — c'est tout l'objet de cette fonction."""
    points = []

    # 1. Le dossier
    if not jeu:
        points.append({
            "cle": "dossier", "titre": "Dossier du jeu",
            "etat": "souci", "reparable": None,
            "detail": "Aucun dossier choisi. Onglet Traduction → Changer."})
    elif not racine_jeu(jeu):
        points.append({
            "cle": "dossier", "titre": "Dossier du jeu",
            "etat": "souci", "reparable": "dossier",
            "detail": ("« %s » n'est pas la racine du jeu : il faudrait y "
                       "trouver Ascension.exe et les dossiers Data et "
                       "Interface. Rien de ce qui est installé là n'est lu "
                       "par le jeu." % jeu)})
    else:
        imbriquees = installations_imbriquees(jeu)
        if imbriquees:
            # On ne propose « Réparer » que si tout ce qu'il y a là-dedans
            # est à nous. Sinon on donne le chemin et on laisse le joueur
            # faire le tri : ses propres addons ne sont pas à nous.
            notre = all(_que_du_notre(c) for c in imbriquees)
            points.append({
                "cle": "dossier", "titre": "Dossier du jeu",
                "etat": "souci",
                "reparable": "imbriquees" if notre else None,
                "detail": ("Une ancienne traduction traîne au mauvais "
                           "endroit (%s). Le jeu ne la lit pas, mais elle "
                           "fait croire que tout est installé.%s"
                           % (", ".join(imbriquees),
                              "" if notre else
                              " Il y a aussi des fichiers qui ne sont pas à "
                              "nous : à toi de faire le tri, le Hub n'y "
                              "touche pas."))})
        else:
            points.append({
                "cle": "dossier", "titre": "Dossier du jeu",
                "etat": "ok", "reparable": None, "detail": jeu})

    # 1 bis. L'addon est-il vraiment posé ?
    version = version_installee(jeu) if jeu else None
    points.append({
        "cle": "addon", "titre": "Traduction installée",
        "etat": "ok" if version else "souci",
        "reparable": None,
        "detail": ("version %s" % version) if version else
                  "Le dossier Interface\\AddOns\\AscensionFR est absent. "
                  "Onglet Traduction → Installer."})

    # 2. La case du lanceur — ni lisible ni cochable depuis ici. On le DIT.
    points.append({
        "cle": "case_lanceur",
        "titre": "Case « %s »" % CASE_LANCEUR_LIBELLE,
        "etat": "inconnu", "reparable": None,
        "detail": ("Le Hub ne peut pas la vérifier : ce réglage ne vit dans "
                   "aucun fichier, seulement dans le jeu. À vérifier une "
                   "fois, toi-même : %s Si tu lis « %s » sur la ligne "
                   "AscensionFR, c'est qu'elle est décochée."
                   % (CASE_LANCEUR_OU, CASE_LANCEUR_TEMOIN))})

    # 2 bis. L'addon coché dans la liste (ça, c'est lisible).
    etat_coche, fichiers = etat_addons_coches(jeu) if jeu else ("inconnu", [])
    # On NOMME les personnages concernés : « au moins un personnage » ferait
    # chercher partout, alors que la liste tient en trois mots.
    persos = ", ".join(sorted({os.path.basename(os.path.dirname(f))
                               for f in fichiers})) if fichiers else ""
    points.append({
        "cle": "addon_coche", "titre": "AscensionFR coché dans la liste",
        "etat": {"coche": "ok", "decoche": "souci",
                 "reserve": "reserve"}.get(etat_coche, "inconnu"),
        "reparable": ("addons_txt"
                      if etat_coche in ("decoche", "reserve") else None),
        "detail": {
            "coche": "Coché pour tous tes personnages.",
            "decoche": ("Décoché PARTOUT — le jeu ne chargera l'addon sur "
                        "aucun personnage. Le Hub peut le recocher "
                        "(jeu fermé)."),
            "reserve": ("Coché partout sauf pour : %s. Ces personnages-là "
                        "joueront en anglais — c'est peut-être voulu. Le Hub "
                        "peut les recocher (jeu fermé)." % persos),
        }.get(etat_coche,
              "Pas encore de liste d'addons : lance le jeu une fois.")})

    # 3. L'interrupteur de /afr
    etat_trad, details = etat_traduction(jeu) if jeu else ("inconnu", {})
    quand = ""
    if details.get("date"):
        quand = time.strftime(" (d'après ta session du %d/%m à %H:%M)",
                              time.localtime(details["date"]))
    points.append({
        "cle": "interrupteur", "titre": "Case « Activer la traduction »",
        "etat": {"active": "ok", "desactivee": "souci"}.get(etat_trad,
                                                            "inconnu"),
        "reparable": "interrupteur" if etat_trad == "desactivee" else None,
        "detail": {
            "active": "Activée" + quand + ".",
            "desactivee": ("DÉCOCHÉE" + quand + " — c'est pour ça que le jeu "
                           "est en anglais. Le Hub peut la recocher (jeu "
                           "fermé). Attention : un clic droit sur le bouton "
                           "de la minicarte suffit à la décocher."),
            "jamais_joue": ("L'addon n'a pas encore tourné : lance le jeu "
                            "une fois, puis reviens."),
        }.get(etat_trad, "Sauvegarde illisible.")})

    return points


def resume_controle(points):
    """(tout_va_bien, nombre_de_soucis, nombre_d_inconnus). `tout_va_bien`
    n'est vrai que si RIEN n'est en souci ET que rien n'est inconnu.

    L'état « reserve » (vrai, mais avec une nuance à lire) ne compte dans
    aucun des deux : il est là pour être VU dans la fenêtre, pas pour faire
    virer tout le Hub au rouge."""
    soucis = sum(1 for p in points if p["etat"] == "souci")
    inconnus = sum(1 for p in points if p["etat"] == "inconnu")
    return (not soucis and not inconnus), soucis, inconnus


def reparer(jeu, quoi):
    """Applique une réparation nommée. Rend (fait, message)."""
    if quoi == "interrupteur":
        n, err = reactiver_traduction(jeu)
        if err:
            return False, err
        return bool(n), ("« Activer la traduction » recochée. Relance le jeu."
                         if n else "Rien à corriger.")
    if quoi == "addons_txt":
        n, err = recocher_addons(jeu)
        if err:
            return False, err
        return bool(n), ("AscensionFR recoché pour %d personnage(s). Relance "
                         "le jeu." % n if n else "Rien à corriger.")
    if quoi == "imbriquees":
        restants = []
        for chemin in installations_imbriquees(jeu):
            if not _que_du_notre(chemin):
                # Deuxième regard juste avant d'effacer : entre l'affichage
                # et le clic, le disque a pu changer.
                restants.append(chemin + " (il n'y a pas que nos fichiers)")
                continue
            try:
                shutil.rmtree(chemin)
            except OSError:
                restants.append(chemin)
        if restants:
            return False, ("Impossible de retirer %s — ferme le jeu et "
                           "réessaie." % ", ".join(restants))
        return True, "Ancienne installation mal placée retirée."
    return False, "Rien à réparer ici."


def _peut_ecrire(dossier):
    """Teste POUR DE VRAI le droit d'écriture : sur Windows, os.access ment
    (il ignore les ACL et le contrôle de compte d'utilisateur)."""
    if not dossier or not os.path.isdir(dossier):
        return False
    temoin = os.path.join(dossier, ".afr_test_ecriture")
    try:
        with open(temoin, "w") as f:
            f.write("x")
        os.remove(temoin)
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- #
# « Tout désinstaller » — la sortie propre
# --------------------------------------------------------------------------- #
# Le 26/07/2026 un joueur a retiré le dossier d'addon ET le contenu de
# %appdata% : son jeu est resté en français et il a enchaîné les erreurs. Il
# avait raison de s'énerver — la sortie propre n'était écrite nulle part, et
# elle n'est pas devinable : le français vient de QUATRE dépôts indépendants,
# tous DANS le dossier du jeu, dont %appdata% ne fait pas partie.
#
#   1. Interface\AddOns\AscensionFR (+ _Repliques)   — le gros morceau
#   2. Interface\PTRXML                              — écrans de connexion,
#      HORS AddOns : c'est celui qu'on oublie, et c'est lui qui laisse le jeu
#      « toujours en français » après une désinstallation à la main
#   3. Sound\ (ou Sound_off\ si les voix ont été coupées)  — les voix
#   4. Wow.ini (Country=FR / Language=fr)            — posé par le zip des voix
#
# Ce que le zip des voix pose sous Sound\, mesuré sur l'archive réelle
# (14 442 entrées) : ces cinq dossiers, et rien d'autre. Le son d'origine du
# client, lui, vit dans les MPQ de Data\ — jamais en clair. On ne supprime
# donc QUE ces cinq-là, et Sound\ ne disparaît que s'il finit vide : un
# joueur qui aurait posé ses propres fichiers ailleurs sous Sound\ les garde.
SOUS_DOSSIERS_VOIX = ("CREATURE", "Creature", "Character", "CinematicVoices",
                      "Interface", "Music")

# Décision de Dan attendue (question posée dans la réponse du 26/07) : faut-il
# cocher les voix par défaut ? 1,7 Go et un re-téléchargement si le joueur
# change d'avis. Par défaut on les coche — « tout désinstaller » doit vouloir
# dire tout —, mais la case reste décochable et la liste s'affiche AVANT.
VOIX_COCHEES_PAR_DEFAUT = True


def _taille(chemins):
    """Octets occupés par une liste de fichiers/dossiers (0 si illisible)."""
    total = 0
    for chemin in chemins:
        if os.path.isfile(chemin):
            try:
                total += os.path.getsize(chemin)
            except OSError:
                pass
            continue
        for dossier, _d, fichiers in os.walk(chemin):
            for f in fichiers:
                try:
                    total += os.path.getsize(os.path.join(dossier, f))
                except OSError:
                    pass
    return total


def _sauvegardes_a_retirer(jeu):
    """Tous les AscensionFR*.lua (+ .bak) de nos addons, au niveau compte ET
    au niveau personnage (aucun de nos .toc ne déclare de SavedVariables par
    personnage aujourd'hui, mais on balaie quand même : un .toc peut changer,
    et un fichier oublié suffit à faire mentir « c'est propre »)."""
    base = os.path.join(jeu or "", "WTF", "Account")
    trouves = []
    if not os.path.isdir(base):
        return trouves
    dossiers = []
    for compte in _sous_dossiers(base):
        dossiers.append(os.path.join(compte, "SavedVariables"))
        for royaume in _sous_dossiers(compte):
            for perso in _sous_dossiers(royaume):
                dossiers.append(os.path.join(perso, "SavedVariables"))
    for dossier in dossiers:
        try:
            noms = os.listdir(dossier)
        except OSError:
            continue
        for nom in noms:
            if nom.lower().startswith("ascensionfr"):
                trouves.append(os.path.join(dossier, nom))
    return sorted(trouves)


def elements_desinstallation(jeu, catalogue=()):
    """L'inventaire de TOUT ce que le Hub a posé, prêt à être affiché AVANT
    de supprimer quoi que ce soit. Rend une liste de dictionnaires :

      cle, libelle, chemins, taille, coche (proposition), note

    Seuls les éléments qui existent VRAIMENT sont rendus : la liste montrée
    au joueur est la liste de ce qui va disparaître, pas un catalogue
    théorique. `catalogue` est le catalogue d'addons du Hub (facultatif) —
    ce qui vient de nous et ce qui vient d'ailleurs y sont séparés."""
    elements = []
    if not jeu or not os.path.isdir(jeu):
        return elements
    addons = os.path.join(jeu, "Interface", "AddOns")

    def ajoute(cle, libelle, chemins, coche, note=""):
        # Dédoublonnage INSENSIBLE À LA CASSE : le zip des voix contient
        # « Sound/CREATURE » et « Sound/Creature », qui sont le MÊME dossier
        # sous Windows. Sans ça la taille annoncée doublait (2,9 Go pour
        # 1,7 Go réels) — un chiffre faux dans une liste de suppression,
        # c'est une confiance perdue.
        vivants, vus = [], set()
        for c in chemins:
            if not os.path.exists(c):
                continue
            cle_c = os.path.normcase(os.path.normpath(c))
            if cle_c in vus:
                continue
            vus.add(cle_c)
            vivants.append(c)
        if vivants:
            elements.append({"cle": cle, "libelle": libelle,
                             "chemins": vivants, "taille": _taille(vivants),
                             "coche": coche, "note": note})

    ajoute("traduction", "La traduction",
           [os.path.join(addons, n) for n in NOS_ADDONS]
           + [os.path.join(jeu, "Interface", "PTRXML")], True,
           "PTRXML est HORS de AddOns : c'est lui qui laisse les écrans de "
           "connexion en français quand on désinstalle à la main.")

    ajoute("imbriquees", "Restes d'une installation mal placée",
           installations_imbriquees(jeu), True,
           "Le jeu ne les lit pas — ils ne servent qu'à faire croire que "
           "tout est installé.")

    nous = [f for f in catalogue
            if (f.get("dossier") or "").startswith("AscensionFR")]
    autres = [f for f in catalogue
              if not (f.get("dossier") or "").startswith("AscensionFR")]

    def dossiers_fiche(fiche):
        return [os.path.join(addons, d) for d in
                [fiche.get("dossier")] + list(fiche.get("dossiers") or [])
                if d]

    ajoute("addons_maison", "Nos addons compagnons",
           [c for f in nous for c in dossiers_fiche(f)], True)
    ajoute("addons_tiers", "Addons d'autres auteurs installés par le Hub",
           [c for f in autres for c in dossiers_fiche(f)], False,
           "Ils ne sont pas de nous (DragonUI…) et marchent sans la "
           "traduction : décoché par défaut.")

    ajoute("sauvegardes", "Tes réglages en jeu (SavedVariables)",
           _sauvegardes_a_retirer(jeu), True)

    voix = [os.path.join(jeu, base, sous)
            for base in ("Sound", "Sound_off")
            for sous in SOUS_DOSSIERS_VOIX]
    ajoute("voix", "Les voix françaises", voix, VOIX_COCHEES_PAR_DEFAUT,
           "Environ 1,7 Go. Les remettre demanderait de tout re-télécharger. "
           "Les sons d'origine du jeu, eux, sont dans Data\\ : ils reviennent "
           "tout seuls.")

    ajoute("wow_ini", "Wow.ini (Country=FR / Language=fr)",
           [os.path.join(jeu, "Wow.ini")], False,
           "Posé par le pack de voix. Sans les voix il ne fait plus rien : "
           "décoché par défaut, le supprimer pourrait effacer un réglage du "
           "client.")

    ajoute("config", "Les réglages du Hub",
           [CONFIG_DIR], True,
           "%APPDATA%\\AscensionFR — le dossier que tout le monde vide en "
           "premier, alors qu'il ne contient RIEN qui traduise le jeu.")

    restes = []
    temp = tempfile.gettempdir()
    try:
        for nom in os.listdir(temp):
            if nom.startswith("AscensionFR_"):
                restes.append(os.path.join(temp, nom))
    except OSError:
        pass
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "AscensionFR_Compagnon")
    if os.environ.get("LOCALAPPDATA"):
        restes.append(local)
    ajoute("restes", "Fichiers temporaires du Hub", restes, True)
    return elements


def desinstaller_tout(jeu, elements):
    """Supprime les éléments choisis. Rend (resultats, tout_est_parti) où
    `resultats` est une liste de (libelle, ok, message).

    Rien n'échoue en silence : un fichier verrouillé, un jeu resté ouvert,
    un droit manquant — chacun est nommé, avec ce qu'il reste à faire."""
    resultats = []
    if jeu_ouvert(jeu) is True:
        return ([("Le jeu est ouvert", False,
                  "Ferme World of Warcraft (et le launcher), puis "
                  "recommence : Windows refuse de supprimer des fichiers "
                  "qu'un programme tient ouverts.")], False)
    for element in elements:
        restants = []
        for chemin in element["chemins"]:
            try:
                if os.path.isdir(chemin):
                    shutil.rmtree(chemin)
                elif os.path.exists(chemin):
                    os.remove(chemin)
            except OSError as e:
                restants.append("%s (%s)" % (chemin, e.strerror or e))
        if restants:
            resultats.append((element["libelle"], False,
                              "Pas pu retirer : " + " ; ".join(restants)))
        else:
            resultats.append((element["libelle"], True, "retiré"))
    # Sound\ et Sound_off\ ne disparaissent que s'ils sont VIDES : on ne
    # touche pas aux fichiers qu'un joueur y aurait mis lui-même.
    for base in ("Sound", "Sound_off"):
        chemin = os.path.join(jeu or "", base)
        try:
            if os.path.isdir(chemin) and not os.listdir(chemin):
                os.rmdir(chemin)
        except OSError:
            pass
    tout = all(ok for _l, ok, _m in resultats)
    return resultats, tout


def diagnostic(jeu=None):
    """Relevé copiable de l'état de l'installation.

    Les joueurs écrivent « ça marche pas » ; sans données, personne ne peut
    aider. Ce relevé répond aux quatre questions qui reviennent : le dossier
    est-il trouvé, peut-on y écrire, GitHub répond-il, et l'addon est-il là.
    Il ne contient AUCUNE information personnelle — seulement des chemins et
    des versions."""
    lignes = []

    def note(cle, valeur):
        lignes.append("%-26s %s" % (cle + " :", valeur))

    note("Hub", VERSION_COMPAGNON)
    note("Windows", platform.platform())
    note("Administrateur", "oui" if _est_admin() else "non")

    cfg = charger_config()
    memorise = cfg.get("jeu")
    jeu = jeu or memorise or chercher_jeu()
    note("Dossier mémorisé", memorise or "aucun")
    note("Dossier utilisé", jeu or "AUCUN — c'est le problème")

    if jeu:
        note("Dossier valide", "oui" if racine_jeu(jeu) else
             "NON — ce n'est pas la racine du jeu (ni Data ni Ascension.exe)")
        imbriquees = installations_imbriquees(jeu)
        if imbriquees:
            note("Installation imbriquée", "OUI — " + ", ".join(imbriquees))
        note("Écriture autorisée", "oui" if _peut_ecrire(jeu) else
             "NON — relance en administrateur")
        # Les deux contrôles qui expliquent la majorité des « installé mais
        # toujours en anglais ». La case du lanceur, elle, n'est nulle part
        # sur le disque : impossible de la relever ici (dit franchement).
        note("Activer la traduction", etat_traduction(jeu)[0])
        note("AscensionFR coché", etat_addons_coches(jeu)[0])
        note("Case « %s »" % CASE_LANCEUR_LIBELLE,
             "non vérifiable hors du jeu")
        ouvert = jeu_ouvert(jeu)
        note("Jeu en cours d'exécution",
             {True: "oui", False: "non"}.get(ouvert, "inconnu"))
        note("Version de l'addon", version_installee(jeu) or "non installé")
        note("Voix installées",
             "oui" if os.path.isfile(os.path.join(jeu, TEMOIN_VOIX))
             else "non")
        sauvegardes = fichiers_sauvegarde(jeu)
        note("Fichiers de relevé", "%d trouvé(s)" % len(sauvegardes))
        try:
            libre = shutil.disk_usage(jeu).free / (1024 ** 3)
            note("Place libre", "%.1f Go" % libre)
        except OSError:
            note("Place libre", "inconnue")

    try:
        version, url_zip, url_exe = derniere_release()
        note("GitHub", "joignable — dernière version %s" % (version or "?"))
        note("Zip de traduction", "présent" if url_zip else "ABSENT")
        note("Application", "présente" if url_exe else "absente")
    except Exception as e:
        note("GitHub", "INJOIGNABLE — " + raison_echec(e))

    note("Envoi des rapports",
         "configuré" if WEBHOOK_RAPPORTS else "désactivé (copie seulement)")
    return "\n".join(lignes)


def _est_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def empreinte(texte):
    """Petite signature d'une entrée, pour se souvenir qu'elle est partie."""
    import hashlib
    return hashlib.md5(texte.encode("utf-8", "replace")).hexdigest()[:12]


def paires_triees(table):
    """Parcours STABLE d'une table Lua. Sans tri, l'ordre change d'un appel à
    l'autre : la même entrée prenait alors deux signatures différentes et
    repartait indéfiniment (constaté : 2 entrées sur 33 revenaient)."""
    def cle(paire):
        try:
            return (0, float(paire[0]), "")
        except (TypeError, ValueError):
            return (1, 0.0, str(paire[0]))
    return sorted(table.items(), key=cle)


def aplatir(valeur, profondeur=0):
    """Rend une valeur lisible, même quand elle contient des tables imbriquées.

    Sans cela, une table dans une table s'écrivait « <Lua table at 0x...> » :
    le contenu du signalement était PERDU, et l'adresse mémoire changeant à
    chaque lecture, l'entrée paraissait toujours neuve."""
    if est_table(valeur):
        if profondeur >= 4:                # garde-fou anti-boucle
            return "…"
        return " / ".join(aplatir(v, profondeur + 1)
                          for _, v in paires_triees(valeur))
    return str(valeur)


def construire_rapport(jeu, deja=None):
    """Rapport texte au même format que le bouton « Copier pour partager »
    du jeu — les outils d'ingestion le lisent donc tel quel.

    `deja` = empreintes des entrées DÉJÀ envoyées, qu'on ne renvoie pas.
    Sans cette mémoire, l'addon gardant ses notes, le rapport repartait
    entier à chaque envoi et le compteur ne descendait jamais — le joueur
    croyait à juste titre que son envoi n'avait servi à rien.

    Rend (texte, nombre d'entrées NEUVES, empreintes de ces entrées).
    """
    deja = deja or set()
    neuves = []

    def neuve(bloc):
        """Vrai si l'entrée n'est jamais partie (et on la note au passage)."""
        signature = empreinte(bloc)
        if signature in deja or signature in neuves:
            return False
        neuves.append(signature)
        return True

    version = version_installee(jeu) or "?"
    blocs = ["Signalement Ascension FR — via le Compagnon",
             "AscensionFR " + version, ""]
    total = 0
    for numero, chemin in enumerate(fichiers_sauvegarde(jeu), 1):
        try:
            saved = lire_sauvegarde(chemin)
        except Exception:
            continue                       # sauvegarde illisible : on passe
        if saved is None:
            continue
        blocs.append("=== Compte %d ===" % numero)   # anonyme : pas de nom
        # 1) Notes laissées par le joueur (« Signaler un souci »).
        sig = saved["Signalements"]
        if est_table(sig):
            lignes, props = [], []
            for _, s in paires_triees(sig):
                champs = ({str(k): aplatir(v) for k, v in paires_triees(s)}
                          if est_table(s) else {})
                if champs.get("T") == "proposition":
                    # Proposition de traduction (fenêtre « Signaler ») : format
                    # PROPRE et parsable — sinon ingerer_rapport perd le texte
                    # proposé et il ne reste que l'ID.
                    ligne = ("- %s | %s | actuel=%s | propose=%s"
                             % (champs.get("cible", "?"),
                                champs.get("ID") or champs.get("nomCadre") or "",
                                champs.get("actuel", ""),
                                champs.get("P", "")))
                    if neuve(ligne):
                        props.append(ligne)
                    continue
                brut = (" | ".join(aplatir(x) for _, x in paires_triees(s))
                        if est_table(s) else str(s))
                ligne = "- " + brut
                if neuve(ligne):
                    lignes.append(ligne)
            if lignes:
                blocs.append("--- Signalements (%d) ---" % len(lignes))
                blocs += lignes
                total += len(lignes)
            if props:
                blocs.append("--- Propositions (%d) ---" % len(props))
                blocs += props
                total += len(props)
        # 2) Échecs d'alignement (le cœur : IDs + texte anglais affiché).
        echecs = saved["EchecsAlignement"]
        if est_table(echecs):
            for genre, table in paires_triees(echecs):
                if not est_table(table):
                    continue
                entrees = []
                for id_, texte in paires_triees(table):
                    corps = ["%s :" % id_]
                    if est_table(texte):
                        for _, ligne in paires_triees(texte):
                            corps.append("  " + aplatir(ligne))
                    else:
                        corps.append("  " + aplatir(texte))
                    bloc = "\n".join(corps)
                    if neuve(bloc):
                        entrees.append(bloc)
                if entrees:
                    blocs.append("--- Échecs d'alignement %s (%d) ---"
                                 % (genre, len(entrees)))
                    blocs += entrees
                    total += len(entrees)
        # 3) Récolte : textes rencontrés sans traduction.
        recolte = saved["Recolte"]
        if est_table(recolte):
            lignes = []
            for categorie, table in paires_triees(recolte):
                if est_table(table):
                    for cle, valeur in paires_triees(table):
                        ligne = "[%s] %s" % (categorie, cle)
                        # Le texte anglais récolté (quêtes surtout) part avec
                        # la ligne — un numéro seul est intraduisible.
                        if isinstance(valeur, str) and valeur:
                            ligne += " ==> " + valeur[:900]
                        if neuve(ligne):
                            lignes.append(ligne)
            if lignes:
                blocs.append("--- Récolte : rencontrés sans traduction (%d) ---"
                             % len(lignes))
                blocs += lignes
                total += len(lignes)
        blocs.append("")
    return "\n".join(blocs), total, neuves


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
ctk.set_appearance_mode("dark")


class Compagnon(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ascension FR — Compagnon")
        self.geometry("540x820")
        self.minsize(500, 720)
        self.configure(fg_color=FOND)
        try:
            self.iconbitmap(ressource("logo.ico"))
        except Exception:
            pass                            # sans icône, l'appli marche quand même

        self.cfg = charger_config()
        self.jeu = self.cfg.get("jeu")
        if not jeu_valide(self.jeu):
            self.jeu = chercher_jeu()
        self.derniere = None
        self.url_zip = None
        self.url_exe = None

        self._construire()
        self._rafraichir_jeu()
        self.after(300, self.verifier_version)
        self.after(600, self.rafraichir_stats)
        # Beaucoup de joueurs laissent le Compagnon ouvert derrière le jeu.
        # En revenant dessus après un /reload, le compteur doit refléter ce
        # qu'ils viennent de croiser, pas l'état d'il y a deux heures.
        self.dernier_coup_oeil = 0
        self.bind("<FocusIn>", self._au_retour)

    # --- mise en page (« launcher moderne » : sombre, plat, accent doré) --- #
    def _cadre(self, entete):
        """Un panneau plat à bordure discrète, en-tête en petites capitales."""
        cadre = ctk.CTkFrame(self, corner_radius=8, fg_color=PANNEAU,
                             border_width=1, border_color=LISERE)
        cadre.pack(fill="x", padx=24, pady=6)
        ctk.CTkLabel(cadre, text=entete.upper(), text_color=DISCRET,
                     font=ctk.CTkFont(size=11, weight="bold")
                     ).pack(anchor="w", padx=16, pady=(10, 0))
        return cadre

    def _bouton_principal(self, parent, texte, commande, **kw):
        """Le bouton d'action du launcher : doré, texte sombre."""
        options = dict(height=40, corner_radius=6,
                       fg_color=ACCENT, hover_color=ACCENT_SURVOL,
                       text_color=ENCRE_ACCENT,
                       font=ctk.CTkFont(size=14, weight="bold"),
                       command=commande)
        options.update(kw)
        return ctk.CTkButton(parent, text=texte, **options)

    def _image(self, nom, taille):
        """Charge une icône des assets. Rend None si elle manque : le
        Compagnon doit démarrer même sans ses images (chacun peut le
        reconstruire depuis la source)."""
        try:
            from PIL import Image
            fichier = Image.open(ressource(nom))
            return ctk.CTkImage(light_image=fichier, dark_image=fichier,
                                size=(taille, taille))
        except Exception:
            return None

    def _icone_lien(self, parent, base, url, libelle, taille=20):
        """Petite icône cliquable : atténuée au repos, pleine couleur au
        survol. Sans image disponible, on retombe sur un lien texte."""
        pale = self._image(base + "_pale.png", taille)
        vive = self._image(base + ".png", taille)
        if not (pale and vive):
            return self._lien(parent, libelle, url)
        lien = ctk.CTkLabel(parent, text="", image=pale, cursor="hand2")
        lien.bind("<Button-1>", lambda _: webbrowser.open(url))
        lien.bind("<Enter>", lambda _: lien.configure(image=vive))
        lien.bind("<Leave>", lambda _: lien.configure(image=pale))
        return lien

    def _lien(self, parent, texte, url, **kw):
        """Lien texte discret : ni cadre ni fond, il ne s'éclaire qu'au survol.
        Pour ce qui doit être accessible sans réclamer l'attention."""
        options = dict(font=ctk.CTkFont(size=11), text_color="#5a6068",
                       cursor="hand2")
        options.update(kw)
        repos = options["text_color"]
        lien = ctk.CTkLabel(parent, text=texte, **options)
        lien.bind("<Button-1>", lambda _: webbrowser.open(url))
        lien.bind("<Enter>", lambda _: lien.configure(text_color=ACCENT))
        lien.bind("<Leave>", lambda _: lien.configure(text_color=repos))
        return lien

    def _bouton_discret(self, parent, texte, commande, **kw):
        """Bouton secondaire : contour seul, fond transparent."""
        options = dict(height=36, corner_radius=6, fg_color="transparent",
                       hover_color=FANTOME_SURVOL, border_width=1,
                       border_color=FANTOME_BORD, text_color=TEXTE,
                       command=commande)
        options.update(kw)
        return ctk.CTkButton(parent, text=texte, **options)

    def _construire(self):
        # En-tête de launcher : chevron doré + nom. Pas de gros logo.
        entete = ctk.CTkFrame(self, fg_color="transparent")
        entete.pack(fill="x", padx=24, pady=(20, 12))
        ctk.CTkLabel(entete, text="⌃", text_color=ACCENT,
                     font=ctk.CTkFont(size=24, weight="bold")
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(entete, text="ASCENSION", text_color=TEXTE,
                     font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(entete, text=" FR", text_color=ACCENT,
                     font=ctk.CTkFont(size=17, weight="bold")
                     ).pack(side="left")
        ctk.CTkLabel(entete, text="Le jeu en français.",
                     text_color=DISCRET, font=ctk.CTkFont(size=12)
                     ).pack(side="right")

        # Bloc jeu
        bloc = self._cadre("Dossier du jeu")
        self.lbl_jeu = ctk.CTkLabel(bloc, text="…", justify="left",
                                    text_color=DISCRET)
        self.lbl_jeu.pack(anchor="w", padx=16)
        self._bouton_discret(bloc, "Changer…", self.choisir_jeu,
                             width=100, height=26
                             ).pack(anchor="e", padx=12, pady=(0, 10))

        # Bloc traduction
        bloc2 = self._cadre("Traduction")
        self.lbl_version = ctk.CTkLabel(bloc2, text="Vérification…",
                                        text_color=TEXTE)
        self.lbl_version.pack(anchor="w", padx=16)
        self.lbl_stats = ctk.CTkLabel(bloc2, text="", text_color=DISCRET,
                                      font=ctk.CTkFont(size=12))
        self.lbl_stats.pack(anchor="w", padx=16)
        self.btn_maj = self._bouton_principal(bloc2,
                                              "Vérifier les mises à jour",
                                              self.action_maj)
        self.btn_maj.pack(fill="x", padx=16, pady=(8, 12))
        # Affiché seulement quand une version plus récente du Compagnon
        # lui-même existe (le .exe ne peut pas se remplacer tout seul :
        # on emmène le joueur sur la page de téléchargement).
        self.lbl_maj_compagnon = ctk.CTkLabel(
            bloc2, text="⬆  Le Compagnon a aussi une nouvelle version — "
                        "clique ici : il se met à jour et redémarre tout seul",
            text_color=ACCENT, cursor="hand2",
            font=ctk.CTkFont(size=12, underline=True))
        self.lbl_maj_compagnon.bind("<Button-1>",
                                    lambda _: self.maj_compagnon())

        # Bloc contribution
        bloc3 = self._cadre("Contribuer")
        if WEBHOOK_RAPPORTS:
            aide = ("En jouant, l'addon note tout seul les textes encore\n"
                    "en anglais. Un clic, et ton rapport part aider la\n"
                    "traduction, avec les textes du jeu que tu as croisés\n"
                    "(quêtes, PNJ, objets — jamais rien de personnel).\n"
                    "(Déconnecte-toi ou /reload d'abord : le jeu\n"
                    "n'écrit le fichier qu'à ce moment-là.)")
        else:
            aide = ("En jouant, l'addon note tout seul les textes encore\n"
                    "en anglais. Copie ton rapport et colle-le sur le Discord.\n"
                    "(Déconnecte-toi ou /reload d'abord : le jeu n'écrit\n"
                    "le fichier qu'à ce moment-là.)")
        ctk.CTkLabel(bloc3, justify="left", text_color=DISCRET, text=aide
                     ).pack(anchor="w", padx=16)
        self.lbl_attente = ctk.CTkLabel(bloc3, text="",
                                        text_color=DISCRET,
                                        font=ctk.CTkFont(size=12))
        self.lbl_attente.pack(anchor="w", padx=16, pady=(4, 0))
        if WEBHOOK_RAPPORTS:
            self.btn_envoyer = self._bouton_principal(
                bloc3, "📨  Envoyer mon rapport", self.envoyer_rapport,
                height=38)
            self.btn_envoyer.pack(fill="x", padx=16, pady=(8, 4))
        ligne = ctk.CTkFrame(bloc3, fg_color="transparent")
        ligne.pack(fill="x", padx=16,
                   pady=((0, 12) if WEBHOOK_RAPPORTS else (8, 12)))
        self.btn_rapport = self._bouton_discret(ligne,
                                                "📋 Copier mon rapport",
                                                self.copier_rapport)
        self.btn_rapport.pack(side="left", expand=True, fill="x",
                              padx=(0, 6))
        # Discord : le logo seul, dans un carré au même trait que le bouton
        # voisin. Le pavé bleu vif attirait l'œil plus que l'action
        # principale — l'icône dit la même chose sans crier.
        logo = self._image("discord.png", 22)
        ctk.CTkButton(ligne, text="" if logo else "Discord", image=logo,
                      height=36, width=48 if logo else 110, corner_radius=6,
                      fg_color="transparent", hover_color=FANTOME_SURVOL,
                      border_width=1, border_color=FANTOME_BORD,
                      text_color=TEXTE,
                      command=lambda: webbrowser.open(DISCORD)
                      ).pack(side="left")

        # Bloc soutien — placé APRÈS « Contribuer » : on demande d'abord de
        # l'aide pour la traduction, l'argent ensuite, et jamais en doré (ce
        # ton est réservé à l'action principale).
        bloc4 = self._cadre("Soutenir le projet")
        ctk.CTkLabel(bloc4, justify="left", text_color=DISCRET,
                     text="La traduction est gratuite, et le restera.\n"
                          "Si elle te rend service, tu peux offrir un café\n"
                          "à celui qui la fait vivre. 💜"
                     ).pack(anchor="w", padx=16)
        self._bouton_discret(
            bloc4, "☕  Offrir un café au créateur",
            lambda: webbrowser.open(SOUTIEN),
            border_color=ACCENT, text_color=ACCENT
        ).pack(fill="x", padx=16, pady=(8, 6))

        # Réseaux : une simple ligne de texte, en tout petit. Volontairement
        # sans bouton ni logo — ce n'est pas ce que le joueur vient chercher.
        reseaux = ctk.CTkFrame(bloc4, fg_color="transparent")
        reseaux.pack(anchor="e", padx=16, pady=(4, 12))
        self._icone_lien(reseaux, "twitch", TWITCH, "Twitch"
                         ).pack(side="left", padx=(0, 12))
        self._icone_lien(reseaux, "youtube", YOUTUBE, "YouTube"
                         ).pack(side="left")

        # Barre d'état + pied de page
        self.lbl_etat = ctk.CTkLabel(self, text="", text_color=DISCRET)
        self.lbl_etat.pack(pady=(8, 0))
        pied = ctk.CTkLabel(self, text="Code source ouvert — github.com/"
                            + DEPOT, font=ctk.CTkFont(size=11),
                            text_color="#5a6068", cursor="hand2")
        pied.pack(side="bottom", pady=8)
        pied.bind("<Button-1>",
                  lambda _: webbrowser.open("https://github.com/" + DEPOT))

    # --- helpers ----------------------------------------------------------- #
    def etat(self, texte, couleur=DISCRET):
        self.lbl_etat.configure(text=texte, text_color=couleur)

    def _rafraichir_jeu(self):
        if jeu_valide(self.jeu):
            self.lbl_jeu.configure(text=self.jeu)
            self.cfg["jeu"] = self.jeu
            sauver_config(self.cfg)
        else:
            self.lbl_jeu.configure(
                text="Introuvable — clique sur « Changer… » et choisis le\n"
                     "dossier du jeu (celui qui contient « Interface »).")

    def choisir_jeu(self):
        from tkinter import filedialog
        choix = filedialog.askdirectory(title="Dossier du jeu Ascension "
                                        "(contient « Interface »)")
        if not choix:
            return
        choix = os.path.normpath(choix)
        # Tolérant : si on nous donne le dossier du launcher, on descend
        # nous-mêmes jusqu'au jeu.
        for essai in (choix,
                      os.path.join(choix, "resources", "ascension-live"),
                      os.path.join(choix, "resources", "client"),
                      os.path.join(choix, "ascension-live"),
                      os.path.join(choix, "client")):
            if jeu_valide(essai):
                self.jeu = essai
                self._rafraichir_jeu()
                self.verifier_version()
                return
        self.etat("Ce dossier ne contient pas « Interface ».", ORANGE)

    # --- statistiques ------------------------------------------------------ #
    def _au_retour(self, _evenement=None):
        """Fenêtre revenue au premier plan : on recompte, sans excès.

        Lire la sauvegarde coûte un vrai temps (fichier Lua volumineux) et
        l'événement se déclenche souvent : une relecture toutes les 10 s au
        plus suffit largement."""
        maintenant = time.time()
        if maintenant - self.dernier_coup_oeil < 10:
            return
        self.dernier_coup_oeil = maintenant
        self.rafraichir_stats()

    def rafraichir_stats(self):
        if not jeu_valide(self.jeu):
            return

        def travail():
            try:
                total, attente = lire_stats(self.jeu)
            except Exception:
                total, attente = None, 0
            self.after(0, lambda: self._montrer_stats(total, attente))
        threading.Thread(target=travail, daemon=True).start()

    def _montrer_stats(self, total, attente):
        if total:
            self.lbl_stats.configure(
                text="🇫🇷  %s textes français actifs sur ton jeu"
                     % format(total, ",").replace(",", " "))
        dernier = self.cfg.get("dernier_envoi")
        if attente > 0:
            texte = "%d entrée(s) prêtes à partir dans ton rapport" % attente
            if dernier:
                texte += "  ·  dernier envoi : %s" % dernier
            self.lbl_attente.configure(text=texte, text_color=ACCENT)
        elif dernier:
            self.lbl_attente.configure(
                text="Rien de nouveau à signaler  ·  dernier envoi : %s"
                     % dernier, text_color=DISCRET)

    # --- mise à jour ------------------------------------------------------- #
    def verifier_version(self):
        def travail():
            try:
                derniere, url, url_exe = derniere_release()
            except Exception:
                derniere, url, url_exe = None, None, None
            self.after(0, lambda: self._montrer_version(derniere, url,
                                                        url_exe))
        threading.Thread(target=travail, daemon=True).start()

    def _montrer_version(self, derniere, url, url_exe):
        self.derniere, self.url_zip = derniere, url
        self.url_exe = url_exe
        # Toute nouvelle vérification rend au bouton son rôle normal (il a pu
        # devenir « Relancer en administrateur » après un refus d'écriture).
        self.btn_maj.configure(command=self.action_maj)
        # Le Compagnon lui-même a-t-il une version plus récente ?
        if derniere and en_tuple(derniere) > en_tuple(VERSION_COMPAGNON):
            self.lbl_maj_compagnon.pack(anchor="w", padx=16, pady=(0, 10))
        installee = jeu_valide(self.jeu) and version_installee(self.jeu)
        if not jeu_valide(self.jeu):
            self.lbl_version.configure(text="Choisis d'abord le dossier du jeu.")
            return
        if not installee:
            self.lbl_version.configure(
                text="Traduction non installée — dernière version : "
                     + (derniere or "?"))
            self.btn_maj.configure(text="⬇️  Installer la traduction",
                                   fg_color=ACCENT,
                                   hover_color=ACCENT_SURVOL,
                                   text_color=ENCRE_ACCENT)
            return
        if derniere is None:
            self.lbl_version.configure(
                text="Installée : %s — impossible de joindre GitHub."
                     % installee)
            self.btn_maj.configure(text="Réessayer", fg_color=ACCENT,
                                   hover_color=ACCENT_SURVOL,
                                   text_color=ENCRE_ACCENT)
            return
        if mise_a_jour_dispo(installee, derniere):
            self.lbl_version.configure(
                text="Installée : %s   →   Disponible : %s"
                     % (installee, derniere))
            self.btn_maj.configure(text="⬇️  Mettre à jour",
                                   fg_color=ACCENT,
                                   hover_color=ACCENT_SURVOL,
                                   text_color=ENCRE_ACCENT)
            self.etat("Une nouvelle version est disponible !", VERT)
        else:
            self.lbl_version.configure(text="Installée : %s — à jour ✓"
                                       % installee)
            self.btn_maj.configure(text="✓  Tu es à jour",
                                   fg_color=FANTOME_SURVOL,
                                   hover_color=FANTOME_SURVOL,
                                   text_color=DISCRET)

    def action_maj(self):
        if not jeu_valide(self.jeu):
            self.etat("Choisis d'abord le dossier du jeu.", ORANGE)
            return
        # Garde-fou ATELIER : sur la machine du mainteneur, le jeu contient des
        # corrections pas encore publiées — réinstaller le zip de la release
        # les écraserait (vécu le 18/07/2026 : perte de 29 corrections,
        # récupérées de justesse). Les joueurs ne verront jamais ce message.
        if os.path.isdir(r"D:\AscensionFR\WorkFlow"):
            self.etat("Atelier de traduction détecté : installer la release "
                      "écraserait le travail en cours. Utilise le Collecteur "
                      "et les outils, pas ce bouton.", ORANGE)
            return
        if not self.url_zip:
            self.verifier_version()
            return
        self.btn_maj.configure(state="disabled", text="Téléchargement…")
        self.etat("Téléchargement de la version " + (self.derniere or ""))

        def montrer_progres(fait, total):
            if total > 0:
                texte = "Téléchargement… %d %%" % (fait * 100 // total)
            else:
                texte = "Téléchargement… %.1f Mo" % (fait / 1048576.0)
            self.after(0, lambda t=texte: self.btn_maj.configure(text=t))

        def travail():
            try:
                chemin = telecharger_fichier(self.url_zip, montrer_progres)
                self.after(0, lambda: self.btn_maj.configure(
                    text="Installation…"))
                installer_zip(chemin, self.jeu)
                self.after(0, self._maj_finie)
            except PermissionError:
                # Jeu installé dans un dossier protégé par Windows (Program
                # Files) : il faut les droits administrateur pour y écrire.
                # (2e signalement de Trey, jour du lancement.)
                self.after(0, self._demander_admin)
            except Exception as e:
                # err=e : la variable d'un « except » disparaît à la fin du
                # bloc ; une lambda qui la lit plus tard planterait en silence
                # et laisserait le bouton figé sur « Téléchargement… » (bug
                # signalé par Trey le jour du lancement).
                self.after(0, lambda err=e: self._maj_ratee(err))
        threading.Thread(target=travail, daemon=True).start()

    def _maj_finie(self):
        self.btn_maj.configure(state="normal")
        self.etat("Installé ! En jeu : /reload, ou reconnecte-toi. 🎉", VERT)
        self.verifier_version()

    def _maj_ratee(self, e):
        self.btn_maj.configure(state="normal", text="Réessayer")
        self.etat("Échec : %s" % e, ROUGE)

    def _demander_admin(self):
        self.btn_maj.configure(state="normal",
                               text="🛡  Relancer en administrateur",
                               command=self._relancer_admin)
        self.etat("Ton jeu est dans un dossier protégé par Windows (Program "
                  "Files) : il faut les droits administrateur pour y écrire.",
                  ORANGE)

    def _relancer_admin(self):
        """Redémarre l'appli avec les droits administrateur (fenêtre UAC de
        Windows), pour pouvoir écrire dans Program Files.

        Cette interface v2 n'est plus celle qui est distribuée (le Hub l'a
        remplacée), mais elle vit dans un fichier surveillé et le balayage du
        programme 23 l'a trouvée sans garde : `ctypes.windll` lève un
        AttributeError hors Windows. Un seul `except` plutôt qu'un défaut
        laissé derrière soi."""
        import ctypes
        if getattr(sys, "frozen", False):
            programme, arguments = sys.executable, ""
        else:                              # mode script (développement)
            programme = sys.executable
            arguments = '"%s"' % os.path.abspath(__file__)
        try:
            r = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", programme, arguments, None, 1)
        except Exception:
            r = 0                          # traité comme un refus, ci-dessous
        if r <= 32:                        # UAC refusé ou échec du lancement
            self.etat("Élévation refusée — tu peux aussi faire clic droit "
                      "sur le Compagnon → « Exécuter en tant "
                      "qu'administrateur ».", ORANGE)
            self.btn_maj.configure(text="🛡  Relancer en administrateur")
            return
        self.after(300, self.destroy)

    # --- auto-mise à jour du Compagnon lui-même ---------------------------- #
    def maj_compagnon(self):
        if not getattr(sys, "frozen", False) or not self.url_exe:
            # En mode script (développement) ou sans exe en release :
            # on emmène simplement sur la page de téléchargement.
            webbrowser.open(PAGE_RELEASES)
            return
        self.lbl_maj_compagnon.unbind("<Button-1>")
        self.lbl_maj_compagnon.configure(cursor="watch")

        def progres(fait, total):
            if total > 0:
                self.after(0, lambda p=fait * 100 // total:
                           self.lbl_maj_compagnon.configure(
                               text="⬇  Nouveau Compagnon… %d %%" % p))

        def travail():
            try:
                # La référence vient des MÉTADONNÉES de la release, pas du
                # fichier qu'on s'apprête à télécharger (programme 9).
                sha, taille = reference_asset(EXE_ATTENDU)
                nouveau = telecharger_fichier(self.url_exe, progres, ".exe",
                                              sha256_attendu=sha,
                                              taille_attendue=taille)
                self.after(0, lambda n=nouveau: self._redemarrer_avec(n))
            except Exception as e:
                self.after(0, lambda err=e: self._maj_compagnon_ratee(err))
        threading.Thread(target=travail, daemon=True).start()

    def _redemarrer_avec(self, nouveau):
        self.etat("Nouvelle version téléchargée — redémarrage…", VERT)
        lancer_remplacement(nouveau, sys.executable)
        # On laisse une demi-seconde à l'affichage, puis on se ferme : le
        # relais attend justement cette fermeture pour faire l'échange.
        self.after(500, self.destroy)

    def _maj_compagnon_ratee(self, err):
        self.lbl_maj_compagnon.configure(
            text="⬆  Mise à jour du Compagnon impossible — clique ici pour "
                 "la page de téléchargement", cursor="hand2")
        self.lbl_maj_compagnon.bind(
            "<Button-1>", lambda _: webbrowser.open(PAGE_RELEASES))
        self.etat("Échec : %s" % err, ROUGE)

    # --- rapport ----------------------------------------------------------- #
    def envoyer_rapport(self):
        """Envoie le rapport sur le salon Discord des rapports (webhook). En
        cas d'échec réseau, repli automatique : copie dans le presse-papiers."""
        if not jeu_valide(self.jeu):
            self.etat("Choisis d'abord le dossier du jeu.", ORANGE)
            return
        try:
            rapport, total, empreintes = construire_rapport(self.jeu,
                                                            deja_envoyees())
        except Exception as e:
            self.etat("Lecture impossible : %s" % e, ROUGE)
            return
        if total == 0:
            self.etat("Tout ce que tu avais est déjà parti — merci ! Rejoue "
                      "un peu, l'addon notera du nouveau. 💜", VERT)
            return
        self.btn_envoyer.configure(state="disabled", text="Envoi…")
        self.etat("Envoi du rapport…")

        def travail():
            try:
                # Les caches du jeu voyagent avec le rapport : c'est la matière
                # première des traducteurs. Jamais bloquant (None si souci).
                caches, _ = extraire_caches(self.jeu)
                envoyer_rapport_discord(rapport, caches)
                self.after(0, lambda: self._envoi_reussi(total, empreintes))
            except Exception:
                self.after(0, lambda: self._envoi_rate(rapport))
        threading.Thread(target=travail, daemon=True).start()

    def _rearmer_envoi(self):
        """Rend le bouton d'envoi utilisable après la confirmation.

        Sans cela il restait bloqué jusqu'à la fermeture de l'application : un
        joueur qui rejouait une heure devait fermer et rouvrir le Compagnon
        pour renvoyer son rapport. Personne ne devine ça."""
        if hasattr(self, "btn_envoyer"):
            self.btn_envoyer.configure(state="normal",
                                       text="📨  Envoyer mon rapport")

    def _envoi_reussi(self, total=0, empreintes=()):
        self.btn_envoyer.configure(text="✓  Rapport envoyé — merci !")
        # 5 s : le temps de lire la confirmation, puis le bouton se réarme.
        self.after(5000, self._rearmer_envoi)
        self.etat("Rapport envoyé (%d entrée(s)) ! Chaque rapport fait "
                  "avancer la traduction. 💜" % total, VERT)
        self.cfg["dernier_envoi"] = time.strftime("%d/%m/%Y")
        # Mémorisé : ces entrées ne repartiront plus, et le compteur retombe.
        noter_envoyees(self.cfg, empreintes)
        self.rafraichir_stats()

    def _envoi_rate(self, rapport):
        self.btn_envoyer.configure(state="normal",
                                   text="📨  Envoyer mon rapport")
        self.clipboard_clear()
        self.clipboard_append(rapport)
        self.etat("Envoi impossible (hors ligne ?) — rapport COPIÉ à la "
                  "place : colle-le sur le Discord.", ORANGE)

    def copier_rapport(self):
        if not jeu_valide(self.jeu):
            self.etat("Choisis d'abord le dossier du jeu.", ORANGE)
            return
        try:
            # Copie : on donne TOUT (même le déjà-envoyé). Le joueur peut
            # vouloir montrer son rapport complet, et rien ne prouve qu'il
            # collera — on ne marque donc rien comme parti.
            rapport, total, _ = construire_rapport(self.jeu)
        except Exception as e:
            self.etat("Lecture impossible : %s" % e, ROUGE)
            return
        if total == 0:
            self.etat("Rien à signaler pour l'instant — joue, l'addon note "
                      "tout seul ! (Ou fais /reload en jeu.)", ORANGE)
            return
        self.clipboard_clear()
        self.clipboard_append(rapport)
        self.etat("Rapport copié (%d entrées) ! Colle-le sur le Discord "
                  "(Ctrl+V). 💜" % total, VERT)


if __name__ == "__main__":
    Compagnon().mainloop()
