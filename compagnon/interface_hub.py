# -*- coding: utf-8 -*-
"""
Ascension FR — le HUB (interface v3, paysage)
=============================================
L'évolution du Compagnon en Hub : une fenêtre « World of Warcraft » posée sur
le bureau (1080×680), avec une barre latérale de navigation et cinq vues —
Accueil, Traduction, Voix, Addons, Contribuer.

Mêmes principes que l'interface v2 :
  - toute la logique (versions, téléchargements, rapport, caches) vient de
    `compagnon.py`, inchangé ;
  - les décors sont des PNG fabriqués par `fabriquer_decor_hub.py` à partir
    des VRAIES textures du jeu (pack wow-ui-textures) et des polices
    officielles (Morpheus, Friz Quadrata) — ils vivent dans `assets/hub/` ;
  - les textes qui changent sont dessinés par le canvas avec ces mêmes
    polices, chargées en privé (rien n'est installé sur la machine).

La vue Addons est un catalogue en cartes piloté par
`assets/hub/catalogue_hub.json` : détection sur le disque (version du .toc),
et installation depuis une URL de release quand la fiche en a une.

Essai : `python interface_hub.py`
Captures : `python interface_hub.py --demo accueil --capture sortie.png`
"""
import ctypes
import json
import os
import re
import sys
import threading
import urllib.request
import webbrowser
import zipfile
import tempfile
import shutil

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog

from PIL import Image, ImageTk

import compagnon as logique

# --------------------------------------------------------------------------- #
# Plan de la fenêtre — la seule source des cotes, partagée avec
# `fabriquer_decor_hub.py` (qui importe ce dictionnaire).
# --------------------------------------------------------------------------- #
METRIQUE = {
    "W": 1080, "H": 680,
    # Barre latérale (panneau sombre)
    "SB_X": 22, "SB_Y": 22, "SB_W": 210, "SB_H": 636,
    "CRETE": 64, "Y_CRETE": 46,
    "Y_SOUS_CRETE": 122,
    "NAV_X": 33, "NAV_Y": 172, "NAV_W": 188, "NAV_H": 46, "NAV_PAS": 53,
    "BTN_LANCER_X": 33, "BTN_LANCER_Y": 542, "BTN_LANCER_W": 188,
    "BTN_LANCER_H": 46,
    "Y_RESEAUX": 596, "Y_LIENS": 648,
    # Zone de contenu (parchemin) : de CT_X au bord droit
    "CT_X": 232, "CT_W": 826,
    "CX": 262, "CW": 766,          # colonne interne du contenu
    "Y_TITRE": 62,
    "Y_ETAT": 606, "H_ETAT": 32, "ETAT_W": 766,
    # Fronton du haut
    "FRONTON_W": 430, "FRONTON_H": 107,
    # Boutons
    "BTN_L_W": 340, "BTN_L_H": 48,       # grands boutons d'action
    "BTN_M_W": 300, "BTN_M_H": 44,       # envoyer le rapport
    "BTN_C_W": 160, "BTN_C_H": 32,       # boutons des cartes d'addons
    "BTN_P_W": 110, "BTN_P_H": 30,       # petit bouton (Changer…)
    "BARRE_W": 560, "BARRE_H": 22,
    # Tuiles de l'accueil (3 côte à côte)
    "TUILE_W": 244, "TUILE_H": 96,
    # Cartes d'addons (2 colonnes)
    "CARTE_W": 372, "CARTE_H": 118,
    # Panneaux
    "PAN_OR_H": 310, "PAN_NOUV_H": 258, "PAN_LETTRE_H": 330,
}

DECOR_DOSSIER = "hub"                # sous assets/
MANIFESTE = "decor_hub.json"
CATALOGUE = "catalogue_hub.json"     # dans assets/hub/

# --------------------------------------------------------------------------- #
# Palette du Hub — l'encre sur parchemin, l'or de WoW sur le sombre.
# --------------------------------------------------------------------------- #
ENCRE = "#3d2b12"            # texte principal sur parchemin
ENCRE_DOUCE = "#5a4020"      # texte secondaire sur parchemin
OR_SOMBRE = "#8a6a2a"        # accents dorés lisibles sur parchemin
BEIGE = "#e9dcbb"            # texte sur les panneaux sombres
BEIGE_VIF = "#fff2cc"
OR_VIF = "#ffd100"           # l'or de WoW (accents sur sombre)
VERT = "#2f7f2a"
ORANGE = "#b8781f"
ROUGE = "#b23b1f"

TONALITES = {
    "neutre": "#4a3316",
    "alerte": "#6e4408",
    "erreur": "#7e1f10",
    "succes": "#1f5a1c",
}

# --------------------------------------------------------------------------- #
# Les états de la vue Traduction (repris de l'interface v2, adaptés).
# --------------------------------------------------------------------------- #
ETATS_TRAD = {
    "verification": {
        "titre": "Vérification…", "couleur": OR_SOMBRE,
        "sous": "Recherche de la dernière version…",
        "badge": False, "bouton": None, "ton": "neutre",
        "statut": "Vérification des mises à jour…"},
    "introuvable": {
        "titre": "Dossier introuvable", "couleur": ORANGE,
        "sous": "Choisis d'abord le dossier du jeu ci-dessous.",
        "badge": False, "bouton": None, "ton": "alerte",
        "statut": "Sélectionne le dossier de World of Warcraft pour "
                  "continuer."},
    "absente": {
        "titre": "Traduction non installée", "couleur": OR_SOMBRE,
        "sous": "Dernière version disponible : {vd}",
        "badge": False, "bouton": "btn_installer", "ton": "neutre",
        "statut": "Prêt à installer la version {vd}."},
    "ajour": {
        "titre": "Tu es à jour", "couleur": VERT,
        "sous": "Version {vi} installée",
        "badge": True, "bouton": "btn_fait", "ton": "succes",
        "statut": "Tout est à jour. Bon jeu !"},
    "maj": {
        "titre": "Mise à jour disponible", "couleur": OR_SOMBRE,
        "sous": "Installée : {vi}   →   Disponible : {vd}",
        "badge": False, "bouton": "btn_maj", "ton": "neutre",
        "statut": "Une nouvelle version de la traduction t'attend."},
    "injoignable": {
        "titre": "Serveur injoignable", "couleur": ROUGE,
        "sous": "Impossible de joindre GitHub. Vérifie ta connexion.",
        "badge": False, "bouton": "btn_reessayer", "ton": "erreur",
        "statut": "Impossible de vérifier les mises à jour."},
    "telechargement": {
        "titre": "Installation en cours…", "couleur": OR_SOMBRE,
        "sous": "Téléchargement de la version {vd}",
        "badge": False, "bouton": None, "ton": "neutre",
        "statut": "Téléchargement… ne ferme pas la fenêtre.",
        "progression": True},
    "protege": {
        "titre": "Dossier protégé", "couleur": ORANGE,
        "sous": "Windows empêche l'écriture ici. Relance en administrateur.",
        "badge": False, "bouton": "btn_admin", "ton": "alerte",
        "statut": "Droits administrateur requis pour ce dossier."},
    "reussie": {
        "titre": "Installation réussie", "couleur": VERT,
        "sous": "En jeu : tape /reload, ou reconnecte-toi.",
        "badge": True, "bouton": None, "ton": "succes",
        "statut": "Traduction installée. Amuse-toi bien !"},
}

ETATS_VOIX = {
    "absentes": {
        "titre": "Voix non installées", "couleur": OR_SOMBRE,
        "sous": "Un téléchargement d'environ 1,4 Go — une seule fois.",
        "bouton": "btn_voix", "bascule": None, "ton": "neutre",
        "statut": "Les voix françaises t'attendent."},
    "telechargement": {
        "titre": "Téléchargement des voix…", "couleur": OR_SOMBRE,
        "sous": "C'est volumineux : laisse la fenêtre ouverte.",
        "bouton": None, "bascule": None, "ton": "neutre",
        "statut": "Téléchargement des voix françaises…",
        "progression": True},
    "installees": {
        "titre": "Voix françaises installées", "couleur": VERT,
        "sous": "14 442 répliques d'époque. Reconnecte-toi si le jeu "
                "tournait pendant l'installation.",
        "bouton": "btn_voix_fait", "bascule": "btn_voix_couper",
        "ton": "succes",
        "statut": "Les personnages parlent français. Bon jeu !"},
    "coupees": {
        "titre": "Voix françaises coupées", "couleur": ORANGE,
        "sous": "Les fichiers sont gardés de côté — un clic les remet, "
                "rien à re-télécharger.",
        "bouton": None, "bascule": "btn_voix_remettre", "ton": "alerte",
        "statut": "Les voix sont coupées : le jeu parle anglais."},
    "erreur": {
        "titre": "Téléchargement interrompu", "couleur": ROUGE,
        "sous": "Vérifie ta connexion, puis réessaie.",
        "bouton": "btn_voix", "bascule": None, "ton": "erreur",
        "statut": "Le téléchargement des voix a échoué."},
}

# La bascule renomme le dossier Sound du jeu (les voix SONT des fichiers ;
# un addon ne peut pas le faire, l'application si — jeu fermé).
DOSSIER_VOIX_COUPEES = "Sound_off"


# --------------------------------------------------------------------------- #
# Polices : Morpheus et Friz Quadrata, chargées pour CETTE application
# seulement (FR_PRIVATE — rien n'est installé, rien ne survit).
# --------------------------------------------------------------------------- #
POLICES_HUB = ("MORPHEUS.TTF", "FRIZQT__.TTF")
FR_PRIVATE = 0x10


def charger_polices():
    for nom in POLICES_HUB:
        chemin = logique.ressource(os.path.join("hub", "fonts", nom))
        if os.path.isfile(chemin):
            try:
                ctypes.windll.gdi32.AddFontResourceExW(chemin, FR_PRIVATE, 0)
            except Exception:
                pass


def police_dispo(nom, repli):
    try:
        return nom if nom in tkfont.families() else repli
    except Exception:
        return repli


# --------------------------------------------------------------------------- #
# Décors : PNG + manifeste de cotes (même mécanique que l'interface v2).
# --------------------------------------------------------------------------- #
class Decor:
    def __init__(self):
        self.dossier = logique.ressource(DECOR_DOSSIER)
        with open(os.path.join(self.dossier, MANIFESTE),
                  encoding="utf-8") as f:
            self.manifeste = json.load(f)
        self._photos = {}
        self._pil = {}

    def existe(self, nom):
        return nom in self.manifeste and os.path.isfile(
            os.path.join(self.dossier, nom + ".png"))

    def pil(self, nom):
        if nom not in self._pil:
            self._pil[nom] = Image.open(
                os.path.join(self.dossier, nom + ".png")).convert("RGBA")
        return self._pil[nom]

    def photo(self, nom):
        if nom not in self._photos:
            self._photos[nom] = ImageTk.PhotoImage(self.pil(nom))
        return self._photos[nom]

    def pad(self, nom):
        return self.manifeste.get(nom, {}).get("pad", 0)

    def poser(self, canvas, nom, x, y, **kw):
        """Pose l'élément pour que son coin haut-gauche (hors ombre) soit à
        (x, y) — la marge du PNG est déduite automatiquement."""
        p = self.pad(nom)
        return canvas.create_image(x - p, y - p, anchor="nw",
                                   image=self.photo(nom), **kw)


class BoutonImage:
    """Bouton dessiné sur le canvas : image au repos, image de survol,
    enfoncement de 2 px au clic, état désactivé (image grise, sans action)."""

    def __init__(self, app, nom, x, y, commande=None, tags=()):
        self.app, self.canvas, self.decor = app, app.canvas, app.decor
        self.x, self.y = x, y
        self.commande = commande
        self.nom = None
        self.actif = True
        self.survole = False
        self.enfonce = False
        self.item = self.canvas.create_image(0, 0, anchor="nw", tags=tags)
        self.canvas.tag_bind(self.item, "<Enter>", self._entree)
        self.canvas.tag_bind(self.item, "<Leave>", self._sortie)
        self.canvas.tag_bind(self.item, "<ButtonPress-1>", self._presse)
        self.canvas.tag_bind(self.item, "<ButtonRelease-1>", self._relache)
        self.configurer(nom, commande)

    def configurer(self, nom, commande=None, actif=True):
        self.nom = nom
        if commande is not None:
            self.commande = commande
        self.actif = actif
        self.enfonce = False
        self._peindre()

    def deplacer(self, x, y):
        self.x, self.y = x, y
        self._peindre()

    def cacher(self):
        self.canvas.itemconfigure(self.item, state="hidden")

    def montrer(self):
        self.canvas.itemconfigure(self.item, state="normal")

    def _image_courante(self):
        if self.actif and self.survole and self.decor.existe(
                self.nom + "_survol"):
            return self.nom + "_survol"
        return self.nom

    def _peindre(self):
        nom = self._image_courante()
        decal = 2 if self.enfonce else 0
        self.canvas.itemconfigure(self.item, image=self.decor.photo(nom))
        self.canvas.coords(self.item, self.x - self.decor.pad(nom),
                           self.y - self.decor.pad(nom) + decal)

    def _entree(self, _e=None):
        self.survole = True
        if self.actif:
            self.canvas.configure(cursor="hand2")
        self._peindre()

    def _sortie(self, _e=None):
        self.survole = False
        self.enfonce = False
        self.canvas.configure(cursor="")
        self._peindre()

    def _presse(self, _e=None):
        if not self.actif:
            return
        self.enfonce = True
        self._peindre()

    def _relache(self, _e=None):
        if not self.actif or not self.enfonce:
            return
        self.enfonce = False
        self._peindre()
        if self.commande:
            self.commande()


# --------------------------------------------------------------------------- #
# Aides addons : lecture de version d'un .toc quelconque, installation d'un
# zip de release dans Interface\AddOns.
# --------------------------------------------------------------------------- #
def version_toc(jeu, dossier):
    """« ## Version: x.y » du .toc d'un addon installé. None si absent."""
    base = os.path.join(jeu, "Interface", "AddOns", dossier)
    toc = os.path.join(base, dossier + ".toc")
    if not os.path.isfile(toc):
        return None
    try:
        with open(toc, encoding="utf-8", errors="replace") as f:
            for ligne in f:
                m = re.match(r"##\s*Version:\s*(\S+)", ligne)
                if m:
                    return m.group(1)
    except OSError:
        return None
    return "?"                       # installé, version non déclarée


def installer_addon_zip(chemin_zip, jeu, dossier):
    """Déballe un zip d'addon dans Interface\\AddOns\\<dossier>. Le zip peut
    contenir le dossier à sa racine, ou (archive GitHub) un dossier
    intermédiaire « Depot-branche/ » : on cherche le .toc et on re-racine."""
    addons = os.path.join(jeu, "Interface", "AddOns")
    tampon = tempfile.mkdtemp(prefix="AscensionFR_addon_")
    try:
        with zipfile.ZipFile(chemin_zip) as z:
            z.extractall(tampon)
        source = None
        for racine, _dossiers, fichiers in os.walk(tampon):
            for f in fichiers:
                if f.lower() == (dossier + ".toc").lower():
                    source = racine
                    break
            if source:
                break
        if not source:
            raise ValueError("le zip ne contient pas " + dossier + ".toc")
        cible = os.path.join(addons, dossier)
        if os.path.isdir(cible):
            shutil.rmtree(cible)
        shutil.copytree(source, cible)
    finally:
        shutil.rmtree(tampon, ignore_errors=True)


def _candidats_registre():
    """Emplacements du launcher Ascension notés dans le registre Windows
    (clés de désinstallation). LECTURE seule, jamais d'écriture."""
    import winreg
    bases = []
    coins = ((winreg.HKEY_CURRENT_USER,
              r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE,
              r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
             (winreg.HKEY_LOCAL_MACHINE,
              r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion"
              r"\Uninstall"))
    for racine, chemin in coins:
        try:
            base = winreg.OpenKey(racine, chemin)
        except OSError:
            continue
        with base:
            for i in range(winreg.QueryInfoKey(base)[0]):
                try:
                    with winreg.OpenKey(base, winreg.EnumKey(base, i)) as cle:
                        def valeur(nom):
                            try:
                                return str(winreg.QueryValueEx(cle, nom)[0])
                            except OSError:
                                return ""
                        if "ascension" not in valeur("DisplayName").lower():
                            continue
                        for v in (valeur("InstallLocation"),
                                  os.path.dirname(valeur("DisplayIcon"))):
                            v = v.strip().strip('"')
                            if v:
                                bases.append(v)
                except OSError:
                    continue
    return bases


# --------------------------------------------------------------------------- #
# L'application
# --------------------------------------------------------------------------- #
VUES = ("accueil", "traduction", "voix", "addons", "contribuer")

M = METRIQUE


class Hub(tk.Tk):
    def __init__(self, demo=None):
        super().__init__()
        self.demo = demo
        self.title("AscensionFR — Hub")
        self.resizable(False, False)
        self.configure(bg="#0a0a0c")
        try:
            self.iconbitmap(logique.ressource("logo.ico"))
        except Exception:
            pass
        charger_polices()
        self.decor = Decor()
        self.canvas = tk.Canvas(self, width=M["W"], height=M["H"],
                                bg="#0a0a0c", highlightthickness=0)
        self.canvas.pack()

        # Polices tk (le nom réel des TTF du jeu, avec repli sûr)
        morpheus = police_dispo("Morpheus", "Georgia")
        friz = police_dispo("Friz Quadrata TT", "Georgia")
        self.p_titre = tkfont.Font(family=morpheus, size=-30, weight="bold")
        self.p_gros = tkfont.Font(family=morpheus, size=-26, weight="bold")
        self.p_nombre = tkfont.Font(family=morpheus, size=-25, weight="bold")
        self.p_soustitre = tkfont.Font(family=friz, size=-17)
        self.p_corps = tkfont.Font(family=friz, size=-15)
        self.p_petit = tkfont.Font(family=friz, size=-13)
        self.p_mini = tkfont.Font(family=friz, size=-12)
        self.p_nom_carte = tkfont.Font(family=friz, size=-16, weight="bold")
        self.p_lien = tkfont.Font(family=friz, size=-13, underline=True)

        # Données vivantes
        self.cfg = logique.charger_config()
        self.jeu = self.cfg.get("jeu")
        if not logique.jeu_valide(self.jeu):
            self.jeu = logique.chercher_jeu()
            if self.jeu:
                self.cfg["jeu"] = self.jeu
                logique.sauver_config(self.cfg)
        self.version_locale = (logique.version_installee(self.jeu)
                               if logique.jeu_valide(self.jeu) else None)
        self.version_dispo = None
        self.url_zip = None
        self.url_exe = None          # nouvel exe de l'application, si publié
        self.appli_en_retard = False
        self.note = None             # patch-note (markdown brut)
        self.stats = (None, 0)       # (total traduit, en attente d'envoi)
        self.catalogue = self._charger_catalogue()
        self.versions_distantes = {}  # id -> tag de la dernière release

        # Construction
        self.decor.poser(self.canvas, "fond", 0, 0)
        self._construire_navigation()
        self._construire_lancement()
        self._construire_etat()
        self._construire_accueil()
        self._construire_traduction()
        self._construire_voix()
        self._construire_addons()
        self._construire_contribuer()
        self.vue = None
        self.montrer_vue("accueil")

        # Premiers rafraîchissements (réseau et lecture disque en fil)
        if demo:
            self._peupler_demo()
        else:
            self.verifier()
            self._fil(self._lire_stats)
            self._fil(self._verifier_addons_fond)
        self.rafraichir_voix()
        self.rafraichir_addons()

    # ------------------------------------------------------------------ outils
    def _charger_catalogue(self):
        try:
            with open(os.path.join(logique.ressource(DECOR_DOSSIER),
                                   CATALOGUE), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return []

    def _fil(self, fonction, *args):
        threading.Thread(target=fonction, args=args, daemon=True).start()

    def _sur_canvas(self, fonction, *args):
        """Repasse par le fil de l'interface (les fils réseau ne touchent
        jamais le canvas directement)."""
        self.after(0, lambda: fonction(*args))

    def statut(self, ton, texte):
        for t in TONALITES:
            self.canvas.itemconfigure("etat_" + t, state="hidden")
        self.canvas.itemconfigure("etat_" + ton, state="normal")
        self.canvas.itemconfigure(self.txt_etat, text=texte,
                                  fill=TONALITES[ton])
        self.canvas.tag_raise(self.txt_etat)

    # ------------------------------------------------------- barre latérale
    def _construire_navigation(self):
        self.nav = {}
        for i, vue in enumerate(VUES):
            y = M["NAV_Y"] + i * M["NAV_PAS"]
            item = self.canvas.create_image(
                M["NAV_X"], y, anchor="nw",
                image=self.decor.photo("nav_" + vue))
            self.nav[vue] = item
            for seq, fn in (("<Enter>", self._nav_entree),
                            ("<Leave>", self._nav_sortie),
                            ("<Button-1>", self._nav_clic)):
                self.canvas.tag_bind(item, seq,
                                     lambda e, v=vue, f=fn: f(v))

    def _nav_entree(self, vue):
        if vue != self.vue:
            self.canvas.itemconfigure(
                self.nav[vue], image=self.decor.photo("nav_%s_survol" % vue))
        self.canvas.configure(cursor="hand2")

    def _nav_sortie(self, vue):
        etat = "actif" if vue == self.vue else None
        nom = "nav_%s_%s" % (vue, etat) if etat else "nav_" + vue
        self.canvas.itemconfigure(self.nav[vue], image=self.decor.photo(nom))
        self.canvas.configure(cursor="")

    def _nav_clic(self, vue):
        self.montrer_vue(vue)

    def montrer_vue(self, vue):
        if vue == self.vue:
            return
        self.vue = vue
        for v in VUES:
            self.canvas.itemconfigure(
                self.nav[v],
                image=self.decor.photo("nav_%s%s" % (
                    v, "_actif" if v == vue else "")))
            etat = "normal" if v == vue else "hidden"
            self.canvas.itemconfigure("vue_" + v, state=etat)
            for bouton in getattr(self, "boutons_" + v, ()):
                (bouton.montrer if v == vue else bouton.cacher)()
        # chaque vue rétablit ses propres boutons conditionnels
        if vue == "traduction":
            self.appliquer_trad(self.etat_trad, remontrer=True)
        elif vue == "voix":
            self.rafraichir_voix()
        elif vue == "addons":
            self.rafraichir_addons()
        elif vue == "contribuer":
            self.rafraichir_contrib()
        elif vue == "accueil":
            self.rafraichir_accueil()
        self.canvas.tag_raise("etat_boite")
        self.canvas.tag_raise(self.txt_etat)

    # --------------------------------------------------------- barre d'état
    def _construire_etat(self):
        for ton in TONALITES:
            self.decor.poser(self.canvas, "etat_" + ton, M["CX"], M["Y_ETAT"],
                             tags=("etat_" + ton, "etat_boite"))
            self.canvas.itemconfigure("etat_" + ton, state="hidden")
        self.txt_etat = self.canvas.create_text(
            M["CX"] + 30, M["Y_ETAT"] + M["H_ETAT"] // 2, anchor="w",
            font=self.p_corps, fill=TONALITES["neutre"], text="")
        self.canvas.itemconfigure("etat_neutre", state="normal")
        self.canvas.itemconfigure(self.txt_etat, text="Bienvenue.")

    # ---------------------------------------------------- liens et lancement
    def _construire_lancement(self):
        self.btn_lancer = BoutonImage(
            self, "btn_lancer", M["BTN_LANCER_X"], M["BTN_LANCER_Y"],
            commande=self.lancer_jeu)
        # Discord et café : les habillages du Compagnon v2 (demande de Dan,
        # 23/07), côte à côte sous le bouton de lancement.
        l_discord = self.decor.manifeste["btn_discord"]["w"]
        l_cafe = self.decor.manifeste["btn_cafe"]["w"]
        x0 = M["SB_X"] + (M["SB_W"] - l_discord - 2 - l_cafe) // 2
        self.btn_discord = BoutonImage(
            self, "btn_discord", x0, M["Y_RESEAUX"],
            commande=lambda: webbrowser.open(logique.DISCORD))
        self.btn_cafe = BoutonImage(
            self, "btn_cafe", x0 + l_discord + 2, M["Y_RESEAUX"],
            commande=lambda: webbrowser.open(logique.SOUTIEN))
        centre = M["SB_X"] + M["SB_W"] // 2
        item = self.canvas.create_text(
            centre, M["Y_LIENS"], text="Code source ouvert ↗",
            font=self.p_mini, fill="#b79a76")
        self.canvas.tag_bind(
            item, "<Button-1>",
            lambda e: webbrowser.open("https://github.com/" + logique.DEPOT))
        self.canvas.tag_bind(
            item, "<Enter>", lambda e: (
                self.canvas.itemconfigure(item, fill=BEIGE_VIF),
                self.canvas.configure(cursor="hand2")))
        self.canvas.tag_bind(
            item, "<Leave>", lambda e: (
                self.canvas.itemconfigure(item, fill="#b79a76"),
                self.canvas.configure(cursor="")))

    def lancer_jeu(self):
        """Lance le LAUNCHER d'Ascension (choix de Dan, 23/07) : c'est lui
        qui vérifie les fichiers du jeu avant de jouer. L'exe du jeu ne sert
        que de secours si aucun launcher n'est trouvable."""
        candidats = []
        # Le launcher vit deux dossiers au-dessus du jeu :
        # <launcher>\resources\ascension-live (ou \client).
        if self.jeu:
            base = os.path.dirname(os.path.dirname(self.jeu))
            candidats.append(base)
        candidats += _candidats_registre()
        for base in candidats:
            launcher = os.path.join(base, "Ascension Launcher.exe")
            if os.path.isfile(launcher):
                try:
                    os.startfile(launcher)
                    self.statut("succes", "Le launcher Ascension se lance. "
                                          "Bon voyage !")
                    return
                except OSError:
                    pass
        exe = os.path.join(self.jeu or "", "Ascension.exe")
        if self.jeu and os.path.isfile(exe):
            try:
                os.startfile(exe)
                self.statut("succes", "Launcher introuvable — le jeu se "
                                      "lance directement.")
                return
            except OSError:
                pass
        self.statut("erreur", "Impossible de trouver le launcher ou le jeu. "
                              "Vérifie le dossier dans l'onglet Traduction.")

    # ------------------------------------------------------------- ACCUEIL
    def _construire_accueil(self):
        t = ("vue_accueil",)
        c, cx = self.canvas, M["CX"]
        c.create_text(cx, M["Y_TITRE"], anchor="w", text="Accueil",
                      font=self.p_titre, fill=ENCRE, tags=t)
        # Grand état général
        self.acc_badge = self.decor.poser(c, "badge_ok", cx + 2, 96, tags=t)
        self.acc_etat = c.create_text(cx + 74, 124, anchor="w",
                                      text="Vérification…",
                                      font=self.p_gros, fill=OR_SOMBRE,
                                      tags=t)
        # Trois tuiles
        y = 170
        libelles = ("Textes traduits", "Voix françaises", "Ta contribution")
        self.acc_valeurs = []
        for i, libelle in enumerate(libelles):
            x = cx + i * (M["TUILE_W"] + 17)
            self.decor.poser(c, "tuile", x, y, tags=t)
            c.create_text(x + M["TUILE_W"] // 2, y + 26, text=libelle,
                          font=self.p_petit, fill=ENCRE_DOUCE, tags=t)
            self.acc_valeurs.append(c.create_text(
                x + M["TUILE_W"] // 2, y + 60, text="—",
                font=self.p_nombre, fill=ENCRE, tags=t))
        # Dernières nouvelles
        y = 300
        self.decor.poser(c, "panneau_nouvelles", cx, y, tags=t)
        c.create_text(cx + 24, y + 30, anchor="w",
                      text="Dernières nouvelles", font=self.p_gros,
                      fill=ENCRE, tags=t)
        self.acc_note = c.create_text(
            cx + 24, y + 58, anchor="nw", text="Chargement du patch-note…",
            font=self.p_corps, fill=ENCRE_DOUCE, width=M["CW"] - 48, tags=t)
        lien = c.create_text(cx + M["CW"] - 24, y + 30, anchor="e",
                             text="Tout lire ↗", font=self.p_lien,
                             fill=OR_SOMBRE, tags=t)
        c.tag_bind(lien, "<Button-1>",
                   lambda e: webbrowser.open(logique.PAGE_RELEASES))
        self.boutons_accueil = ()

    def rafraichir_accueil(self):
        c = self.canvas
        # État général : traduction + dossier
        if not logique.jeu_valide(self.jeu):
            texte, coul, badge = "Choisis le dossier du jeu", ORANGE, False
        elif self.etat_trad == "ajour":
            texte, coul, badge = "Tout est à jour", VERT, True
        elif self.etat_trad == "maj":
            texte, coul, badge = "Une mise à jour t'attend", OR_SOMBRE, False
        elif self.etat_trad == "absente":
            texte, coul, badge = "Traduction à installer", OR_SOMBRE, False
        elif self.etat_trad == "injoignable":
            texte, coul, badge = "Serveur injoignable", ROUGE, False
        else:
            texte, coul, badge = "Vérification…", OR_SOMBRE, False
        c.itemconfigure(self.acc_etat, text=texte, fill=coul)
        c.itemconfigure(self.acc_badge,
                        state="normal" if badge else "hidden")
        # Tuiles
        c.itemconfigure(self.acc_valeurs[0], text="≈ 670 000")
        voix = self._etat_voix_disque()
        c.itemconfigure(self.acc_valeurs[1],
                        text={"installees": "Installées ✓",
                              "coupees": "Coupées",
                              "absentes": "À installer"}[voix],
                        fill={"installees": VERT, "coupees": ORANGE,
                              "absentes": ENCRE}[voix])
        total = self.stats[0]
        c.itemconfigure(self.acc_valeurs[2],
                        text="{:,}".format(total).replace(",", " ")
                        if total else "—")
        # Patch-note
        if self.note is not None:
            c.itemconfigure(self.acc_note, text=self._resumer_note())

    def _resumer_note(self):
        """Le patch-note GitHub (markdown), aplati en quelques lignes."""
        lignes = []
        for brute in (self.note or "").splitlines():
            ligne = brute.strip()
            if not ligne or ligne.startswith(("```", "|", "![", "<")):
                continue
            ligne = re.sub(r"^#+\s*", "", ligne)
            ligne = re.sub(r"^[-*]\s+", "• ", ligne)
            ligne = re.sub(r"\*\*([^*]+)\*\*", r"\1", ligne)
            ligne = re.sub(r"\*([^*]+)\*", r"\1", ligne)
            ligne = re.sub(r"`([^`]+)`", r"\1", ligne)
            ligne = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", ligne)
            # Friz Quadrata ne connaît pas les émojis : on les retire
            # (au-delà des flèches, tout sort en glyphe cassé).
            ligne = "".join(ch for ch in ligne if ord(ch) < 0x2190).strip()
            if not ligne:
                continue
            lignes.append(ligne)
            if len(lignes) >= 8:
                break
        return "\n".join(lignes) if lignes else "Pas encore de nouvelles."

    # ----------------------------------------------------------- TRADUCTION
    def _construire_traduction(self):
        t = ("vue_traduction",)
        c, cx = self.canvas, M["CX"]
        c.create_text(cx, M["Y_TITRE"], anchor="w", text="Traduction",
                      font=self.p_titre, fill=ENCRE, tags=t)
        y = self.y_pan_or = 96
        self.decor.poser(c, "panneau_or", cx, y, tags=t)
        centre = cx + M["CW"] // 2
        self.trad_titre = c.create_text(centre, y + 62, text="Vérification…",
                                        font=self.p_gros, fill=OR_SOMBRE,
                                        tags=t)
        self.trad_sous = c.create_text(centre, y + 96, text="",
                                       font=self.p_soustitre,
                                       fill=ENCRE_DOUCE, tags=t)
        self.trad_badge = self.decor.poser(
            c, "badge_ok", cx + M["CW"] - 92, y + 34, tags=t)
        c.itemconfigure(self.trad_badge, state="hidden")
        # Bouton principal + barre de progression (au même endroit)
        self.y_action = y + 138
        self.btn_trad = BoutonImage(
            self, "btn_fait", centre - M["BTN_L_W"] // 2, self.y_action,
            tags=t)
        self.btn_trad.cacher()
        self.barre_trad = self._construire_barre(centre, self.y_action + 12,
                                                 t)
        self.trad_verse = c.create_text(
            centre, self.y_action + 52, text="", font=self.p_petit,
            fill=ENCRE_DOUCE, tags=t)
        # Dossier du jeu, sous le panneau
        y2 = y + M["PAN_OR_H"] + 34
        c.create_text(cx, y2, anchor="w", text="Dossier du jeu :",
                      font=self.p_corps, fill=ENCRE, tags=t)
        self.trad_dossier = c.create_text(
            cx + 118, y2, anchor="w", text="—", font=self.p_petit,
            fill=ENCRE_DOUCE, width=M["CW"] - 260, tags=t)
        self.btn_changer = BoutonImage(
            self, "btn_changer", cx + M["CW"] - M["BTN_P_W"],
            y2 - M["BTN_P_H"] // 2, commande=self.changer_dossier, tags=t)
        # Mise à jour de l'APPLICATION elle-même : le Hub remplace le
        # Compagnon (décision de Dan, 23/07), il doit donc porter la même
        # chaîne d'auto-mise à jour que lui.
        self.lien_appli = c.create_text(
            cx, y2 + 30, anchor="w",
            text="Une nouvelle version de l'application est disponible — "
                 "cliquer ici pour l'installer.",
            font=self.p_lien, fill=OR_SOMBRE, tags=t)
        c.itemconfigure(self.lien_appli, state="hidden")
        c.tag_bind(self.lien_appli, "<Button-1>",
                   lambda e: self.mettre_a_jour_appli())
        self.boutons_traduction = (self.btn_trad, self.btn_changer)
        self.etat_trad = "verification"

    def _construire_barre(self, centre, y, tags):
        """Barre de progression : rail creux + bande dorée recadrée."""
        rail = self.decor.poser(self.canvas, "barre_creuse",
                                centre - M["BARRE_W"] // 2, y, tags=tags)
        bande = self.canvas.create_image(
            centre - M["BARRE_W"] // 2 + 2, y + 2, anchor="nw", tags=tags)
        pct = self.canvas.create_text(centre, y + M["BARRE_H"] // 2,
                                      text="", font=self.p_mini,
                                      fill=ENCRE, tags=tags)
        for item in (rail, bande):
            self.canvas.itemconfigure(item, state="hidden")
        return {"rail": rail, "bande": bande, "pct": pct, "photo": None}

    def _barre_montrer(self, barre, visible):
        etat = "normal" if visible else "hidden"
        for cle in ("rail", "bande", "pct"):
            self.canvas.itemconfigure(barre[cle], state=etat)
        if not visible:
            self.canvas.itemconfigure(barre["pct"], text="")

    def _progres(self, barre):
        """Rappel de progression pour `telecharger_fichier` : appelé depuis
        le fil réseau, il ne repasse par l'interface qu'aux pour cent
        entiers (1,4 Go = des dizaines de milliers d'appels sinon)."""
        def rappel(fait, total):
            if not total:
                return
            pct = int(min(1.0, fait / total) * 100)
            if pct != barre.get("dernier_pct"):
                barre["dernier_pct"] = pct
                self._sur_canvas(self._barre_pct, barre, fait, total)
        return rappel

    def _barre_pct(self, barre, fait, total):
        if not total:
            return
        fraction = min(1.0, fait / total)
        pleine = self.decor.pil("barre_bande")
        largeur = max(1, int(pleine.width * fraction))
        barre["photo"] = ImageTk.PhotoImage(
            pleine.crop((0, 0, largeur, pleine.height)))
        self.canvas.itemconfigure(barre["bande"], image=barre["photo"],
                                  state="normal")
        self.canvas.itemconfigure(
            barre["pct"], text="%d %%" % int(fraction * 100))

    def appliquer_trad(self, etat, remontrer=False):
        self.etat_trad = etat
        fiche = ETATS_TRAD[etat]
        fmt = {"vi": self.version_locale or "?",
               "vd": self.version_dispo or "?"}
        c = self.canvas
        c.itemconfigure(self.trad_titre, text=fiche["titre"],
                        fill=fiche["couleur"])
        c.itemconfigure(self.trad_sous, text=fiche["sous"].format(**fmt))
        # Le badge ne se montre que si la vue Traduction est affichée —
        # sinon il réapparaîtrait par-dessus la vue courante.
        c.itemconfigure(self.trad_badge,
                        state="normal" if (fiche["badge"]
                                          and self.vue == "traduction")
                        else "hidden")
        if self.vue == "traduction":
            if fiche["bouton"]:
                commandes = {"btn_installer": self.installer_trad,
                             "btn_maj": self.installer_trad,
                             "btn_reessayer": self.verifier,
                             "btn_admin": self.relancer_admin,
                             "btn_fait": None}
                self.btn_trad.configurer(
                    fiche["bouton"], commandes[fiche["bouton"]],
                    actif=fiche["bouton"] != "btn_fait")
                self.btn_trad.montrer()
            else:
                self.btn_trad.cacher()
            self._barre_montrer(self.barre_trad,
                                bool(fiche.get("progression")))
        c.itemconfigure(self.trad_dossier, text=self.jeu or
                        "aucun — choisis-le avec le bouton Changer")
        c.itemconfigure(self.lien_appli,
                        state="normal" if (self.appli_en_retard
                                           and self.url_exe
                                           and self.vue == "traduction")
                        else "hidden")
        self.statut(fiche["ton"], fiche["statut"].format(**fmt))
        if self.vue == "accueil":
            self.rafraichir_accueil()

    def changer_dossier(self):
        dossier = filedialog.askdirectory(
            title="Choisis le dossier du jeu (celui qui contient Interface)")
        if not dossier:
            return
        dossier = os.path.normpath(dossier)
        if not logique.jeu_valide(dossier):
            self.statut("erreur", "Ce dossier ne contient pas le jeu "
                                  "(pas de dossier Interface).")
            return
        self.jeu = dossier
        self.cfg["jeu"] = dossier
        logique.sauver_config(self.cfg)
        self.version_locale = logique.version_installee(dossier)
        self.verifier()
        self.rafraichir_voix()
        self.rafraichir_addons()

    def verifier(self):
        self._sur_canvas(self.appliquer_trad, "verification")
        self._fil(self._verifier_fond)

    def _verifier_fond(self):
        try:
            version, url_zip, url_exe = logique.derniere_release()
            note = self._note_release()
        except Exception:
            self._sur_canvas(self._apres_verif, None, None, None, None)
            return
        self._sur_canvas(self._apres_verif, version, url_zip, url_exe, note)

    def _note_release(self):
        req = urllib.request.Request(logique.API_RELEASE, headers=logique.UA)
        with urllib.request.urlopen(req, timeout=20,
                                    context=logique.CONTEXTE_SSL) as r:
            return json.load(r).get("body") or ""

    def _apres_verif(self, version, url_zip, url_exe, note):
        if note is not None:
            self.note = note
        if version is None:
            self.appliquer_trad("injoignable")
            return
        self.version_dispo, self.url_zip = version, url_zip
        self.url_exe = url_exe
        # L'application a-t-elle une version plus récente qu'elle-même ?
        # (l'affichage du lien vit dans appliquer_trad, qui repasse à
        # chaque entrée dans la vue Traduction)
        self.appli_en_retard = (logique.en_tuple(version)
                                > logique.en_tuple(
                                    logique.VERSION_COMPAGNON))
        if not logique.jeu_valide(self.jeu):
            self.appliquer_trad("introuvable")
        elif not self.version_locale:
            self.appliquer_trad("absente")
        elif logique.mise_a_jour_dispo(self.version_locale, version):
            self.appliquer_trad("maj")
        else:
            self.appliquer_trad("ajour")
        self.rafraichir_accueil()

    def installer_trad(self):
        if not self.url_zip:
            return
        self.appliquer_trad("telechargement")
        self._fil(self._installer_trad_fond)

    def _installer_trad_fond(self):
        try:
            chemin = logique.telecharger_fichier(
                self.url_zip, progres=self._progres(self.barre_trad))
            logique.installer_zip(chemin, self.jeu)
        except PermissionError:
            self._sur_canvas(self.appliquer_trad, "protege")
            return
        except Exception:
            self._sur_canvas(self.appliquer_trad, "injoignable")
            return
        self.version_locale = self.version_dispo
        self._sur_canvas(self.appliquer_trad, "reussie")

    def mettre_a_jour_appli(self):
        """Télécharge le nouvel exe et se fait remplacer (même mécanique
        que le Compagnon v2 : lancer_remplacement échange les fichiers et
        relance). Hors exe figé (essais python), on ouvre la page."""
        if not self.url_exe:
            return
        if not getattr(sys, "frozen", False):
            webbrowser.open(logique.PAGE_RELEASES)
            return
        self.statut("neutre", "Téléchargement de la nouvelle version de "
                              "l'application…")
        self._fil(self._maj_appli_fond)

    def _maj_appli_fond(self):
        try:
            chemin = logique.telecharger_fichier(self.url_exe,
                                                 suffixe=".exe")
        except Exception:
            self._sur_canvas(self.statut, "erreur",
                             "Téléchargement impossible. Réessaie plus "
                             "tard.")
            return
        self._sur_canvas(self._remplacer_appli, chemin)

    def _remplacer_appli(self, chemin):
        try:
            logique.lancer_remplacement(chemin, sys.executable)
        except Exception:
            self.statut("erreur", "Remplacement impossible — télécharge "
                                  "la nouvelle version depuis GitHub.")
            return
        self.destroy()

    def relancer_admin(self):
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                " ".join('"%s"' % a for a in sys.argv), None, 1)
            self.destroy()
        except Exception:
            self.statut("erreur", "Relance impossible. Fais un clic droit "
                                  "sur l'application → Exécuter en tant "
                                  "qu'administrateur.")

    # ----------------------------------------------------------------- VOIX
    def _construire_voix(self):
        t = ("vue_voix",)
        c, cx = self.canvas, M["CX"]
        c.create_text(cx, M["Y_TITRE"], anchor="w", text="Voix françaises",
                      font=self.p_titre, fill=ENCRE, tags=t)
        c.create_text(cx, M["Y_TITRE"] + 34, anchor="w",
                      text="Les cinématiques et les personnages parlent "
                           "français — les 14 442 répliques d'époque, "
                           "retrouvées et remises en place.",
                      font=self.p_corps, fill=ENCRE, width=M["CW"], tags=t)
        y = 140
        self.decor.poser(c, "panneau_or", cx, y, tags=t)
        centre = cx + M["CW"] // 2
        self.voix_titre = c.create_text(centre, y + 62, text="",
                                        font=self.p_gros, fill=OR_SOMBRE,
                                        tags=t)
        self.voix_sous = c.create_text(centre, y + 96, text="",
                                       font=self.p_soustitre,
                                       fill=ENCRE_DOUCE, tags=t)
        self.btn_voix = BoutonImage(
            self, "btn_voix", centre - M["BTN_L_W"] // 2, y + 138,
            commande=self.installer_voix, tags=t)
        self.barre_voix = self._construire_barre(centre, y + 150, t)
        self.btn_voix_bascule = BoutonImage(
            self, "btn_voix_couper", centre - 110, y + 224, tags=t)
        self.btn_voix_bascule.cacher()
        c.create_text(cx, y + M["PAN_OR_H"] + 30, anchor="w",
                      text="Les voix vivent dans un dépôt séparé de la "
                           "traduction : l'une ne peut jamais casser "
                           "l'autre.",
                      font=self.p_petit, fill=ENCRE, width=M["CW"], tags=t)
        self.boutons_voix = (self.btn_voix, self.btn_voix_bascule)
        self.etat_voix = "absentes"

    def _etat_voix_disque(self):
        """installees / coupees / absentes, lu sur le disque. Le témoin
        des voix commence par « Sound\\… » : la version coupée est le même
        chemin sous le dossier renommé."""
        if not logique.jeu_valide(self.jeu):
            return "absentes"
        if os.path.isfile(os.path.join(self.jeu, logique.TEMOIN_VOIX)):
            return "installees"
        reste = logique.TEMOIN_VOIX.split(os.sep, 1)[1]
        if os.path.isfile(os.path.join(self.jeu, DOSSIER_VOIX_COUPEES,
                                       reste)):
            return "coupees"
        return "absentes"

    def rafraichir_voix(self):
        if self.etat_voix == "telechargement":
            return
        self.appliquer_voix(self._etat_voix_disque())

    def appliquer_voix(self, etat):
        self.etat_voix = etat
        fiche = ETATS_VOIX[etat]
        c = self.canvas
        c.itemconfigure(self.voix_titre, text=fiche["titre"],
                        fill=fiche["couleur"])
        c.itemconfigure(self.voix_sous, text=fiche["sous"])
        if self.vue == "voix":
            if fiche["bouton"]:
                self.btn_voix.configurer(
                    fiche["bouton"],
                    self.installer_voix,
                    actif=fiche["bouton"] == "btn_voix")
                self.btn_voix.montrer()
            else:
                self.btn_voix.cacher()
            if fiche["bascule"]:
                commandes = {"btn_voix_couper": self.couper_voix,
                             "btn_voix_remettre": self.remettre_voix}
                self.btn_voix_bascule.configurer(
                    fiche["bascule"], commandes[fiche["bascule"]])
                self.btn_voix_bascule.montrer()
            else:
                self.btn_voix_bascule.cacher()
            self._barre_montrer(self.barre_voix,
                                bool(fiche.get("progression")))
            self.statut(fiche["ton"], fiche["statut"])

    def couper_voix(self):
        """Renomme <jeu>\\Sound en <jeu>\\Sound_off : le client repasse aux
        voix anglaises de ses archives. Rien n'est perdu."""
        source = os.path.join(self.jeu, "Sound")
        cible = os.path.join(self.jeu, DOSSIER_VOIX_COUPEES)
        if os.path.isdir(cible):
            self.statut("erreur", "Un dossier Sound_off existe déjà — "
                                  "range-le d'abord.")
            return
        try:
            os.rename(source, cible)
        except OSError:
            self.statut("erreur", "Impossible de couper : ferme d'abord "
                                  "le jeu, puis réessaie.")
            return
        self.appliquer_voix("coupees")
        self.rafraichir_accueil()

    def remettre_voix(self):
        source = os.path.join(self.jeu, DOSSIER_VOIX_COUPEES)
        cible = os.path.join(self.jeu, "Sound")
        if os.path.isdir(cible):
            self.statut("erreur", "Un dossier Sound existe déjà — "
                                  "range-le d'abord.")
            return
        try:
            os.rename(source, cible)
        except OSError:
            self.statut("erreur", "Impossible de remettre : ferme d'abord "
                                  "le jeu, puis réessaie.")
            return
        self.appliquer_voix("installees")
        self.rafraichir_accueil()

    def installer_voix(self):
        if not logique.jeu_valide(self.jeu):
            self.statut("alerte", "Choisis d'abord le dossier du jeu "
                                  "(onglet Traduction).")
            return
        self.appliquer_voix("telechargement")
        self._fil(self._installer_voix_fond)

    def _installer_voix_fond(self):
        try:
            chemin = logique.telecharger_fichier(
                logique.VOIX_URL, progres=self._progres(self.barre_voix))
            logique.installer_zip(chemin, self.jeu)
        except Exception:
            self._sur_canvas(self.appliquer_voix, "erreur")
            return
        self._sur_canvas(self.appliquer_voix, "installees")
        self._sur_canvas(self.rafraichir_accueil)

    # --------------------------------------------------------------- ADDONS
    def _construire_addons(self):
        t = ("vue_addons",)
        c, cx = self.canvas, M["CX"]
        c.create_text(cx, M["Y_TITRE"], anchor="w", text="Addons",
                      font=self.p_titre, fill=ENCRE, tags=t)
        c.create_text(cx, M["Y_TITRE"] + 30, anchor="w",
                      text="Traduits à 100 %, entretenus et distribués par "
                           "AscensionFR — toute la chaîne est de chez "
                           "nous.",
                      font=self.p_corps, fill=ENCRE_DOUCE, tags=t)
        self.cartes = []
        self.boutons_addons = []
        y0 = 122
        for i, fiche in enumerate(self.catalogue[:6]):
            x = cx + (i % 2) * (M["CARTE_W"] + 22)
            y = y0 + (i // 2) * (M["CARTE_H"] + 14)
            self.decor.poser(c, "carte", x, y, tags=t)
            self.decor.poser(c, "carte_ic_" + fiche["id"], x + 16, y + 16,
                             tags=t)
            c.create_text(x + 86, y + 26, anchor="w", text=fiche["nom"],
                          font=self.p_nom_carte, fill=ENCRE, tags=t)
            c.create_text(x + 86, y + 46, anchor="nw", text=fiche["desc"],
                          font=self.p_mini, fill=ENCRE_DOUCE,
                          width=M["CARTE_W"] - 108, tags=t)
            if fiche.get("fr"):
                self.decor.poser(c, "badge_fr", x + M["CARTE_W"] - 62,
                                 y + 14, tags=t)
            version = c.create_text(x + 86, y + M["CARTE_H"] - 16,
                                    anchor="w", text="",
                                    font=self.p_mini, fill=ENCRE_DOUCE,
                                    tags=t)
            bouton = BoutonImage(
                self, "btn_carte_bientot",
                x + M["CARTE_W"] - M["BTN_C_W"] - 14,
                y + M["CARTE_H"] - M["BTN_C_H"] - 10, tags=t)
            bouton.cacher()
            self.boutons_addons.append(bouton)
            self.cartes.append({"fiche": fiche, "version": version,
                                "bouton": bouton})

    def _verifier_addons_fond(self):
        """Lit le tag de la dernière release GitHub de chaque addon du
        catalogue : « Mettre à jour » ne s'affiche que si elle est VRAIMENT
        plus récente que le .toc installé (retouche de Dan du 23/07 — le
        bouton restait sur « Mettre à jour » en permanence)."""
        for fiche in self.catalogue:
            m = re.match(r"https://github\.com/([^/]+/[^/]+)/",
                         fiche.get("url") or "")
            if not m:
                continue
            try:
                req = urllib.request.Request(
                    "https://api.github.com/repos/%s/releases/latest"
                    % m.group(1), headers=logique.UA)
                with urllib.request.urlopen(
                        req, timeout=20, context=logique.CONTEXTE_SSL) as r:
                    tag = (json.load(r).get("tag_name") or "").lstrip("vV")
            except Exception:
                continue
            if tag:
                self.versions_distantes[fiche["id"]] = tag
        self._sur_canvas(self.rafraichir_addons)

    def rafraichir_addons(self):
        for carte in self.cartes:
            fiche, bouton = carte["fiche"], carte["bouton"]
            installee = (version_toc(self.jeu, fiche["dossier"])
                         if logique.jeu_valide(self.jeu) else None)
            if fiche.get("etat") == "bientot":
                texte = ""            # le bouton « Bientôt… » dit déjà tout
                nom, actif, cmd = "btn_carte_bientot", False, None
            elif installee:
                texte = ("version " + installee
                         if installee != "?" else "détecté chez toi")
                nom, actif, cmd = "btn_carte_installe", False, None
                # « Mettre à jour » seulement si la release distante est
                # STRICTEMENT plus récente que la version installée.
                distante = self.versions_distantes.get(fiche["id"])
                if (fiche.get("url") and distante and installee != "?"
                        and logique.en_tuple(distante)
                        > logique.en_tuple(installee)):
                    texte = "version %s  →  %s" % (installee, distante)
                    nom, actif = "btn_carte_maj", True
                    cmd = lambda f=fiche: self.installer_addon(f)
            elif fiche.get("url"):
                texte = "non installé"
                nom, actif = "btn_carte_installer", True
                cmd = lambda f=fiche: self.installer_addon(f)
            else:
                texte = "non détecté"
                nom, actif, cmd = "btn_carte_absent", False, None
            self.canvas.itemconfigure(carte["version"], text=texte)
            bouton.configurer(nom, cmd, actif=actif)
            if self.vue == "addons":
                bouton.montrer()

    def installer_addon(self, fiche):
        self.statut("neutre", "Téléchargement de %s…" % fiche["nom"])
        self._fil(self._installer_addon_fond, fiche)

    def _installer_addon_fond(self, fiche):
        try:
            chemin = logique.telecharger_fichier(fiche["url"])
            installer_addon_zip(chemin, self.jeu, fiche["dossier"])
        except Exception:
            self._sur_canvas(self.statut, "erreur",
                             "Installation de %s impossible." % fiche["nom"])
            return
        self._sur_canvas(self.statut, "succes",
                         "%s installé. En jeu : /reload." % fiche["nom"])
        self._sur_canvas(self.rafraichir_addons)

    # ----------------------------------------------------------- CONTRIBUER
    def _construire_contribuer(self):
        t = ("vue_contribuer",)
        c, cx = self.canvas, M["CX"]
        c.create_text(cx, M["Y_TITRE"], anchor="w", text="Contribuer",
                      font=self.p_titre, fill=ENCRE, tags=t)
        y = 96
        self.decor.poser(c, "parchemin_lettre", cx, y, tags=t)
        c.create_text(cx + 34, y + 44, anchor="w",
                      text="Fais avancer la traduction",
                      font=self.p_gros, fill=ENCRE, tags=t)
        c.create_text(cx + 34, y + 74, anchor="nw",
                      text="En jouant, l'addon note tout seul les textes "
                           "encore en anglais. Un clic, et ton rapport part "
                           "aider la traduction — des textes du jeu que tu "
                           "as croisés (quêtes, PNJ, objets), jamais rien de "
                           "personnel.\nDéconnecte-toi ou tape /reload "
                           "d'abord : le jeu n'écrit sa liste qu'à ce "
                           "moment-là.",
                      font=self.p_corps, fill=ENCRE_DOUCE,
                      width=M["CW"] - 130, tags=t)
        self.contrib_compteur = c.create_text(
            cx + 34, y + 188, anchor="w", text="",
            font=self.p_soustitre, fill=OR_SOMBRE, tags=t)
        self.btn_envoyer = BoutonImage(
            self, "btn_envoyer", cx + 34, y + 220,
            commande=self.envoyer_rapport, tags=t)
        self.contrib_etat = c.create_text(
            cx + 34 + M["BTN_M_W"] + 20, y + 220 + M["BTN_M_H"] // 2,
            anchor="w", text="", font=self.p_petit, fill=ENCRE_DOUCE,
            tags=t)
        self.boutons_contribuer = (self.btn_envoyer,)
        self.envoi_en_cours = False

    def rafraichir_contrib(self):
        total, attente = self.stats
        if total:
            texte = ("Tu as fait traduire %s textes. Merci !"
                     % "{:,}".format(total).replace(",", " "))
        else:
            texte = "Joue avec l'addon, puis reviens envoyer ta récolte."
        self.canvas.itemconfigure(self.contrib_compteur, text=texte)
        if not self.envoi_en_cours:
            possible = bool(logique.WEBHOOK_RAPPORTS
                            and logique.jeu_valide(self.jeu))
            self.btn_envoyer.configurer(
                "btn_envoyer" if possible else "btn_envoyer_gris",
                self.envoyer_rapport, actif=possible)

    def _lire_stats(self):
        if not logique.jeu_valide(self.jeu):
            return
        try:
            stats = logique.lire_stats(self.jeu)
        except Exception:
            return
        self._sur_canvas(self._apres_stats, stats)

    def _apres_stats(self, stats):
        self.stats = stats
        self.rafraichir_contrib()
        self.rafraichir_accueil()

    def envoyer_rapport(self):
        if self.envoi_en_cours:
            return
        self.envoi_en_cours = True
        self.btn_envoyer.configurer("btn_envoyer_gris", actif=False)
        self.canvas.itemconfigure(self.contrib_etat, text="Envoi…")
        self.statut("neutre", "Préparation du rapport…")
        self._fil(self._envoyer_fond)

    def _envoyer_fond(self):
        try:
            deja = logique.deja_envoyees()
            rapport, nombre, empreintes = logique.construire_rapport(
                self.jeu, deja)
            if not nombre:
                self._sur_canvas(self._apres_envoi, "vide",
                                 "Rien de nouveau à envoyer — tout est "
                                 "déjà parti. Rejoue un peu !")
                return
            caches = logique.extraire_caches(self.jeu)
            logique.envoyer_rapport_discord(rapport, caches)
            logique.noter_envoyees(self.cfg, empreintes)
        except Exception:
            self._sur_canvas(self._apres_envoi, "horsligne",
                             "Envoi impossible. Vérifie ta connexion, puis "
                             "réessaie.")
            return
        self._sur_canvas(self._apres_envoi, "reussi",
                         "Rapport envoyé — merci pour le coup de main !")
        self._sur_canvas(self._lire_stats_apres_envoi)

    def _lire_stats_apres_envoi(self):
        self._fil(self._lire_stats)

    def _apres_envoi(self, etat, message):
        self.envoi_en_cours = False
        self.canvas.itemconfigure(self.contrib_etat, text=message)
        self.statut("succes" if etat in ("reussi", "vide") else "erreur",
                    message)
        self.rafraichir_contrib()

    # ------------------------------------------------------------- mode démo
    def _peupler_demo(self):
        """États factices pour les captures d'écran (aucun réseau)."""
        self.version_locale, self.version_dispo = "2.2.1", "3.0.0"
        self.note = ("## 3.0.0 — le Hub\n"
                     "- Catalogue d'addons français en un clic\n"
                     "- Grimoire et fenêtres d'Ascension traduits\n"
                     "- Bulles de talents + 793 noms de sorts corrigés\n"
                     "- D'autres addons traduits arrivent bientôt\n"
                     "\nUn mot de Dan :\n"
                     "Ce week-end, je corrige un maximum de bugs ; ensuite la "
                     "traduction avancera plus doucement, mais vos rapports "
                     "restent les bienvenus. Merci à la communauté pour tout. "
                     "Je vais enfin prendre le temps de jouer, au lieu de "
                     "manger ma carte graphique. Cœur sur vous, et à "
                     "bientôt en jeu <3\n")
        self.stats = (12847, 315)
        self.appliquer_trad({"accueil": "ajour", "traduction": "maj",
                             "voix": "ajour", "addons": "ajour",
                             "contribuer": "ajour"}.get(self.demo, "ajour"))
        self.rafraichir_contrib()
        self.rafraichir_accueil()


# --------------------------------------------------------------------------- #
def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    args = sys.argv[1:]
    demo = None
    capture = None
    if "--demo" in args:
        i = args.index("--demo")
        demo = args[i + 1] if i + 1 < len(args) else "accueil"
    if "--capture" in args:
        i = args.index("--capture")
        capture = args[i + 1] if i + 1 < len(args) else "hub.png"
    app = Hub(demo=demo)
    if demo:
        app.montrer_vue(demo if demo in VUES else "accueil")
    if capture:
        # La capture photographie une ZONE D'ÉCRAN : la fenêtre doit être
        # devant tout le reste, sinon on photographie ce qui la recouvre.
        app.attributes("-topmost", True)
        app.update_idletasks()
        app.update()

        def prendre():
            from PIL import ImageGrab
            app.lift()
            app.focus_force()
            app.update()
            x = app.winfo_rootx()
            y = app.winfo_rooty()
            boite = (x, y, x + M["W"], y + M["H"])
            ImageGrab.grab(bbox=boite).save(capture)
            print("capture :", capture)
            app.destroy()
        app.after(700, prendre)
    app.mainloop()


if __name__ == "__main__":
    main()
