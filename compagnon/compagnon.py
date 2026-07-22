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
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
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
# Version de CETTE application (alignée sur la release qui l'embarque). Quand
# une release plus récente sort, le Compagnon propose son propre remplacement
# (lien vers la page de téléchargement) en plus de mettre à jour l'addon.
VERSION_COMPAGNON = "2.1.1"

# Salon des rapports : URL du webhook Discord (fournie par le mainteneur).
# VIDE -> le bouton « Envoyer » n'existe pas, seul « Copier » reste (aucun
# envoi réseau). Quand il est renseigné, « Envoyer » poste le rapport en pièce
# jointe .txt dans le salon — le rapport ne contient QUE des textes du jeu et
# des numéros de sorts/objets, jamais d'information personnelle.
WEBHOOK_RAPPORTS = ""    # renseigné uniquement dans l'exe distribué
DISCORD = "https://discord.gg/kFJGDJbeay"
# Soutien au créateur. La traduction reste gratuite : le bouton est volontaire-
# ment secondaire (contour seul) pour ne pas concurrencer l'envoi de rapport.
SOUTIEN = "https://buymeacoffee.com/lepetitdan"
# Réseaux du créateur : de simples liens texte, jamais des boutons — ce n'est
# pas l'objet de l'application, ils ne doivent attirer l'œil que si on les
# cherche.
TWITCH = "https://www.twitch.tv/lepetitdan"
YOUTUBE = "https://www.youtube.com/@LePetitDan"
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

CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "AscensionFR")
CONFIG = os.path.join(CONFIG_DIR, "compagnon.json")


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


def chercher_jeu():
    """Essaie les emplacements habituels du launcher Ascension, puis balaie le
    premier niveau de chaque disque : le launcher peut être posé n'importe où,
    mais le jeu est toujours dans <dossier>\\resources\\ascension-live."""
    candidats = []
    for disque in "CDEFGH":
        racine = disque + ":\\"
        if not os.path.isdir(racine):
            continue
        # Deux dispositions vues en vrai : resources\ascension-live (ancienne)
        # et resources\client (celle du launcher actuel — vu chez un joueur).
        for fin in (("resources", "ascension-live"), ("resources", "client")):
            candidats += [
                os.path.join(racine, "Program Files", "Ascension Launcher",
                             *fin),
                os.path.join(racine, "Ascension Launcher", *fin),
                os.path.join(racine, "Ascension", *fin),
            ]
        try:
            for dossier in os.listdir(racine):
                candidats.append(os.path.join(racine, dossier, "resources",
                                              "ascension-live"))
                candidats.append(os.path.join(racine, dossier, "resources",
                                              "client"))
                candidats.append(os.path.join(racine, dossier,
                                              "ascension-live"))
        except OSError:
            pass
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidats.append(os.path.join(local, "Ascension Launcher",
                                      "resources", "ascension-live"))
    for c in candidats:
        if jeu_valide(c):
            return c
    return None


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


def en_tuple(version):
    return tuple(int(x) for x in re.findall(r"\d+", version or "0"))


def derniere_release():
    """(version, url_du_zip, url_de_l_exe) de la dernière release GitHub."""
    req = urllib.request.Request(API_RELEASE, headers=UA)
    with urllib.request.urlopen(req, timeout=20) as r:
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
    if vi >= (2, 0) and vd < (2, 0):
        return True
    return vd > vi


def telecharger_fichier(url, progres=None, suffixe=".zip"):
    """Télécharge un fichier de release dans un fichier temporaire ; rend le
    chemin. progres(fait, total) est appelé au fil de l'eau."""
    req = urllib.request.Request(url, headers=UA)
    fd, chemin = tempfile.mkstemp(suffix=suffixe, prefix="AscensionFR_")
    with urllib.request.urlopen(req, timeout=60) as r, \
            os.fdopen(fd, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        fait = 0
        while True:
            bloc = r.read(65536)
            if not bloc:
                break
            f.write(bloc)
            fait += len(bloc)
            if progres:
                progres(fait, total)
    return chemin


def installer_zip(chemin_zip, jeu):
    """Extrait le zip (structure Interface\\...) par-dessus le dossier du jeu."""
    with zipfile.ZipFile(chemin_zip) as z:
        z.extractall(jeu)
    os.remove(chemin_zip)


def lancer_remplacement(nouveau, cible):
    """Auto-mise à jour du Compagnon : un programme ne peut pas s'écraser
    lui-même pendant qu'il tourne. On confie donc l'échange à un minuscule
    script relais qui attend la fermeture de l'appli (tant que l'exe est
    verrouillé, « del » échoue), remplace l'ancien exe par le nouveau,
    relance, puis s'efface lui-même."""
    fd, bat = tempfile.mkstemp(suffix=".bat", prefix="AscensionFR_maj_")
    contenu = (
        "@echo off\r\n"
        ":attente\r\n"
        "timeout /t 1 /nobreak >nul\r\n"
        "del \"%s\" 2>nul\r\n"
        "if exist \"%s\" goto attente\r\n"
        "move /y \"%s\" \"%s\" >nul\r\n"
        # Respiration : l'antivirus inspecte l'exe tout juste écrit ; relancer
        # dans la même seconde peut échouer (« Failed to load Python DLL »).
        "timeout /t 4 /nobreak >nul\r\n"
        "start \"\" \"%s\"\r\n"
        "del \"%%~f0\"\r\n" % (cible, cible, nouveau, cible, cible))
    # mbcs : l'encodage des .bat sous Windows (chemins accentués compris).
    with os.fdopen(fd, "w", encoding="mbcs", errors="replace") as f:
        f.write(contenu)
    subprocess.Popen(["cmd", "/c", bat],
                     creationflags=0x08000000)      # CREATE_NO_WINDOW


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


ROYAUME_CIBLE = "conquest of azeroth"    # on ne collecte QUE ce royaume


def dossiers_caches(jeu):
    """Les dossiers de cache du royaume Conquest of Azeroth, toutes langues de
    client confondues : <jeu>\\Cache\\WDB\\<langue>\\<royaume>\\*.wdb."""
    base = os.path.join(jeu, "Cache", "WDB")
    trouves = []
    if os.path.isdir(base):
        for langue in sorted(os.listdir(base)):
            d = os.path.join(base, langue)
            if not os.path.isdir(d):
                continue
            for royaume in sorted(os.listdir(d)):
                r = os.path.join(d, royaume)
                if ROYAUME_CIBLE in royaume.lower() and os.path.isdir(r):
                    trouves.append(r)
    return trouves


def extraire_caches(jeu):
    """Extrait les textes anglais des caches du jeu (quêtes, PNJ, objets…)
    et les compresse. Rend (octets .json.gz, nombre d'entrées) ou (None, 0) :
    quoi qu'il arrive, le rapport part — au pire sans cette pièce jointe."""
    if parser_wdb is None:
        return None, 0
    try:
        fusion = {}
        for dossier in dossiers_caches(jeu):
            tmp = tempfile.mkdtemp(prefix="afr_caches_")
            try:
                parser_wdb.parse_dir(dossier, tmp)
                for f in os.listdir(tmp):
                    if not f.endswith(".json"):
                        continue
                    with open(os.path.join(tmp, f), encoding="utf-8") as g:
                        fusion.setdefault(f[:-5], {}).update(json.load(g))
            except Exception:
                pass                       # un cache abîmé n'empêche pas le reste
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
        total = sum(len(v) for v in fusion.values())
        if total == 0:
            return None, 0
        paquet = {"format": 1, "royaume": "Conquest of Azeroth",
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
    with urllib.request.urlopen(req, timeout=60):
        pass                               # 2xx = envoyé ; sinon une exception


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
            lignes = []
            for _, s in paires_triees(sig):
                if est_table(s):
                    s = " | ".join(aplatir(x) for _, x in paires_triees(s))
                ligne = "- " + str(s)
                if neuve(ligne):
                    lignes.append(ligne)
            if lignes:
                blocs.append("--- Signalements (%d) ---" % len(lignes))
                blocs += lignes
                total += len(lignes)
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
        if os.path.isdir(r"D:\WOW_Priv\traduction"):
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
        Windows), pour pouvoir écrire dans Program Files."""
        import ctypes
        if getattr(sys, "frozen", False):
            programme, arguments = sys.executable, ""
        else:                              # mode script (développement)
            programme = sys.executable
            arguments = '"%s"' % os.path.abspath(__file__)
        r = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", programme, arguments, None, 1)
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
                nouveau = telecharger_fichier(self.url_exe, progres, ".exe")
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
