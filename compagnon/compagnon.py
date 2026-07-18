# -*- coding: utf-8 -*-
"""
Ascension FR — Compagnon
========================
Petite application OPTIONNELLE qui accompagne l'addon de traduction française
de Project Ascension (https://github.com/LePetitDan/AscensionFR) :

  1. vérifie si une nouvelle version de la traduction existe et l'installe
     en un clic (téléchargée depuis les releases GitHub officielles) ;
  2. prépare ton rapport de contribution (textes rencontrés en anglais,
     notés par l'addon dans ta sauvegarde) et le copie pour le Discord.

TRANSPARENCE : ce fichier est TOUT le programme. Il ne lit que le dossier du
jeu, n'écrit que les fichiers de l'addon, et ne contacte que api.github.com /
github.com (téléchargement des versions). Aucune donnée n'est envoyée nulle
part : le rapport est copié dans TON presse-papiers, c'est toi qui le colles.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile

import customtkinter as ctk

DEPOT = "LePetitDan/AscensionFR"
API_RELEASE = "https://api.github.com/repos/" + DEPOT + "/releases/latest"
PAGE_RELEASES = "https://github.com/" + DEPOT + "/releases"
# Version de CETTE application (alignée sur la release qui l'embarque). Quand
# une release plus récente sort, le Compagnon propose son propre remplacement
# (lien vers la page de téléchargement) en plus de mettre à jour l'addon.
VERSION_COMPAGNON = "1.4"

# Salon des rapports : URL du webhook Discord (fournie par le mainteneur).
# VIDE -> le bouton « Envoyer » n'existe pas, seul « Copier » reste (aucun
# envoi réseau). Quand il est renseigné, « Envoyer » poste le rapport en pièce
# jointe .txt dans le salon — le rapport ne contient QUE des textes du jeu et
# des numéros de sorts/objets, jamais d'information personnelle.
WEBHOOK_RAPPORTS = ""  # renseignée dans l'exe officiel au moment de sa construction
DISCORD = "https://discord.gg/kFJGDJbeay"
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
        candidats += [
            os.path.join(racine, "Program Files", "Ascension Launcher",
                         "resources", "ascension-live"),
            os.path.join(racine, "Ascension Launcher", "resources",
                         "ascension-live"),
            os.path.join(racine, "Ascension", "resources", "ascension-live"),
        ]
        try:
            for dossier in os.listdir(racine):
                candidats.append(os.path.join(racine, dossier, "resources",
                                              "ascension-live"))
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


def envoyer_rapport_discord(rapport):
    """Poste le rapport en pièce jointe .txt sur le salon des rapports (via le
    webhook). Lève en cas d'échec — l'appelant se replie alors sur la copie."""
    import uuid
    frontiere = "----AscensionFR" + uuid.uuid4().hex
    nom = "rapport_%s.txt" % uuid.uuid4().hex[:8]
    meta = json.dumps({"username": "Compagnon Ascension FR",
                       "content": "Nouveau rapport de contribution :"})
    corps = (
        "--%s\r\n"
        "Content-Disposition: form-data; name=\"payload_json\"\r\n"
        "Content-Type: application/json\r\n\r\n%s\r\n"
        "--%s\r\n"
        "Content-Disposition: form-data; name=\"files[0]\"; "
        "filename=\"%s\"\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n%s\r\n"
        "--%s--\r\n" % (frontiere, meta, frontiere, nom, rapport, frontiere)
    ).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_RAPPORTS, data=corps, method="POST",
        headers={"User-Agent": UA["User-Agent"],
                 "Content-Type": "multipart/form-data; boundary=" + frontiere})
    with urllib.request.urlopen(req, timeout=30):
        pass                               # 2xx = envoyé ; sinon une exception


def construire_rapport(jeu):
    """Rapport texte au même format que le bouton « Copier pour partager »
    du jeu — les outils d'ingestion le lisent donc tel quel."""
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
            for _, s in sig.items():
                if est_table(s):
                    s = " | ".join(str(x) for _, x in s.items())
                lignes.append("- " + str(s))
            if lignes:
                blocs.append("--- Signalements (%d) ---" % len(lignes))
                blocs += lignes
                total += len(lignes)
        # 2) Échecs d'alignement (le cœur : IDs + texte anglais affiché).
        echecs = saved["EchecsAlignement"]
        if est_table(echecs):
            for genre, table in echecs.items():
                if not est_table(table):
                    continue
                entrees = list(table.items())
                if not entrees:
                    continue
                blocs.append("--- Échecs d'alignement %s (%d) ---"
                             % (genre, len(entrees)))
                for id_, texte in entrees:
                    blocs.append("%s :" % id_)
                    if est_table(texte):
                        for _, ligne in texte.items():
                            blocs.append("  " + str(ligne))
                    else:
                        blocs.append("  " + str(texte))
                total += len(entrees)
        # 3) Récolte : textes rencontrés sans traduction.
        recolte = saved["Recolte"]
        if est_table(recolte):
            lignes = []
            for categorie, table in recolte.items():
                if est_table(table):
                    for cle, valeur in table.items():
                        lignes.append("[%s] %s" % (categorie, cle))
            if lignes:
                blocs.append("--- Récolte : rencontrés sans traduction (%d) ---"
                             % len(lignes))
                blocs += lignes
                total += len(lignes)
        blocs.append("")
    return "\n".join(blocs), total


# --------------------------------------------------------------------------- #
# Interface
# --------------------------------------------------------------------------- #
ctk.set_appearance_mode("dark")


class Compagnon(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ascension FR — Compagnon")
        self.geometry("540x640")
        self.minsize(500, 600)
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
                    "traduction. (Déconnecte-toi ou /reload d'abord : le jeu\n"
                    "n'écrit le fichier qu'à ce moment-là.)")
        else:
            aide = ("En jouant, l'addon note tout seul les textes encore\n"
                    "en anglais. Copie ton rapport et colle-le sur le Discord.\n"
                    "(Déconnecte-toi ou /reload d'abord : le jeu n'écrit\n"
                    "le fichier qu'à ce moment-là.)")
        ctk.CTkLabel(bloc3, justify="left", text_color=DISCRET, text=aide
                     ).pack(anchor="w", padx=16)
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
        ctk.CTkButton(ligne, text="💬 Discord", height=36, width=110,
                      corner_radius=6, fg_color="#5865F2",
                      hover_color="#4752C4",
                      command=lambda: webbrowser.open(DISCORD)
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
                      os.path.join(choix, "ascension-live")):
            if jeu_valide(essai):
                self.jeu = essai
                self._rafraichir_jeu()
                self.verifier_version()
                return
        self.etat("Ce dossier ne contient pas « Interface ».", ORANGE)

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
            rapport, total = construire_rapport(self.jeu)
        except Exception as e:
            self.etat("Lecture impossible : %s" % e, ROUGE)
            return
        if total == 0:
            self.etat("Rien à signaler pour l'instant — joue, l'addon note "
                      "tout seul ! (Ou fais /reload en jeu.)", ORANGE)
            return
        self.btn_envoyer.configure(state="disabled", text="Envoi…")
        self.etat("Envoi du rapport…")

        def travail():
            try:
                envoyer_rapport_discord(rapport)
                self.after(0, self._envoi_reussi)
            except Exception:
                self.after(0, lambda: self._envoi_rate(rapport))
        threading.Thread(target=travail, daemon=True).start()

    def _envoi_reussi(self):
        self.btn_envoyer.configure(text="✓  Rapport envoyé — merci !")
        self.etat("Rapport envoyé ! Chaque rapport fait avancer la "
                  "traduction. 💜", VERT)

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
            rapport, total = construire_rapport(self.jeu)
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
