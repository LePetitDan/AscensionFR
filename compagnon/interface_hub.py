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
import traceback
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
    # PAN_LETTRE_H : 330 -> 364 au programme 23. Le second bouton du bloc B
    # (« Copier mon rapport ») a repoussé le compteur sous la rangée, et le
    # compteur a repoussé la case « envoi automatique ». Le panneau grandit
    # de 34 px plutôt que de tasser trois éléments les uns sur les autres.
    "PAN_OR_H": 310, "PAN_NOUV_H": 258, "PAN_LETTRE_H": 364,
    # Plaques d'infobulle (lot 12 : jamais d'encre sur le bois — tout texte
    # posé sur la texture passe sur une plaque, la règle que WoW s'applique)
    "PLAQUE_VERDICT_H": 78,      # accueil : verdict + lien de contrôle
    "PLAQUE_OUTILS_H": 106,      # traduction : dossier + liens de secours
    "PLAQUE_NOTE_H": 36,         # voix : note de bas de vue
    # Zone défilante du catalogue d'addons (le plafond de 6 a sauté)
    "CATA_Y": 122, "CATA_H": 464,
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

# Sur les PLAQUES d'infobulle (fond bleu nuit du jeu), l'encre et les teintes
# de parchemin sont illisibles : chaque tonalité a sa variante claire,
# calibrée pour tenir les 4,5:1 du seuil de l'audit sur le fond de plaque.
P_VERT = "#7fd06a"
P_ORANGE = "#e8a33d"
P_ROUGE = "#ff8f70"
P_OR = OR_VIF
P_TEXTE = BEIGE
P_TEXTE_VIF = BEIGE_VIF
P_DISCRET = "#b9ad8f"

TONALITES = {
    "neutre": "#4a3316",
    "alerte": "#6e4408",
    "erreur": "#7e1f10",
    "succes": "#1f5a1c",
}

# --------------------------------------------------------------------------- #
# Les états de la vue Traduction (repris de l'interface v2, adaptés).
# --------------------------------------------------------------------------- #
# « pastille » : la bille d'état du jeu (COMMON/Indicator-*) posée à côté du
# verdict — la couleur DOUBLE le texte, elle ne le remplace jamais (un
# daltonien lit la phrase, la pastille n'est qu'un renfort).
# Lot 12, point 6 : « ajour » et « installees » n'ont PLUS de bouton — un
# état ne doit pas ressembler à un bouton. Le verdict vit dans le titre, le
# badge et la pastille.
ETATS_TRAD = {
    "verification": {
        "titre": "Vérification…", "couleur": OR_SOMBRE,
        "sous": "Recherche de la dernière version…",
        "badge": False, "bouton": None, "ton": "neutre",
        "pastille": "grise",
        "statut": "Vérification des mises à jour…"},
    "introuvable": {
        "titre": "Dossier introuvable", "couleur": ORANGE,
        "sous": "Choisis d'abord le dossier du jeu ci-dessous.",
        "badge": False, "bouton": None, "ton": "alerte",
        "pastille": "jaune",
        "statut": "Sélectionne le dossier de World of Warcraft pour "
                  "continuer."},
    "absente": {
        "titre": "Traduction non installée", "couleur": OR_SOMBRE,
        "sous": "Dernière version disponible : {vd}",
        "badge": False, "bouton": "btn_installer", "ton": "neutre",
        "pastille": "jaune",
        "statut": "Prêt à installer la version {vd}."},
    "ajour": {
        "titre": "Tu es à jour", "couleur": VERT,
        "sous": "Version {vi} installée — rien à faire.",
        "badge": True, "bouton": None, "ton": "succes",
        "pastille": "verte",
        "statut": "Tout est à jour. Bon jeu !"},
    "maj": {
        "titre": "Mise à jour disponible", "couleur": OR_SOMBRE,
        "sous": "Installée : {vi}   →   Disponible : {vd}",
        "badge": False, "bouton": "btn_maj", "ton": "neutre",
        "pastille": "jaune",
        "statut": "Une nouvelle version de la traduction t'attend."},
    "injoignable": {
        "titre": "Serveur injoignable", "couleur": ROUGE,
        "sous": "Impossible de joindre GitHub. Vérifie ta connexion.",
        "badge": False, "bouton": "btn_reessayer", "ton": "erreur",
        "pastille": "rouge",
        "statut": "Impossible de vérifier les mises à jour."},
    "telechargement": {
        "titre": "Installation en cours…", "couleur": OR_SOMBRE,
        "sous": "Téléchargement de la version {vd}",
        "badge": False, "bouton": None, "ton": "neutre",
        "pastille": "grise",
        "statut": "Téléchargement… ne ferme pas la fenêtre.",
        "progression": True},
    "protege": {
        "titre": "Dossier protégé", "couleur": ORANGE,
        "sous": "Windows empêche l'écriture ici. Relance en administrateur.",
        "badge": False, "bouton": "btn_admin", "ton": "alerte",
        "pastille": "jaune",
        "statut": "Droits administrateur requis pour ce dossier."},
    "reussie": {
        "titre": "Installation réussie", "couleur": VERT,
        "sous": "En jeu : tape /reload, ou reconnecte-toi.",
        "badge": True, "bouton": None, "ton": "succes",
        "pastille": "verte",
        "statut": "Traduction installée. Amuse-toi bien !"},
}

ETATS_VOIX = {
    "absentes": {
        "titre": "Voix non installées", "couleur": OR_SOMBRE,
        "sous": "Un téléchargement d'environ 1,4 Go — une seule fois.",
        "bouton": "btn_voix", "bascule": None, "ton": "neutre",
        "badge": False, "pastille": "jaune",
        "statut": "Les voix françaises t'attendent."},
    "telechargement": {
        "titre": "Téléchargement des voix…", "couleur": OR_SOMBRE,
        "sous": "C'est volumineux : laisse la fenêtre ouverte.",
        "bouton": None, "bascule": None, "ton": "neutre",
        "badge": False, "pastille": "grise",
        "statut": "Téléchargement des voix françaises…",
        "progression": True},
    "installees": {
        "titre": "Voix françaises installées", "couleur": VERT,
        "sous": "14 442 répliques d'époque. Reconnecte-toi si le jeu "
                "tournait pendant l'installation.",
        # Plus de faux bouton « Voix installées » : l'état vit dans le
        # titre, le badge et la pastille (lot 12, point 6). La bascule
        # « Couper » est NEUTRE — le rouge appartient à l'action principale.
        "bouton": None, "bascule": "btn_voix_couper",
        "ton": "succes", "badge": True, "pastille": "verte",
        "consequence": "Couper repasse le jeu aux voix anglaises — rien "
                       "n'est perdu, un clic les remet.",
        "statut": "Les personnages parlent français. Bon jeu !"},
    "coupees": {
        "titre": "Voix françaises coupées", "couleur": ORANGE,
        "sous": "Les fichiers sont gardés de côté — un clic les remet, "
                "rien à re-télécharger.",
        "bouton": None, "bascule": "btn_voix_remettre", "ton": "alerte",
        "badge": False, "pastille": "jaune",
        "statut": "Les voix sont coupées : le jeu parle anglais."},
    "erreur": {
        "titre": "Téléchargement interrompu", "couleur": ROUGE,
        "sous": "Vérifie ta connexion, puis réessaie.",
        "bouton": "btn_voix", "bascule": None, "ton": "erreur",
        "badge": False, "pastille": "rouge",
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
        (x, y) — la marge du PNG est déduite automatiquement.

        Si le PNG est ABSENT, on saute proprement (retourne None) au lieu de
        planter. Sans ce garde-fou, un addon ajouté au catalogue sans son
        icône « carte_ic_<id>.png » faisait PLANTER le Hub AU DÉMARRAGE pour
        TOUS les joueurs (un addon du catalogue en 3.1.0, signalé par Dan le
        24/07/2026). Une icône manquante ne doit jamais casser toute
        l'application."""
        if not os.path.isfile(os.path.join(self.dossier, nom + ".png")):
            return None
        p = self.pad(nom)
        return canvas.create_image(x - p, y - p, anchor="nw",
                                   image=self.photo(nom), **kw)


# --------------------------------------------------------------------------- #
# La molette — le même geste, deux protocoles
# --------------------------------------------------------------------------- #
# Sous Windows (et macOS), Tk envoie un seul événement `<MouseWheel>` dont
# `delta` vaut ±120 par cran. Sous X11, la molette est un BOUTON : `<Button-4>`
# vers le haut, `<Button-5>` vers le bas, et `delta` vaut **0** — un code écrit
# pour Windows ne défile donc pas du tout, en silence. Trouvé au balayage du
# programme 23 : trois liaisons dans le Hub, dont le catalogue d'addons, à qui
# on avait justement retiré son plafond de 6 pour qu'il défile.
def crans_molette(evenement):
    """Nombre de crans, signé : positif vers le haut, comme `delta // 120`."""
    numero = getattr(evenement, "num", None)
    if numero == 4:
        return 1
    if numero == 5:
        return -1
    return (getattr(evenement, "delta", 0) or 0) // 120


def lier_molette(widget, fonction):
    """Relie les TROIS séquences. Celles qui ne concernent pas le système ne
    se déclenchent simplement jamais : rien ne change sous Windows."""
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        widget.bind(sequence, fonction)


# Le nom du décor d'un bouton EST son libellé : on le retraduit en une phrase
# que le joueur reconnaîtra dans la fenêtre de plantage (programme 23).
GESTES = {
    "btn_lancer": "Lancer le jeu",
    "btn_installer": "Installer la traduction",
    "btn_maj": "Mettre à jour la traduction",
    "btn_reessayer": "Réessayer",
    "btn_admin": "Relancer en administrateur",
    "btn_voix": "Installer les voix françaises",
    "btn_voix_couper": "Couper les voix",
    "btn_voix_remettre": "Remettre les voix",
    "btn_envoyer": "Envoyer mon rapport",
    "btn_copier": "Copier mon rapport",
    "btn_changer": "Changer le dossier du jeu",
    "btn_discord": "Ouvrir le Discord",
    "btn_cafe": "Ouvrir la page de soutien",
    "btn_carte_installer": "Installer un addon",
    "btn_carte_maj": "Mettre à jour un addon",
    "btn_carte_desinstaller": "Désinstaller un addon",
}


class BoutonImage:
    """Bouton dessiné sur le canvas : image au repos, image de survol,
    enfoncement de 2 px au clic, état désactivé (image grise, sans action)."""

    def __init__(self, app, nom, x, y, commande=None, tags=(), canvas=None):
        # `canvas` : par défaut le canvas principal ; le catalogue d'addons
        # vit sur son propre canvas défilant (lot 12, point 7).
        self.app, self.decor = app, app.decor
        self.canvas = canvas if canvas is not None else app.canvas
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
            # Le dernier geste du joueur, pour que la fenêtre de plantage
            # dise « c'est arrivé pendant : Lancer le jeu » plutôt que
            # « une action du Hub » (programme 23). Un seul endroit à tenir :
            # tous les boutons du Hub passent par ici.
            self.app.geste_en_cours = GESTES.get(self.nom, self.nom)
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


def _taille_lisible(octets):
    """« 1,7 Go » plutôt que « 1825361920 » : la liste de ce qu'on va
    supprimer doit se lire d'un coup d'œil."""
    for unite, seuil in (("Go", 1 << 30), ("Mo", 1 << 20), ("Ko", 1 << 10)):
        if octets >= seuil:
            return ("%.1f %s" % (octets / float(seuil), unite)).replace(
                ".", ",")
    return "%d octets" % octets


def dossiers_addon_du_zip(tampon):
    """Tous les dossiers d'addon contenus dans une archive déballée.

    Un dossier d'addon, c'est un dossier qui porte SON PROPRE .toc — la règle
    de WoW. On ne descend pas dedans une fois trouvé : les libs (AceGUI,
    LibStub…) ne sont pas des addons, et un .toc d'exemple planqué au fond ne
    doit pas créer un faux dossier. Rend une liste de (nom, chemin)."""
    trouves = []
    for racine, dossiers, fichiers in os.walk(tampon):
        nom = os.path.basename(racine)
        bas = {f.lower() for f in fichiers}
        if nom and (nom.lower() + ".toc") in bas:
            trouves.append((nom, racine))
            dossiers[:] = []          # trouvé : on ne fouille pas dessous
    return trouves


def installer_addon_zip(chemin_zip, jeu, dossier):
    """Déballe un zip d'addon dans Interface\\AddOns. Le zip peut contenir le
    dossier à sa racine, ou (archive GitHub) un dossier intermédiaire
    « Depot-branche/ » : on cherche les .toc et on re-racine.

    26/07/2026 — on installe TOUS les dossiers d'addon du zip, plus seulement
    celui qui porte le nom de la fiche. DragonUI se livre en DEUX dossiers
    frères : DragonUI et DragonUI_Options (« ## LoadOnDemand: 1 »,
    « ## Dependencies: DragonUI »). L'ancien re-racinage sur le seul
    « DragonUI.toc » copiait le premier et jetait le second avec le dossier
    temporaire — d'où le « module des options n'est pas installé » en jeu, et
    le bouton DragonUI qui disparaît du menu Échap (gamemenu.lua:204). Deux
    joueurs sont allés chercher le dossier manquant sur le dépôt d'origine ;
    ce n'était pas à eux de le faire.

    Rend la liste des noms de dossiers réellement installés."""
    addons = os.path.join(jeu, "Interface", "AddOns")
    tampon = tempfile.mkdtemp(prefix="AscensionFR_addon_")
    try:
        with zipfile.ZipFile(chemin_zip) as z:
            z.extractall(tampon)
        sources = dossiers_addon_du_zip(tampon)
        # (le zip téléchargé est effacé dans le finally : installer_zip le
        # faisait, pas nous — onze archives orphelines traînaient dans le
        # %TEMP% de Dan, une par installation d'addon depuis le début)
        if not any(n.lower() == dossier.lower() for n, _c in sources):
            # Garde-fou inchangé : si l'addon attendu n'est pas là, c'est que
            # l'URL a changé de contenu — on ne pose RIEN plutôt que n'importe
            # quoi dans le dossier AddOns du joueur.
            raise ValueError("le zip ne contient pas " + dossier + ".toc")
        poses = []
        for nom, source in sources:
            cible = os.path.join(addons, nom)
            if os.path.isdir(cible):
                shutil.rmtree(cible)
            shutil.copytree(source, cible)
            poses.append(nom)
        return poses
    finally:
        shutil.rmtree(tampon, ignore_errors=True)
        try:
            os.remove(chemin_zip)
        except OSError:
            pass


def _candidats_registre():
    """Emplacements du launcher Ascension notés dans le registre Windows
    (clés de désinstallation). LECTURE seule, jamais d'écriture.

    ⚠️ `winreg` N'EXISTE PAS hors Windows : sans cette garde, l'import lève
    ModuleNotFoundError et le bouton « Lancer le jeu » ne fait rien du tout
    (trouvé par Tetardtek sous Linux, 02/08/2026). C'est la MÊME garde que
    `compagnon._pistes_launcher` (l. 316-347) : on ne crée pas une deuxième
    manière de gérer le cas non-Windows, on reprend celle qui existe."""
    try:
        import winreg
    except ImportError:
        return []                  # pas Windows : aucun registre à lire
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
# LE PLANTAGE VISIBLE (programme 23, 02/08/2026)
# --------------------------------------------------------------------------- #
# LE DÉFAUT QU'ON RÉPARE, MESURÉ. Dans un exe figé en mode fenêtré,
# `sys.stdout` ET `sys.stderr` valent None. Tkinter attrape toute exception de
# rappel dans `report_callback_exception`, qui fait `print(..., file=None)`
# puis `traceback.print_exception` : les deux écrivent dans le vide SANS RIEN
# LEVER. Un bouton qui plante ne fait donc rien du tout, l'application se
# ferme ensuite normalement, et le joueur n'a aucune piste. Vrai sous Linux
# (pas de console) ET sous Windows (pas de console non plus) : les 274.
#
# Le garde-fou de PyInstaller (`disable_windowed_traceback=False`) ne suffit
# pas : il ne se déclenche que pour une exception NON RATTRAPÉE au niveau
# supérieur — or Tkinter les rattrape toutes —, il n'existe que sous Windows
# et macOS (documenté dans PyInstaller/building/api.py), et il affiche un
# traceback Python brut en anglais.
#
# Trois portes, parce qu'une exception peut arriver à trois endroits :
#   1. dans un rappel Tk (un bouton)     -> Hub.report_callback_exception
#   2. dans un fil de fond (self._fil)   -> threading.excepthook
#   3. avant/hors la boucle (démarrage)  -> sys.excepthook + le try de main()
_APPLI = None                # le Hub vivant, pour reposter depuis un fil
_PLANTAGE_OUVERT = False     # une seule fenêtre à la fois (boucle de plantage)

# Mêmes teintes que les fenêtres filles du Hub (Hub.FOND_F et compagnie), mais
# au niveau du module : cette fenêtre doit pouvoir s'ouvrir même quand la
# classe Hub n'a pas fini de se construire.
PL_FOND = "#efe2c0"
PL_PANNEAU = "#f7eed6"
PL_BORD = "#8a6a2a"


def montrer_plantage(parent, ou, trace=None):
    """« Ça a raté, voilà où c'est écrit » — une fenêtre, pas un terminal.

    Le texte s'adresse à un JOUEUR : ce qui s'est passé, ce que ça ne casse
    pas, où c'est écrit, et quoi faire s'il veut aider. Le relevé est
    COPIABLE (règle de la maison : jamais un print, toujours du copiable) et
    déjà anonymisé par `logique.journal_incident`.

    Cette fonction ne doit JAMAIS lever : un gestionnaire de plantage qui
    plante rend le défaut d'origine indébusquable."""
    global _PLANTAGE_OUVERT
    if _PLANTAGE_OUVERT:
        return
    if trace is None:
        trace = traceback.format_exc()
    chemin = logique.journal_incident(ou, trace)
    detail = logique._anonymiser(trace).rstrip()
    try:
        _PLANTAGE_OUVERT = True
        _fenetre_plantage(parent, ou, chemin, detail)
    except Exception:
        _PLANTAGE_OUVERT = False
        # Dernier repli : la boîte de dialogue du système. Elle est moche,
        # mais elle s'affiche là où notre fenêtre a échoué.
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "AscensionFR — quelque chose a raté",
                "Le Hub a rencontré un problème pendant : %s.\n\n"
                "Le détail est écrit dans :\n%s"
                % (ou, chemin or "(nulle part — le disque a refusé)"))
        except Exception:
            pass


def _fenetre_plantage(parent, ou, chemin, detail):
    vivant = False
    try:
        vivant = bool(parent) and bool(parent.winfo_exists())
    except Exception:
        vivant = False
    if vivant:
        f = tk.Toplevel(parent)
    else:
        # Le Hub n'existe pas (plantage au démarrage) : on fabrique la seule
        # fenêtre de l'application. Elle doit donc porter sa propre boucle.
        f = tk.Tk()
    f.title("AscensionFR — quelque chose a raté")
    f.configure(bg=PL_FOND, highlightbackground=PL_BORD,
                highlightcolor=PL_BORD, highlightthickness=2)
    f.resizable(False, False)
    try:
        f.iconbitmap(logique.ressource("logo.ico"))
    except Exception:
        pass                      # X11 ne connaît pas les .ico

    cadre = tk.Frame(f, bg=PL_FOND)
    cadre.pack(fill="both", expand=True, padx=18, pady=16)
    tk.Label(cadre, text="Le Hub a rencontré un problème.",
             bg=PL_FOND, fg="#7e1f10",
             font=("Segoe UI", 13, "bold")).pack(anchor="w")
    # Le Hub existe-t-il encore derrière ? La phrase change — dire « continue
    # à te servir du Hub » alors qu'il n'a pas pu démarrer serait un mensonge,
    # et c'est précisément le cas où le joueur a le plus besoin d'être guidé.
    suite = ("Tu peux fermer cette fenêtre et continuer à te servir du Hub."
             if vivant else
             "Le Hub n'a pas pu démarrer. Ferme cette fenêtre, puis "
             "réessaie ; si ça recommence, envoie-nous le détail ci-dessous.")
    tk.Label(
        cadre, bg=PL_FOND, fg=ENCRE, justify="left", wraplength=560,
        text="Ce n'est pas de ta faute, et rien n'est cassé dans ton jeu.\n"
             + suite + "\n\nC'est arrivé pendant : %s" % ou,
        font=("Segoe UI", 10)).pack(anchor="w", pady=(8, 10))
    tk.Label(
        cadre, bg=PL_FOND, fg=ENCRE_DOUCE, justify="left", wraplength=560,
        text=("Le détail est écrit dans ce fichier :\n%s" % chemin) if chemin
        else "Le détail n'a pas pu être écrit sur le disque — il est "
             "ci-dessous, copie-le avant de fermer.",
        font=("Segoe UI", 9)).pack(anchor="w")

    boite = tk.Text(cadre, height=9, width=74, wrap="none",
                    bg=PL_PANNEAU, fg=ENCRE, relief="flat",
                    highlightbackground=PL_BORD, highlightthickness=1,
                    font=("Consolas", 9))
    boite.insert("1.0", detail)
    boite.configure(state="disabled")
    boite.pack(fill="both", expand=True, pady=(8, 10))

    tk.Label(
        cadre, bg=PL_FOND, fg=ENCRE_DOUCE, justify="left", wraplength=560,
        text="Si tu veux aider à le corriger : « Copier le détail », puis "
             "colle-le sur le Discord dans le salon d'entraide. Il ne "
             "contient ni ton pseudo, ni tes mots de passe, ni aucun chemin "
             "personnel.",
        font=("Segoe UI", 9)).pack(anchor="w")

    rangee = tk.Frame(cadre, bg=PL_FOND)
    rangee.pack(fill="x", pady=(12, 0))

    dit = tk.Label(rangee, text="", bg=PL_FOND, fg="#1f5a1c",
                   font=("Segoe UI", 9))

    def copier():
        try:
            f.clipboard_clear()
            f.clipboard_append(detail)
            f.update_idletasks()      # sans ça, Windows perd le contenu
            dit.configure(text="Copié.")
        except Exception:
            dit.configure(text="Copie impossible — sélectionne le texte "
                               "ci-dessus.", fg="#7e1f10")

    def fermer():
        global _PLANTAGE_OUVERT
        _PLANTAGE_OUVERT = False
        try:
            f.destroy()
        except Exception:
            pass

    tk.Button(rangee, text="Copier le détail", command=copier,
              bg="#e8c25a", fg="#15130c", activebackground="#d9b44e",
              relief="flat", bd=0, padx=14, pady=6,
              cursor="hand2").pack(side="left")
    tk.Button(rangee, text="Fermer", command=fermer,
              bg="#e6d6ac", fg=ENCRE, activebackground="#dcc998",
              relief="flat", bd=0, padx=14, pady=6,
              cursor="hand2").pack(side="left", padx=(8, 0))
    dit.pack(side="left", padx=(12, 0))
    f.protocol("WM_DELETE_WINDOW", fermer)

    # Pas de grab_set ici, VOLONTAIREMENT : c'est précisément le piège du
    # bloc A (« grab failed: window not viewable » sous X11), et une fenêtre
    # d'erreur qui refuse de s'ouvrir serait le comble.
    try:
        f.lift()
        f.attributes("-topmost", True)
        f.after(400, lambda: f.attributes("-topmost", False))
    except tk.TclError:
        pass
    if not vivant:
        f.mainloop()


def _sur_rappel_tk(self, exc, val, tb):
    """Remplace `Tk.report_callback_exception`, qui écrivait dans le vide."""
    montrer_plantage(self, getattr(self, "geste_en_cours", None)
                     or "une action du Hub",
                     "".join(traceback.format_exception(exc, val, tb)))


def _sur_fil(args):
    """Une exception dans un fil de fond (self._fil). Elle ne passe PAS par
    report_callback_exception : sans ceci, elle disparaît encore plus
    complètement qu'un rappel — Python l'écrit sur stderr, qui est None."""
    if args.exc_type is SystemExit:
        return
    trace = "".join(traceback.format_exception(
        args.exc_type, args.exc_value, args.exc_traceback))
    ou = "une tâche de fond (%s)" % getattr(args.thread, "name", "?")
    # On écrit la trace TOUT DE SUITE, depuis le fil : si l'interface est
    # morte, c'est tout ce qu'on aura.
    logique.journal_incident(ou, trace)
    appli = _APPLI
    if appli is None:
        return
    try:
        # On ne touche jamais Tk depuis un fil : on repasse par la boucle.
        appli.after(0, lambda: montrer_plantage(appli, ou, trace))
    except Exception:
        pass


def _sur_hors_boucle(exc, val, tb):
    """Tout le reste : le démarrage, et ce qui échappe aux deux autres."""
    montrer_plantage(_APPLI, "le démarrage du Hub",
                     "".join(traceback.format_exception(exc, val, tb)))


# --------------------------------------------------------------------------- #
# L'application
# --------------------------------------------------------------------------- #
VUES = ("accueil", "traduction", "voix", "addons", "contribuer")

M = METRIQUE


class Hub(tk.Tk):
    # Programme 23 : la porte n°1 du plantage visible. Tkinter appelle CETTE
    # méthode pour toute exception levée dans un rappel — c'est-à-dire pour
    # tous les boutons du Hub. Celle de Tk écrivait sur `sys.stderr`, qui vaut
    # None dans un exe fenêtré : tout partait dans le vide.
    report_callback_exception = _sur_rappel_tk

    def __init__(self, demo=None):
        super().__init__()
        self.demo = demo
        # Ce que le joueur venait de cliquer, pour le nommer s'il plante.
        self.geste_en_cours = None
        self.title("AscensionFR — Hub")
        self.resizable(False, False)
        self.configure(bg="#0a0a0c")
        try:
            self.iconbitmap(logique.ressource("logo.ico"))
        except Exception:
            pass
        # Ctrl+D : copie le diagnostic dans le presse-papier, à tout moment.
        # Sans données, un « ça marche pas » n'est pas dépannable.
        self.bind("<Control-d>", lambda _e: self.copier_diagnostic())
        self.bind("<Control-D>", lambda _e: self.copier_diagnostic())
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
        self.cfg.setdefault("envoi_auto", True)   # contributions auto (opt-out)
        self.jeu = self.cfg.get("jeu")
        # RATTRAPAGE DES CONFIGS HÉRITÉES (26/07/2026). Durcir « Changer… »
        # ne protège que celui qui reclique dessus. Les douze joueurs bloqués
        # ont un mauvais chemin DÉJÀ écrit dans leur compagnon.json par une
        # version précédente — s'il passait le vieux test, il restait là pour
        # toujours, et le Hub installait à côté sans un mot. On le repasse
        # donc par le correcteur au démarrage, en silence quand il retombe
        # sur ses pattes.
        if self.jeu and not logique.racine_jeu(self.jeu):
            racine, _note = logique.corriger_dossier_jeu(self.jeu)
            if racine:
                self.jeu = racine
                self.cfg["jeu"] = racine
                logique.sauver_config(self.cfg)
        if not logique.racine_jeu(self.jeu):
            trouve = logique.chercher_jeu()
            # On ne remplace un chemin mémorisé que par MIEUX : si la
            # recherche ne rend rien de solide, on garde l'ancien pour que le
            # contrôle d'installation puisse en parler au joueur.
            if trouve and (logique.racine_jeu(trouve)
                           or not logique.jeu_valide(self.jeu)):
                self.jeu = trouve
                self.cfg["jeu"] = trouve
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
        if demo == "addons":
            # En démo, on gonfle le catalogue à 8 fiches : c'est la preuve
            # visuelle que le plafond de 6 a sauté et que le défilement
            # marche (lot 12, point 7). Icônes déjà cuites pour les trois.
            self.catalogue = self.catalogue + [
                {"id": "dbm", "nom": "Deadly Boss Mods",
                 "desc": "Alertes de combat pour les donjons et raids.",
                 "dossier": "DBM-Core", "etat": "bientot"},
                {"id": "adibags", "nom": "AdiBags",
                 "desc": "Sacs en un seul panneau, rangé par catégories.",
                 "dossier": "AdiBags", "etat": "bientot"},
                {"id": "lootcollector", "nom": "LootCollector",
                 "desc": "Suivi des collectes et des butins rares.",
                 "dossier": "LootCollector", "etat": "bientot"}]
        self.versions_distantes = {}  # id -> tag de la dernière release
        self.url_distantes = {}       # id -> URL du dernier asset .zip (API)
        self.controle = None          # contrôle d'installation (lecture disque)
        self.installations_en_cours = set()   # ids d'addons en cours de pose

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
            self._fil(self._controle_fond)
            # Envoi automatique des contributions à l'ouverture (opt-out) :
            # beaucoup de joueurs ne penseraient jamais à cliquer « Envoyer »,
            # donc leurs textes récoltés (et propositions) ne remonteraient
            # jamais. Silencieux ; désactivable dans l'onglet Contribuer.
            self.after(2500, self.envoi_auto_au_lancement)
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
        # Un message qui tient sur la ligne garde la police courante ; un
        # message long (erreur avec un chemin) passe en petit et se replie
        # sur deux lignes DANS la boîte, au lieu d'en sortir (lot 12, pt 5).
        large = self.p_corps.measure(texte) > M["ETAT_W"] - 44
        self.canvas.itemconfigure(self.txt_etat, text=texte,
                                  fill=TONALITES[ton],
                                  font=self.p_mini if large else self.p_corps)
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
        # width= OBLIGATOIRE (lot 12, point 5) : sans lui, un message long
        # (une erreur avec un chemin) sortait de la boîte crème et se faisait
        # trancher — précisément quand le joueur a besoin de le lire. La
        # bascule de police vit dans statut().
        self.txt_etat = self.canvas.create_text(
            M["CX"] + 30, M["Y_ETAT"] + M["H_ETAT"] // 2, anchor="w",
            font=self.p_corps, fill=TONALITES["neutre"], text="",
            width=M["ETAT_W"] - 44)
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
        que de secours si aucun launcher n'est trouvable.

        ⚠️ `os.startfile` N'EXISTE QUE SOUS WINDOWS : ailleurs c'est un
        AttributeError, que `except OSError` ne rattrapait pas. Plutôt que de
        deviner comment lancer un .exe Windows depuis Linux (Wine ? Lutris ?
        un préfixe ? — je ne peux rien en éprouver), on le DIT au joueur.
        Un message honnête vaut mieux qu'un lancement inventé."""
        if not hasattr(os, "startfile"):
            self.statut("alerte", "Sur ce système, le Hub ne sait pas lancer "
                                  "le jeu à ta place — lance-le comme "
                                  "d'habitude. Tout le reste fonctionne.")
            return
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

    def _lien_texte(self, x, y, texte, commande, tags, couleur=P_TEXTE,
                    survol=None, ancre="w"):
        """Un lien cliquable dessiné sur le canvas. Depuis le lot 12, les
        liens vivent sur des PLAQUES (fond bleu nuit) : la couleur par défaut
        est le beige des infobulles, le survol l'éclaircit. Aucun décor à
        cuire : les PNG du Hub sont figés par fabriquer_decor_hub.py."""
        if survol is None:
            survol = BEIGE_VIF if couleur in (P_TEXTE, P_TEXTE_VIF) else \
                OR_SOMBRE if couleur == ENCRE else P_TEXTE_VIF
        item = self.canvas.create_text(x, y, anchor=ancre, text=texte,
                                       font=self.p_lien, fill=couleur,
                                       tags=tags)

        def cliquer():
            # Même raison que dans BoutonImage._relache : nommer le geste
            # pour la fenêtre de plantage. Le libellé du lien EST la phrase
            # que le joueur vient de lire (« Vérifier mon installation »).
            self.geste_en_cours = texte.rstrip(" ↗›»").strip()
            commande()
        # La couleur de base est MUTABLE (le lien du contrôle passe au rouge
        # ou au vert selon le verdict) : le survol doit rendre la couleur
        # COURANTE en partant, pas celle de la création.
        self._liens_couleur = getattr(self, "_liens_couleur", {})
        self._liens_couleur[item] = couleur
        self.canvas.tag_bind(item, "<Button-1>", lambda _e: cliquer())
        self.canvas.tag_bind(item, "<Enter>", lambda _e: (
            self.canvas.itemconfigure(item, fill=survol),
            self.canvas.configure(cursor="hand2")))
        self.canvas.tag_bind(item, "<Leave>", lambda _e: (
            self.canvas.itemconfigure(
                item, fill=self._liens_couleur.get(item, couleur)),
            self.canvas.configure(cursor="")))
        return item

    def _lien_recolorer(self, item, couleur):
        self._liens_couleur = getattr(self, "_liens_couleur", {})
        self._liens_couleur[item] = couleur
        self.canvas.itemconfigure(item, fill=couleur)

    def _titre_vue(self, vue, tags):
        """Le titre de la vue : or vif + contour noir, cuit dans un décor
        (arbitrage de Dan, 28/07 — le traitement des titres du jeu, sans
        plaque). En encre sur le bois, il mesurait 3,2:1."""
        h = self.decor.manifeste.get("titre_" + vue, {}).get("h", 34)
        self.decor.poser(self.canvas, "titre_" + vue, M["CX"],
                         M["Y_TITRE"] - h // 2, tags=tags)

    # ------------------------------------------------------------- ACCUEIL
    def _construire_accueil(self):
        t = ("vue_accueil",)
        c, cx = self.canvas, M["CX"]
        self._titre_vue("accueil", t)
        # Grand état général — sur PLAQUE d'infobulle (lot 12, point 2) : en
        # encre sur le bois, le verdict mesurait 1,4:1 et n'était distingué
        # que par la teinte — nul pour un joueur daltonien. La pastille
        # double le verdict, le TEXTE porte toujours le sens.
        y = 92
        self.decor.poser(c, "plaque_verdict", cx, y, tags=t)
        self.acc_pastille = self.decor.poser(c, "pastille_grise",
                                             cx + 26, y + 16, tags=t)
        self.acc_etat = c.create_text(cx + 64, y + 27, anchor="w",
                                      text="Vérification…",
                                      font=self.p_gros, fill=P_OR,
                                      tags=t)
        # Le lien du contrôle d'installation. Il vit ICI, sur l'accueil, et
        # pas au fond d'un fichier d'aide : les douze joueurs bloqués en neuf
        # jours n'ont ouvert aucun fichier d'aide. Sur le bois il mesurait
        # 1,4:1 — invisible pour ceux-là mêmes à qui il était destiné.
        self.acc_controle = self._lien_texte(
            cx + 64, y + 57, "Vérifier mon installation ↗",
            self.controler_installation, t)
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
        # Le filet séparateur des infobulles du jeu, sous le titre.
        self.decor.poser(c, "filet_nouvelles", cx + 24, y + 44, tags=t)
        self.acc_note = c.create_text(
            cx + 24, y + 60, anchor="nw", text="Chargement du patch-note…",
            font=self.p_corps, fill=ENCRE_DOUCE, width=M["CW"] - 48, tags=t)
        # « Tout lire » : c'était le seul lien sans survol ni curseur, et
        # l'or sombre ne tient que 3,5:1 sur parchemin — encre soulignée.
        self._lien_texte(cx + M["CW"] - 24, y + 30, "Tout lire ↗",
                         lambda: webbrowser.open(logique.PAGE_RELEASES),
                         t, couleur=ENCRE, survol=OR_SOMBRE, ancre="e")
        self.boutons_accueil = ()

    def _controle_fond(self):
        """Le contrôle lit le disque (sauvegardes, listes d'addons) : jamais
        dans le fil de l'interface."""
        try:
            points = logique.controler_installation(self.jeu)
        except Exception:
            points = []
        self._sur_canvas(self._apres_controle, points)

    def _apres_controle(self, points):
        self.controle = points
        self.rafraichir_accueil()
        # Le contrôle arrive APRÈS la vérification réseau : on repasse la
        # barre d'état pour qu'elle porte le verdict le plus récent.
        if self.etat_trad in ETATS_TRAD:
            self.appliquer_trad(self.etat_trad)

    def rafraichir_accueil(self):
        c = self.canvas
        # Le lien du contrôle porte son propre verdict : « à corriger » en
        # rouge, « à vérifier toi-même » en orange (la case du lanceur, qu'on
        # ne peut honnêtement pas lire), « vérifiée » en vert — avec le
        # NOMBRE de points contrôlés : on sait ce qui a été vérifié, pas
        # seulement « ça va ». Teintes claires : le lien vit sur la plaque.
        if self.controle is None:
            libelle, couleur = "Vérifier mon installation ↗", P_TEXTE
        else:
            _bien, soucis, inconnus = logique.resume_controle(self.controle)
            if soucis:
                libelle, couleur = ("%d point(s) à corriger ↗" % soucis,
                                    P_ROUGE)
            elif inconnus:
                libelle, couleur = ("%d chose(s) à vérifier toi-même ↗"
                                    % inconnus, P_ORANGE)
            else:
                libelle, couleur = ("Installation vérifiée — %d points "
                                    "contrôlés ↗" % len(self.controle),
                                    P_VERT)
        c.itemconfigure(self.acc_controle, text=libelle)
        self._lien_recolorer(self.acc_controle, couleur)

        # État général : traduction + dossier. La pastille (Indicator du
        # jeu) double le verdict ; le texte porte toujours le sens.
        soucis = (logique.resume_controle(self.controle)[1]
                  if self.controle else 0)
        if not logique.jeu_valide(self.jeu):
            texte, coul, bille = "Choisis le dossier du jeu", P_ORANGE, "jaune"
        elif soucis:
            # JAMAIS de « tout est à jour » par-dessus un contrôle en échec :
            # c'est exactement ce qui a envoyé douze joueurs sur le Discord.
            texte, coul, bille = ("Installé, mais quelque chose bloque",
                                  P_ROUGE, "rouge")
        elif self.etat_trad == "ajour":
            texte, coul, bille = "Tout est à jour", P_VERT, "verte"
        elif self.etat_trad == "maj":
            texte, coul, bille = "Une mise à jour t'attend", P_OR, "jaune"
        elif self.etat_trad == "absente":
            texte, coul, bille = "Traduction à installer", P_OR, "jaune"
        elif self.etat_trad == "injoignable":
            texte, coul, bille = "Serveur injoignable", P_ROUGE, "rouge"
        else:
            texte, coul, bille = "Vérification…", P_TEXTE, "grise"
        c.itemconfigure(self.acc_etat, text=texte, fill=coul)
        if self.acc_pastille:
            c.itemconfigure(self.acc_pastille,
                            image=self.decor.photo("pastille_" + bille))
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
        self._titre_vue("traduction", t)
        y = self.y_pan_or = 96
        self.decor.poser(c, "panneau_or", cx, y, tags=t)
        centre = cx + M["CW"] // 2
        self.trad_titre = c.create_text(centre, y + 62, text="Vérification…",
                                        font=self.p_gros, fill=OR_SOMBRE,
                                        tags=t)
        # La pastille double le verdict (Indicator du jeu) : posée à gauche
        # du titre, recalée à chaque changement d'état (le titre est centré).
        self.trad_pastille = self.decor.poser(c, "pastille_grise",
                                              centre - 120, y + 51, tags=t)
        self.trad_sous = c.create_text(centre, y + 96, text="",
                                       font=self.p_soustitre,
                                       fill=ENCRE_DOUCE, tags=t)
        self.trad_badge = self.decor.poser(
            c, "badge_ok", cx + M["CW"] - 92, y + 34, tags=t)
        c.itemconfigure(self.trad_badge, state="hidden")
        # Bouton principal + barre de progression (au même endroit)
        self.y_action = y + 138
        self.btn_trad = BoutonImage(
            self, "btn_maj", centre - M["BTN_L_W"] // 2, self.y_action,
            tags=t)
        self.btn_trad.cacher()
        self.barre_trad = self._construire_barre(centre, self.y_action + 12,
                                                 t)
        # (« trad_verse » a disparu : élément mort, jamais renseigné.)
        # La BOÎTE À OUTILS (lot 12, règle n° 1) : dossier du jeu, mise à
        # jour de l'application et liens de secours quittent le bois — où ils
        # mesuraient 1,4 à 2,7:1 — pour UNE plaque d'infobulle, à un seul
        # endroit.
        y2 = y + M["PAN_OR_H"] + 18
        self.decor.poser(c, "plaque_outils", cx, y2, tags=t)
        r1, r2, r3 = y2 + 22, y2 + 52, y2 + 82
        c.create_text(cx + 24, r1, anchor="w", text="Dossier du jeu :",
                      font=self.p_corps, fill=P_TEXTE_VIF, tags=t)
        self.trad_dossier = c.create_text(
            cx + 142, r1, anchor="w", text="—", font=self.p_petit,
            fill=P_TEXTE, width=M["CW"] - 300, tags=t)
        self.btn_changer = BoutonImage(
            self, "btn_changer", cx + M["CW"] - M["BTN_P_W"] - 16,
            r1 - M["BTN_P_H"] // 2, commande=self.changer_dossier, tags=t)
        # Mise à jour de l'APPLICATION elle-même : le Hub remplace le
        # Compagnon (décision de Dan, 23/07), il doit donc porter la même
        # chaîne d'auto-mise à jour que lui. Sur le bois : 1,4:1 — un joueur
        # ne pouvait littéralement pas voir qu'une version l'attendait.
        self.lien_appli = c.create_text(
            cx + 24, r2, anchor="w",
            text="Une nouvelle version de l'application est disponible — "
                 "cliquer ici pour l'installer.",
            font=self.p_lien, fill=P_OR, tags=t)
        c.itemconfigure(self.lien_appli, state="hidden")
        c.tag_bind(self.lien_appli, "<Button-1>",
                   lambda e: self.mettre_a_jour_appli())
        c.tag_bind(self.lien_appli, "<Enter>",
                   lambda e: c.configure(cursor="hand2"))
        c.tag_bind(self.lien_appli, "<Leave>",
                   lambda e: c.configure(cursor=""))
        # Les deux sorties : contrôler, et partir proprement. « Tout
        # désinstaller » reste un lien — pas une action qu'on propose, une
        # action qu'on doit pouvoir TROUVER (trois joueurs l'ont cherchée,
        # dont un en colère le 26/07 : à 1,7:1, ils ne cherchaient pas mal).
        self._lien_texte(cx + 24, r3, "Vérifier mon installation ↗",
                         self.controler_installation, t)
        self._lien_texte(cx + M["CW"] - 176, r3, "Tout désinstaller ↗",
                         self.tout_desinstaller, t, couleur=P_ROUGE,
                         survol="#ffb39e")
        self.boutons_traduction = (self.btn_trad, self.btn_changer)
        self.etat_trad = "verification"

    def _construire_barre(self, centre, y, tags):
        """Barre de progression : rail creux + bande dorée recadrée."""
        rail = self.decor.poser(self.canvas, "barre_creuse",
                                centre - M["BARRE_W"] // 2, y, tags=tags)
        bande = self.canvas.create_image(
            centre - M["BARRE_W"] // 2 + 2, y + 2, anchor="nw", tags=tags)
        # Le « % » vit AU-DESSUS de la jauge, en encre sur le parchemin
        # (lot 12, point 4) : posé sur le rail sombre, il mesurait 1,2:1 —
        # illisible pendant les 1,4 Go du téléchargement des voix.
        pct = self.canvas.create_text(centre, y - 12,
                                      text="", font=self.p_petit,
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
        # JAMAIS de « tu es à jour » avec sa pastille verte par-dessus un
        # contrôle en échec. C'est toute l'affaire des douze joueurs bloqués
        # en neuf jours : le Hub était vert, le jeu était en anglais, et rien
        # ne disait lequel des deux avait raison. Le panneau, le badge et la
        # barre d'état changent ensemble — un seul verdict à l'écran.
        soucis = (logique.resume_controle(self.controle)[1]
                  if self.controle else 0)
        if soucis and etat in ("ajour", "reussie"):
            fiche = dict(fiche,
                         titre="Installée, mais bloquée",
                         couleur=ROUGE, badge=False, ton="erreur",
                         pastille="rouge",
                         bouton=None,
                         sous="Version {vi} en place — le jeu ne l'affiche "
                              "pas encore.",
                         statut="Installée, mais %d point(s) empêchent la "
                                "traduction de s'afficher — clique "
                                "« Vérifier mon installation »." % soucis)
        c = self.canvas
        c.itemconfigure(self.trad_titre, text=fiche["titre"],
                        fill=fiche["couleur"])
        # La pastille suit le verdict : recalée à gauche du titre centré.
        if self.trad_pastille:
            c.itemconfigure(self.trad_pastille,
                            image=self.decor.photo(
                                "pastille_" + fiche["pastille"]))
            centre = M["CX"] + M["CW"] // 2
            demi = self.p_gros.measure(fiche["titre"]) // 2
            c.coords(self.trad_pastille, centre - demi - 34,
                     self.y_pan_or + 51)
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
                             "btn_admin": self.relancer_admin}
                self.btn_trad.configurer(
                    fiche["bouton"], commandes[fiche["bouton"]])
                self.btn_trad.montrer()
            else:
                self.btn_trad.cacher()
            self._barre_montrer(self.barre_trad,
                                bool(fiche.get("progression")))
        c.itemconfigure(self.trad_dossier, text=self.jeu or
                        "aucun — choisis-le avec le bouton Changer")
        c.itemconfigure(self.lien_appli,
                        state="normal" if self._maj_appli_proposable()
                        else "hidden")
        self.statut(fiche["ton"], fiche["statut"].format(**fmt))
        if self.vue == "accueil":
            self.rafraichir_accueil()

    def changer_dossier(self):
        # L'ancien libellé — « celui qui contient Interface » — enseignait la
        # mauvaise règle : Data\enUS et Sound contiennent eux aussi un
        # dossier Interface, et c'est comme ça qu'on installe à côté.
        dossier = filedialog.askdirectory(
            title="Choisis le dossier du jeu (celui qui contient "
                  "Ascension.exe)")
        if not dossier:
            return
        # On corrige tout seul quand on peut (le joueur a désigné le dossier
        # du launcher, ou il est descendu jusqu'à Interface\AddOns), et on
        # refuse en EXPLIQUANT quand on ne peut pas. Jamais d'installation
        # silencieuse dans un dossier que le jeu ne lira pas.
        from tkinter import messagebox
        racine, note = logique.corriger_dossier_jeu(dossier)
        if not racine:
            # Une boîte, pas la barre d'état : la barre est réécrite par la
            # vérification qui suit, et ce message-là doit être lu.
            messagebox.showwarning("Ce n'est pas le dossier du jeu", note)
            self.statut("erreur", note)
            return
        if note:
            messagebox.showinfo("Dossier du jeu", note)
        self.jeu = racine
        self.cfg["jeu"] = racine
        logique.sauver_config(self.cfg)
        self.version_locale = logique.version_installee(racine)
        self.verifier()
        self.rafraichir_voix()
        self.rafraichir_addons()
        self._fil(self._controle_fond)

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
        if not self.url_zip or not self.dossier_sur():
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
        except Exception as e:
            # On DIT ce qui a échoué (24/07/2026). Avant, tout finissait en
            # « serveur injoignable » : un disque plein, un antivirus ou un
            # chemin trop long envoyaient le joueur vérifier sa connexion
            # pour rien. Une mauvaise piste coûte plus cher qu'un silence.
            self._sur_canvas(self.appliquer_trad, "injoignable")
            self._sur_canvas(
                self.statut, "erreur",
                logique.raison_echec(e)
                + "  (diagnostic copié : colle-le sur le Discord)")
            # Copié d'office : personne ne pense à le faire au moment où ça
            # rate, et c'est précisément là qu'il vaut de l'or.
            self._sur_canvas(self.copier_diagnostic, True)
            return
        self.version_locale = self.version_dispo
        self._sur_canvas(self.appliquer_trad, "reussie")
        # « Installation réussie » ne veut pas dire « ça marchera » : c'est
        # là, juste après, que se jouent les deux autres causes (case du
        # lanceur, interrupteur de /afr). On relance donc le contrôle.
        self._controle_fond()

    def _maj_appli_proposable(self):
        """Doit-on MONTRER au joueur qu'une nouvelle application l'attend ?

        ⚠️ `logique.remplacement_possible()` EST LA DÉSAMORCE (ajout urgent du
        programme 23, trouvé par Tetardtek). Sans elle, un joueur Linux se
        serait vu proposer, dès la prochaine version publiée, le
        téléchargement de l'exe WINDOWS : `derniere_release()` n'apparie que
        `EXE_ATTENDU` et ne sait pas choisir par plateforme. On ne PROPOSE pas
        ce qu'on ne sait pas faire.

        C'est la première des trois barrières — celle que le joueur voit. Les
        deux autres : `mettre_a_jour_appli` (au bord de l'action) et
        `logique.lancer_remplacement` (qui refuse net). Une règle NOMMÉE et
        sans état, pour qu'un banc puisse l'éprouver sans ouvrir de fenêtre."""
        return bool(self.appli_en_retard
                    and self.url_exe
                    and logique.remplacement_possible()
                    and self.vue == "traduction")

    def mettre_a_jour_appli(self):
        """Télécharge le nouvel exe et se fait remplacer (même mécanique
        que le Compagnon v2 : lancer_remplacement échange les fichiers et
        relance). Hors exe figé (essais python), on ouvre la page."""
        if not self.url_exe:
            return
        # Deuxième barrière (programme 23). Le lien est déjà caché hors
        # Windows, mais rien ne dit qu'un autre chemin n'appellera jamais
        # cette méthode : la garde vit AUSSI ici, au bord de l'action. Et on
        # ne renvoie pas le joueur dans le vide — la page des versions
        # existe, elle, sur tous les systèmes.
        if not logique.remplacement_possible():
            webbrowser.open(logique.PAGE_RELEASES)
            self.statut("alerte", "Sur ce système, le Hub ne se met pas à "
                                  "jour tout seul — la page des versions "
                                  "vient de s'ouvrir.")
            return
        if not getattr(sys, "frozen", False):
            webbrowser.open(logique.PAGE_RELEASES)
            return
        self.statut("neutre", "Téléchargement de la nouvelle version de "
                              "l'application…")
        self._fil(self._maj_appli_fond)

    def _maj_appli_fond(self):
        try:
            # La référence d'intégrité vient des métadonnées de la release,
            # pas du fichier téléchargé (programme 9).
            sha, taille = logique.reference_asset(logique.EXE_ATTENDU)
            chemin = logique.telecharger_fichier(self.url_exe,
                                                 suffixe=".exe",
                                                 sha256_attendu=sha,
                                                 taille_attendue=taille)
        except Exception as err:
            # On DIT pourquoi. Le message d'origine était le même quelle que
            # soit la cause — or un téléchargement abîmé et une panne réseau
            # n'appellent pas le même geste du joueur, et refuser en silence
            # recrée la boucle qu'on essaie de casser (programme 9).
            self._sur_canvas(self.statut, "erreur",
                             "Mise à jour impossible — %s" % err)
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

    def copier_diagnostic(self, silencieux=False):
        """Met le relevé d'installation dans le presse-papier.

        Ajouté le 24/07/2026 : beaucoup de joueurs signalaient « je n'arrive
        pas à télécharger / trouver le dossier / installer les voix » sans
        qu'aucune donnée ne permette de trancher. Le relevé ne contient que
        des chemins et des versions — jamais d'information personnelle."""
        try:
            texte = logique.diagnostic(self.jeu)
        except Exception as e:
            texte = "Diagnostic impossible : %s: %s" % (type(e).__name__, e)
        try:
            self.clipboard_clear()
            self.clipboard_append(texte)
            self.update_idletasks()      # sans ça, Windows perd le contenu
        except Exception:
            if not silencieux:
                self.statut("erreur", "Copie impossible.")
            return
        if not silencieux:
            self.statut("succes", "Diagnostic copié — colle-le sur le "
                                  "Discord, dans le salon d'entraide.")

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
        self._titre_vue("voix", t)
        # Sous-titre CUIT (beige contouré — en encre sur le bois : ~3:1), et
        # décollé du titre : à +34, deux lignes chevauchaient les 30 px du
        # titre (lot 12, point 3).
        self.decor.poser(c, "soustitre_voix", cx, M["Y_TITRE"] + 28, tags=t)
        y = self.y_pan_voix = 140
        self.decor.poser(c, "panneau_or", cx, y, tags=t)
        centre = cx + M["CW"] // 2
        self.voix_titre = c.create_text(centre, y + 62, text="",
                                        font=self.p_gros, fill=OR_SOMBRE,
                                        tags=t)
        self.voix_pastille = self.decor.poser(c, "pastille_grise",
                                              centre - 120, y + 51, tags=t)
        self.voix_badge = self.decor.poser(
            c, "badge_ok", cx + M["CW"] - 92, y + 34, tags=t)
        c.itemconfigure(self.voix_badge, state="hidden")
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
        # La conséquence de la bascule, écrite SOUS elle : un bouton neutre
        # n'a plus la couleur pour dire « attention, ça coupe quelque
        # chose » — alors le texte le dit (arbitrage du 28/07).
        self.voix_consequence = c.create_text(
            centre, y + 274, text="", font=self.p_petit, fill=ENCRE_DOUCE,
            width=M["CW"] - 160, justify="center", tags=t)
        # La note de bas de vue quitte le bois (3,0:1) pour une plaque.
        y_note = y + M["PAN_OR_H"] + 18
        self.decor.poser(c, "plaque_note", cx, y_note, tags=t)
        c.create_text(cx + 24, y_note + M["PLAQUE_NOTE_H"] // 2, anchor="w",
                      text="Les voix vivent dans un dépôt séparé de la "
                           "traduction : l'une ne peut jamais casser "
                           "l'autre.",
                      font=self.p_petit, fill=P_TEXTE, width=M["CW"] - 48,
                      tags=t)
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
            # On ne relit pas le disque en plein téléchargement, mais on
            # RÉAPPLIQUE l'état : montrer_vue vient de rendre visibles tous
            # les items de la vue, badge compris — l'état les recorrige.
            self.appliquer_voix("telechargement")
            return
        self.appliquer_voix(self._etat_voix_disque())

    def appliquer_voix(self, etat):
        self.etat_voix = etat
        fiche = ETATS_VOIX[etat]
        c = self.canvas
        c.itemconfigure(self.voix_titre, text=fiche["titre"],
                        fill=fiche["couleur"])
        if self.voix_pastille:
            c.itemconfigure(self.voix_pastille,
                            image=self.decor.photo(
                                "pastille_" + fiche["pastille"]))
            centre = M["CX"] + M["CW"] // 2
            demi = self.p_gros.measure(fiche["titre"]) // 2
            c.coords(self.voix_pastille, centre - demi - 34,
                     self.y_pan_voix + 51)
        if self.voix_badge:
            c.itemconfigure(self.voix_badge,
                            state="normal" if (fiche.get("badge")
                                               and self.vue == "voix")
                            else "hidden")
        c.itemconfigure(self.voix_sous, text=fiche["sous"])
        c.itemconfigure(self.voix_consequence,
                        text=fiche.get("consequence", ""))
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
        # 1,4 Go déballés à la racine : c'est le pire endroit où se tromper
        # de dossier. On exige la VRAIE racine, pas « un dossier qui contient
        # Interface ».
        if not self.dossier_sur():
            return
        self.appliquer_voix("telechargement")
        self._fil(self._installer_voix_fond)

    def _installer_voix_fond(self):
        try:
            chemin = logique.telecharger_fichier(
                logique.VOIX_URL, progres=self._progres(self.barre_voix))
            logique.installer_zip(chemin, self.jeu)
        except Exception as e:
            # Même raison que pour la traduction : on nomme la panne. Les
            # voix sont un GROS zip (14 442 fichiers) — c'est là que le
            # disque plein et les chemins trop longs frappent en premier.
            self._sur_canvas(self.appliquer_voix, "erreur")
            self._sur_canvas(
                self.statut, "erreur",
                logique.raison_echec(e)
                + "  (diagnostic copié : colle-le sur le Discord)")
            self._sur_canvas(self.copier_diagnostic, True)
            return
        self._sur_canvas(self.appliquer_voix, "installees")
        self._sur_canvas(self.rafraichir_accueil)

    # --------------------------------------------------------------- ADDONS
    def _construire_addons(self):
        t = ("vue_addons",)
        c, cx = self.canvas, M["CX"]
        self._titre_vue("addons", t)
        # Sous-titre CUIT (beige contouré), décollé du titre : à +30 il le
        # chevauchait, et en encre sur le bois il mesurait ~2,7:1 (lot 12).
        self.decor.poser(c, "soustitre_addons", cx, M["Y_TITRE"] + 34,
                         tags=t)
        # LE CATALOGUE DÉFILE (lot 12, point 7). L'ancien `catalogue[:6]`
        # plafonnait à 6 cartes : le 7ᵉ addon disparaissait SANS UN MOT. Les
        # cartes vivent sur leur propre canvas (qui rogne ce qui dépasse),
        # le fond de parchemin reste immobile dessous, et une barre aux
        # textures du jeu (UI-ScrollBar-*) apparaît quand il le faut.
        self.cv_addons = tk.Canvas(self, width=M["CW"], height=M["CATA_H"],
                                   highlightthickness=0, bd=0)
        fond = self.decor.pil("fond").crop(
            (cx, M["CATA_Y"], cx + M["CW"], M["CATA_Y"] + M["CATA_H"]))
        self._fond_addons = ImageTk.PhotoImage(fond)
        self._fond_item = self.cv_addons.create_image(
            0, 0, anchor="nw", image=self._fond_addons)
        c.create_window(cx, M["CATA_Y"], window=self.cv_addons, anchor="nw",
                        tags=t)
        self.defil_addons = 0
        lier_molette(
            self.cv_addons,
            lambda e: self._defiler_addons(-crans_molette(e) * 44))
        self.cartes = []
        self.boutons_addons = []
        for i, fiche in enumerate(self.catalogue):
            self._construire_carte(i, fiche)
        # La barre : deux flèches + le pouce, sur le canvas principal, à
        # droite de la zone. Montrés seulement quand le contenu déborde.
        x_sb = cx + M["CW"] + 6
        self.fl_haut = BoutonImage(
            self, "fleche_haut", x_sb, M["CATA_Y"],
            commande=lambda: self._defiler_addons(-132), tags=t)
        self.fl_bas = BoutonImage(
            self, "fleche_bas", x_sb, M["CATA_Y"] + M["CATA_H"] - 22,
            commande=lambda: self._defiler_addons(132), tags=t)
        self.pouce = c.create_image(x_sb + 2, M["CATA_Y"] + 24, anchor="nw",
                                    image=self.decor.photo(
                                        "pouce_defilement"), tags=t)
        self.boutons_addons += [self.fl_haut, self.fl_bas]

    def _construire_carte(self, i, fiche):
        cv = self.cv_addons
        x = (i % 2) * (M["CARTE_W"] + 22)
        y = 6 + (i // 2) * (M["CARTE_H"] + 14)
        self.decor.poser(cv, "carte", x, y)
        self.decor.poser(cv, "carte_ic_" + fiche["id"], x + 16, y + 16)
        cv.create_text(x + 86, y + 26, anchor="w", text=fiche["nom"],
                       font=self.p_nom_carte, fill=ENCRE)
        cv.create_text(x + 86, y + 46, anchor="nw", text=fiche["desc"],
                       font=self.p_mini, fill=ENCRE_DOUCE,
                       width=M["CARTE_W"] - 108)
        if fiche.get("fr"):
            self.decor.poser(cv, "badge_fr", x + M["CARTE_W"] - 62, y + 14)
        # Largeur BORNÉE au couloir libre à gauche du bouton : un libellé
        # long (« module manquant : … ») passait SOUS le bouton de la carte.
        version = cv.create_text(x + 86, y + M["CARTE_H"] - 24,
                                 anchor="w", text="",
                                 font=self.p_mini, fill=ENCRE_DOUCE,
                                 width=M["CARTE_W"] - M["BTN_C_W"] - 108)
        bouton = BoutonImage(
            self, "btn_carte_bientot",
            x + M["CARTE_W"] - M["BTN_C_W"] - 14,
            y + M["CARTE_H"] - M["BTN_C_H"] - 10, canvas=cv)
        self.boutons_addons.append(bouton)
        self.cartes.append({"fiche": fiche, "version": version,
                            "bouton": bouton})

    def _defiler_addons(self, delta):
        """Fait glisser les cartes ; le fond, lui, ne bouge pas."""
        rangees = (len(self.catalogue) + 1) // 2
        contenu = 6 + rangees * (M["CARTE_H"] + 14)
        borne = max(0, contenu - M["CATA_H"])
        vise = max(0, min(borne, self.defil_addons + delta))
        if vise == self.defil_addons:
            return
        bouge = self.defil_addons - vise         # >0 : les cartes descendent
        self.defil_addons = vise
        boutons = {carte["bouton"].item for carte in self.cartes}
        for item in self.cv_addons.find_all():
            if item == self._fond_item or item in boutons:
                continue
            self.cv_addons.move(item, 0, bouge)
        for carte in self.cartes:
            carte["bouton"].deplacer(carte["bouton"].x,
                                     carte["bouton"].y + bouge)
        self._maj_defilement()

    def _maj_defilement(self):
        """Montre la barre quand le contenu déborde, et place le pouce."""
        rangees = (len(self.catalogue) + 1) // 2
        contenu = 6 + rangees * (M["CARTE_H"] + 14)
        borne = max(0, contenu - M["CATA_H"])
        visible = borne > 0 and self.vue == "addons"
        for fleche in (self.fl_haut, self.fl_bas):
            (fleche.montrer if visible else fleche.cacher)()
        if not visible:
            self.canvas.itemconfigure(self.pouce, state="hidden")
            return
        self.canvas.itemconfigure(self.pouce, state="normal")
        course = M["CATA_H"] - 48 - 24           # entre les deux flèches
        y = M["CATA_Y"] + 24 + int(course * (self.defil_addons / borne))
        x_sb = M["CX"] + M["CW"] + 8
        self.canvas.coords(self.pouce, x_sb, y)

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
                    donnees = json.load(r)
                tag = (donnees.get("tag_name") or "").lstrip("vV")
                # URL du dernier asset .zip — indispensable pour les addons qui
                # mettent la VERSION dans le nom du fichier (NomAddon_1.2.3.zip)
                # : sans elle, « Mettre à jour » retéléchargeait l'URL FIGÉE de
                # la fiche et réinstallait la vieille version.
                dossier = (fiche.get("dossier") or "").lower()
                zips = [a for a in (donnees.get("assets") or [])
                        if (a.get("name") or "").lower().endswith(".zip")]
                choisi = next((a for a in zips if dossier
                               and dossier in (a.get("name") or "").lower()),
                              zips[0] if zips else None)
                if choisi and choisi.get("browser_download_url"):
                    self.url_distantes[fiche["id"]] = choisi["browser_download_url"]
            except Exception:
                continue
            if tag:
                self.versions_distantes[fiche["id"]] = tag
        self._sur_canvas(self.rafraichir_addons)

    def dossier_sur(self):
        """Le dossier du jeu est-il la VRAIE racine ? Barrière commune à tout
        ce qui écrit ou supprime.

        Le contrôle d'installation, lui, se contente de signaler — mais poser
        des fichiers dans un faux dossier, ou annoncer « ton jeu est revenu
        en anglais » après n'avoir rien supprimé, c'est pire que ne rien
        faire. Rend True, ou False APRÈS avoir dit pourquoi."""
        if logique.racine_jeu(self.jeu):
            return True
        if self.jeu:
            self.statut("erreur",
                        "Le dossier enregistré n'est pas la racine du jeu "
                        "(« %s ») — clique « Vérifier mon installation »."
                        % self.jeu)
        else:
            self.statut("alerte", "Choisis d'abord le dossier du jeu "
                                  "(onglet Traduction → Changer).")
        return False

    def _annexes_manquantes(self, fiche):
        """Les dossiers COMPAGNONS d'un addon qui ne sont pas sur le disque.
        DragonUI en a un (DragonUI_Options) : sans lui, l'addon se charge mais
        ses options sont inaccessibles — le pire des états, parce que rien ne
        dit au joueur ce qui manque."""
        if not logique.jeu_valide(self.jeu):
            return []
        addons = os.path.join(self.jeu, "Interface", "AddOns")
        return [d for d in (fiche.get("dossiers") or [])
                if not os.path.isdir(os.path.join(addons, d))]

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
                # Installé : le bouton principal devient « Désinstaller »
                # (rouge, actionnable), au même format que « Installer ».
                nom, actif = "btn_carte_desinstaller", True
                cmd = lambda f=fiche: self.desinstaller_addon(f)
                # « Mettre à jour » prend le dessus si la release distante est
                # STRICTEMENT plus récente que la version installée.
                distante = self.versions_distantes.get(fiche["id"])
                if (fiche.get("url") and distante and installee != "?"
                        and logique.en_tuple(distante)
                        > logique.en_tuple(installee)):
                    texte = "version %s  →  %s" % (installee, distante)
                    nom, actif = "btn_carte_maj", True
                    cmd = lambda f=fiche: self.installer_addon(f)
                elif fiche.get("url") and self._annexes_manquantes(fiche):
                    # Cas des joueurs déjà servis par l'ancien Hub : DragonUI
                    # est là, DragonUI_Options non. Sans ça, leur bouton
                    # resterait sur « Désinstaller » et rien ne leur dirait
                    # qu'il leur manque le module des options.
                    texte = "module manquant : " + ", ".join(
                        self._annexes_manquantes(fiche))
                    nom, actif = "btn_carte_maj", True
                    cmd = lambda f=fiche: self.installer_addon(f)
            elif fiche.get("url"):
                texte = "non installé"
                nom, actif = "btn_carte_installer", True
                cmd = lambda f=fiche: self.installer_addon(f)
            else:
                texte = "non détecté"
                nom, actif, cmd = "btn_carte_absent", False, None
            self.cv_addons.itemconfigure(carte["version"], text=texte)
            bouton.configurer(nom, cmd, actif=actif)
            if self.vue == "addons":
                bouton.montrer()
        self._maj_defilement()

    def installer_addon(self, fiche):
        if not self.dossier_sur():
            return
        # Verrou de ré-entrance : deux clics lançaient deux installations
        # concurrentes sur le MÊME dossier — l'une fait rmtree pendant que
        # l'autre copytree, et l'addon finit à moitié posé.
        if fiche["id"] in self.installations_en_cours:
            self.statut("alerte", "%s s'installe déjà — laisse-le finir."
                                  % fiche["nom"])
            return
        self.installations_en_cours.add(fiche["id"])
        self.statut("neutre", "Téléchargement de %s…" % fiche["nom"])
        self._fil(self._installer_addon_fond, fiche)

    def _installer_addon_fond(self, fiche):
        try:
            # URL du dernier asset (résolue via l'API) si dispo, sinon l'URL de
            # la fiche : « Installer / Mettre à jour » prend TOUJOURS la dernière
            # version, même si le nom du fichier change à chaque release.
            url = self.url_distantes.get(fiche["id"]) or fiche["url"]
            chemin = logique.telecharger_fichier(url)
            poses = installer_addon_zip(chemin, self.jeu, fiche["dossier"])
        except Exception as e:
            # On NOMME la panne, comme pour la traduction et les voix : un
            # « impossible » sec envoyait le joueur sur le Discord sans rien.
            self._sur_canvas(self.statut, "erreur",
                             "Installation de %s impossible — %s"
                             % (fiche["nom"], logique.raison_echec(e)))
            return
        finally:
            self.installations_en_cours.discard(fiche["id"])
        # On dit ce qui a été posé : quand un addon se livre en plusieurs
        # dossiers (DragonUI + DragonUI_Options), le joueur voit que le
        # module d'options est bien arrivé.
        annexes = [n for n in poses if n.lower() != fiche["dossier"].lower()]
        supplement = (" (avec %s)" % ", ".join(annexes)) if annexes else ""
        self._sur_canvas(self.statut, "succes",
                         "%s installé%s. En jeu : /reload."
                         % (fiche["nom"], supplement))
        self._sur_canvas(self.rafraichir_addons)

    def desinstaller_addon(self, fiche):
        if not self.dossier_sur():
            return
        from tkinter import messagebox
        if not messagebox.askyesno(
                "Désinstaller",
                "Désinstaller « %s » ?\n\nSes fichiers seront retirés du jeu.\n"
                "Tu pourras le réinstaller depuis le Hub à tout moment."
                % fiche["nom"]):
            return
        self.statut("neutre", "Désinstallation de %s…" % fiche["nom"])
        self._fil(self._desinstaller_addon_fond, fiche)

    def _desinstaller_addon_fond(self, fiche):
        try:
            addons = os.path.join(self.jeu, "Interface", "AddOns")
            for d in [fiche["dossier"]] + (fiche.get("dossiers") or []):
                cible = os.path.join(addons, d)
                if os.path.isdir(cible):
                    shutil.rmtree(cible, ignore_errors=True)
        except Exception:
            self._sur_canvas(self.statut, "erreur",
                             "Désinstallation de %s impossible." % fiche["nom"])
            return
        self._sur_canvas(self.statut, "succes",
                         "%s désinstallé. En jeu : /reload." % fiche["nom"])
        self._sur_canvas(self.rafraichir_addons)

    # ------------------------------------------- CONTRÔLE ET DÉSINSTALLATION
    # Deux fenêtres à part, en widgets classiques : le décor du Hub est fait
    # de PNG cuits d'avance (fabriquer_decor_hub.py), et ces deux écrans ont
    # un nombre de lignes VARIABLE. Une fenêtre sobre qu'on peut relire et
    # copier vaut mieux qu'un décor qui déborde — et c'est la règle maison
    # pour tout ce qui est relevé (jamais un print, toujours du copiable).
    # Lot 12, point 8 : ces fenêtres étaient en Tk gris/moutarde, hors
    # univers — et ce sont justement les deux moments d'inquiétude du
    # joueur. Elles passent au parchemin bordé d'or, palette du Hub.
    FOND_F = "#efe2c0"           # parchemin
    PANNEAU_F = "#f7eed6"        # carte crème
    TEXTE_F = ENCRE
    DISCRET_F = ENCRE_DOUCE
    BORD_F = "#8a6a2a"           # liseré doré de la fenêtre
    PASTILLES = {"ok": (VERT, "✓"),
                 "souci": ("#a02c12", "✗"),
                 # « vrai, mais lis quand même » : visible sans faire virer
                 # tout le Hub au rouge (un voyant toujours rouge, plus
                 # personne ne le regarde).
                 "reserve": ("#5a7a1e", "≈"),
                 "inconnu": ("#9c6410", "?")}

    def _fenetre(self, titre, largeur, hauteur):
        """Une fenêtre fille sobre, centrée sur le Hub, qui ne rend la main
        qu'une fois fermée (grab) : on ne veut pas d'un contrôle
        d'installation oublié derrière la fenêtre principale."""
        f = tk.Toplevel(self)
        f.title(titre)
        f.configure(bg=self.FOND_F,
                    highlightbackground=self.BORD_F,
                    highlightcolor=self.BORD_F, highlightthickness=2)
        f.resizable(False, False)
        try:
            f.iconbitmap(logique.ressource("logo.ico"))
        except Exception:
            pass
        x = self.winfo_rootx() + (M["W"] - largeur) // 2
        y = self.winfo_rooty() + max(20, (M["H"] - hauteur) // 2)
        f.geometry("%dx%d+%d+%d" % (largeur, hauteur, x, y))
        f.transient(self)
        # ⚠️ `grab_set()` EXIGE UNE FENÊTRE DÉJÀ AFFICHÉE. Sous Windows elle
        # l'est aussitôt ; sous X11 le gestionnaire de fenêtres la « mappe »
        # quand il veut, et Tk lève « grab failed: window not viewable » —
        # le bouton « Vérifier mon installation » ne faisait donc rien du tout
        # (Tetardtek, 02/08/2026).
        #
        # On garde l'essai IMMÉDIAT (sous Windows il réussit, rigoureusement
        # comme avant), et on ne se rabat sur l'attente que s'il échoue. Au
        # bout de ~1 s on abandonne SANS bruit : une fenêtre sans grab reste
        # parfaitement utilisable, une TclError tue le bouton.
        def prendre_la_main(reste=20):
            try:
                f.grab_set()
            except tk.TclError:
                if reste and f.winfo_exists():
                    f.after(50, lambda: prendre_la_main(reste - 1))
        prendre_la_main()
        return f

    def _zone_defilante(self, parent, largeur, hauteur):
        """Une zone qui défile. Le nombre de lignes n'est pas connu d'avance
        (autant de points de contrôle que de causes, autant d'éléments à
        supprimer que le joueur en a installé) : sans défilement, le bouton
        du bas sort de l'écran — et un bouton qu'on ne voit pas est un bouton
        qui n'existe pas. Rend le cadre dans lequel empiler les lignes."""
        boite = tk.Frame(parent, bg=self.FOND_F)
        boite.pack(fill="both", expand=True, padx=18)
        toile = tk.Canvas(boite, bg=self.FOND_F, highlightthickness=0,
                          width=largeur, height=hauteur)
        barre = tk.Scrollbar(boite, orient="vertical", command=toile.yview)
        dedans = tk.Frame(toile, bg=self.FOND_F)
        fenetre = toile.create_window((0, 0), window=dedans, anchor="nw",
                                      width=largeur)

        def molette(evenement):
            toile.yview_scroll(-crans_molette(evenement), "units")

        def ajuster(_e=None):
            toile.configure(scrollregion=toile.bbox("all"))
            # Les lignes empilées dedans avalent la molette : on la relie sur
            # chaque descendant (au moment où ils existent, pas avant).
            piles = [dedans]
            while piles:
                w = piles.pop()
                lier_molette(w, molette)
                piles.extend(w.winfo_children())
            # La barre ne s'affiche que si elle sert : une barre grise inutile
            # à droite d'une liste de trois lignes fait « c'est compliqué ».
            besoin = dedans.winfo_reqheight() > hauteur
            if besoin and not barre.winfo_ismapped():
                barre.pack(side="right", fill="y")
                toile.configure(width=largeur - 16)
                toile.itemconfigure(fenetre, width=largeur - 16)
            elif not besoin and barre.winfo_ismapped():
                barre.pack_forget()
        dedans.bind("<Configure>", ajuster)
        toile.configure(yscrollcommand=barre.set)
        toile.pack(side="left", fill="both", expand=True)

        # Uniquement des liaisons LOCALES (voir `ajuster` pour les enfants).
        # Un bind_all survivrait à la fermeture de la fenêtre et lèverait une
        # TclError à chaque cran de molette dans le Hub, une par fenêtre déjà
        # fermée.
        lier_molette(toile, molette)
        return dedans

    def _bouton(self, parent, texte, commande, accent=False, **kw):
        # Or du Hub pour l'action principale, crème lisérée pour le reste —
        # plus de bouton moutarde sur gris (lot 12, point 8).
        return tk.Button(parent, text=texte, command=commande,
                         bg="#e8c25a" if accent else "#e6d6ac",
                         fg="#15130c" if accent else self.TEXTE_F,
                         activebackground="#d9b44e" if accent else "#dcc998",
                         activeforeground="#15130c" if accent else
                         self.TEXTE_F,
                         relief="flat", bd=0, padx=14, pady=7,
                         highlightbackground=self.BORD_F,
                         highlightthickness=1,
                         font=self.p_corps, cursor="hand2", **kw)

    # -------------------------------------------------- contrôle (objectif A)
    def controler_installation(self):
        """« J'ai installé, le jeu reste en anglais » — douze joueurs en neuf
        jours. On vérifie les trois causes connues et on dit, pour chacune,
        soit qu'elle est réparée, soit exactement quoi cliquer."""
        # UNE seule source de vérité. `self.controle` alimente l'accueil et
        # la barre d'état ; si la fenêtre gardait sa copie à part, une
        # réparation réussie laissait le Hub rouge jusqu'au redémarrage — le
        # joueur répare, rien ne change à l'écran, il croit que ça n'a pas
        # marché.
        self.controle = self.points_controle = logique.controler_installation(
            self.jeu)
        self.rafraichir_accueil()
        if self.etat_trad in ETATS_TRAD:
            self.appliquer_trad(self.etat_trad)
        f = self._fenetre("Vérifier mon installation", 720, 620)
        self.fen_controle = f
        tk.Label(f, text="Vérification de l'installation", bg=self.FOND_F,
                 fg=self.TEXTE_F, font=self.p_gros).pack(anchor="w",
                                                         padx=24, pady=(20, 2))
        bien, soucis, inconnus = logique.resume_controle(self.points_controle)
        if bien:
            resume, couleur = ("Tout est en place.", VERT)
        else:
            morceaux = []
            if soucis:
                morceaux.append("%d point(s) à corriger" % soucis)
            if inconnus:
                morceaux.append("%d à vérifier toi-même" % inconnus)
            resume = " · ".join(morceaux)
            couleur = "#a02c12" if soucis else "#9c6410"
        tk.Label(f, text=resume, bg=self.FOND_F, fg=couleur,
                 font=self.p_corps).pack(anchor="w", padx=24, pady=(0, 12))

        pied = tk.Frame(f, bg=self.FOND_F)
        pied.pack(side="bottom", fill="x", padx=24, pady=14)
        corps = self._zone_defilante(f, 684, 430)
        for point in self.points_controle:
            self._ligne_controle(corps, point)

        self._bouton(pied, "Copier ce relevé",
                     self._copier_controle).pack(side="left")
        self._bouton(pied, "Revérifier", self._reverifier).pack(side="left",
                                                                padx=8)
        self._bouton(pied, "Fermer", f.destroy,
                     accent=True).pack(side="right")

    def _ligne_controle(self, parent, point):
        couleur, signe = self.PASTILLES[point["etat"]]
        cadre = tk.Frame(parent, bg=self.PANNEAU_F)
        cadre.pack(fill="x", pady=3)
        tk.Label(cadre, text=signe, bg=self.PANNEAU_F, fg=couleur,
                 font=self.p_nom_carte, width=2).pack(side="left",
                                                      padx=(10, 4), pady=8)
        texte = tk.Frame(cadre, bg=self.PANNEAU_F)
        texte.pack(side="left", fill="x", expand=True, pady=8)
        tk.Label(texte, text=point["titre"], bg=self.PANNEAU_F,
                 fg=self.TEXTE_F, font=self.p_nom_carte,
                 anchor="w").pack(fill="x")
        tk.Label(texte, text=point["detail"], bg=self.PANNEAU_F,
                 fg=self.DISCRET_F, font=self.p_petit, anchor="w",
                 justify="left", wraplength=540).pack(fill="x")
        if point["reparable"]:
            self._bouton(cadre, "Réparer",
                         lambda p=point: self._reparer(p),
                         accent=True).pack(side="right", padx=10)

    def _reparer(self, point):
        if point["reparable"] == "dossier":
            self.fen_controle.destroy()
            self.changer_dossier()
            return
        fait, message = logique.reparer(self.jeu, point["reparable"])
        self.statut("succes" if fait else "alerte", message)
        self._reverifier()

    def _reverifier(self):
        self.fen_controle.destroy()
        self.version_locale = (logique.version_installee(self.jeu)
                               if logique.jeu_valide(self.jeu) else None)
        self.controler_installation()   # remet self.controle et l'affichage

    def _texte_controle(self):
        lignes = ["Contrôle d'installation AscensionFR (Hub %s)"
                  % logique.VERSION_COMPAGNON, ""]
        for p in getattr(self, "points_controle", ()):
            lignes.append("[%s] %s" % (p["etat"].upper(), p["titre"]))
            lignes.append("     " + p["detail"])
        return "\n".join(lignes)

    def _copier_controle(self):
        try:
            self.clipboard_clear()
            self.clipboard_append(self._texte_controle())
            self.update_idletasks()
            self.statut("succes", "Relevé copié — colle-le sur le Discord.")
        except Exception:
            self.statut("erreur", "Copie impossible.")

    # ------------------------------------------ désinstallation (objectif C)
    def tout_desinstaller(self):
        """Le 26/07/2026, un joueur a retiré le dossier d'addon et vidé
        %appdata% : son jeu est resté en français. Normal — le français vient
        de quatre dépôts, tous dans le dossier du JEU. On liste tout, on
        montre la liste AVANT, et on dit ce qui n'a pas pu partir."""
        # LE contrôle qui manquait : sur un dossier erroné, on ne trouvait
        # rien à supprimer dans le jeu, tout « réussissait », et la fenêtre
        # annonçait « ton jeu est revenu en anglais » alors que la traduction
        # et les 1,7 Go de voix étaient toujours là. Mot pour mot le
        # scénario du joueur en colère du 26/07.
        if not self.dossier_sur():
            return
        elements = logique.elements_desinstallation(self.jeu, self.catalogue)
        f = self._fenetre("Tout désinstaller", 760, 620)
        if not elements:
            tk.Label(f, text="Rien à retirer : ce dossier de jeu est déjà "
                             "vierge de tout ce que nous posons.",
                     bg=self.FOND_F, fg=self.TEXTE_F, font=self.p_corps,
                     wraplength=680, justify="left").pack(padx=24, pady=30)
            self._bouton(f, "Fermer", f.destroy, accent=True).pack(pady=10)
            return
        tk.Label(f, text="Voici tout ce qui va être supprimé", bg=self.FOND_F,
                 fg=self.TEXTE_F, font=self.p_gros).pack(anchor="w", padx=24,
                                                         pady=(20, 2))
        tk.Label(f, text="Rien n'est supprimé tant que tu n'as pas cliqué en "
                         "bas. Décoche ce que tu veux garder.",
                 bg=self.FOND_F, fg=self.DISCRET_F,
                 font=self.p_petit).pack(anchor="w", padx=24, pady=(0, 12))
        pied = tk.Frame(f, bg=self.FOND_F)
        pied.pack(side="bottom", fill="x", padx=24, pady=14)
        corps = self._zone_defilante(f, 724, 430)
        cases = []
        for element in elements:
            var = tk.BooleanVar(value=element["coche"])
            cases.append((var, element))
            cadre = tk.Frame(corps, bg=self.PANNEAU_F)
            cadre.pack(fill="x", pady=3)
            tk.Checkbutton(
                cadre, variable=var, bg=self.PANNEAU_F, fg=self.TEXTE_F,
                activebackground=self.PANNEAU_F, selectcolor="#fffbe8",
                text="%s   (%s, %d élément(s))"
                     % (element["libelle"], _taille_lisible(element["taille"]),
                        len(element["chemins"])),
                font=self.p_nom_carte, anchor="w",
                highlightthickness=0, bd=0).pack(fill="x", padx=8, pady=(8, 0))
            detail = element["note"] or ""
            apercu = " · ".join(element["chemins"][:3])
            if len(element["chemins"]) > 3:
                apercu += " · … (%d de plus)" % (len(element["chemins"]) - 3)
            tk.Label(cadre, text=(detail + "\n" if detail else "") + apercu,
                     bg=self.PANNEAU_F, fg=self.DISCRET_F, font=self.p_mini,
                     anchor="w", justify="left",
                     wraplength=650).pack(fill="x", padx=34, pady=(0, 8))
        self._bouton(pied, "Annuler", f.destroy).pack(side="left")
        self._bouton(pied, "Supprimer ce qui est coché",
                     lambda: self._desinstaller(f, cases),
                     accent=True).pack(side="right")

    def _desinstaller(self, fenetre, cases):
        from tkinter import messagebox
        choisis = [e for var, e in cases if var.get()]
        if not choisis:
            self.statut("alerte", "Rien de coché : rien n'a été supprimé.")
            return
        if not messagebox.askyesno(
                "Tout désinstaller",
                "Supprimer définitivement %d élément(s) ?\n\n%s\n\n"
                "Le jeu doit être fermé."
                % (len(choisis),
                   "\n".join("• " + e["libelle"] for e in choisis)),
                parent=fenetre):
            return
        resultats, tout = logique.desinstaller_tout(self.jeu, choisis)
        fenetre.destroy()
        # « Revenu en anglais » n'est vrai que si la TRADUCTION est partie.
        # Ne cocher que « les réglages du Hub » et tout supprimer avec succès
        # ne remet évidemment rien en anglais — et l'annoncer serait refaire,
        # en plus poli, l'erreur qui a mis un joueur en colère le 26/07.
        anglais = tout and any(e["cle"] == "traduction" for e in choisis)
        self._rapport_desinstallation(resultats, tout, anglais)

    def _rapport_desinstallation(self, resultats, tout, anglais=True):
        f = self._fenetre("Désinstallation", 720, 480)
        titre = ("Ton jeu est revenu en anglais." if anglais else
                 "C'est fait." if tout else "Il reste quelque chose.")
        tk.Label(f, text=titre, bg=self.FOND_F,
                 fg=VERT if tout else "#9c6410",
                 font=self.p_gros).pack(anchor="w", padx=24, pady=(20, 4))
        if anglais:
            sous = ("Relance le jeu : les textes, les écrans de connexion et "
                    "les voix sont revenus à l'original. Si un personnage "
                    "reste en français, c'est un cache d'affichage : il part "
                    "à la reconnexion.")
        elif tout:
            sous = ("Tout ce que tu avais coché est parti. La traduction, "
                    "elle, n'était pas dans la liste : ton jeu reste en "
                    "français.")
        else:
            sous = ("Ce qui n'a pas pu être retiré est listé ci-dessous, avec "
                    "la raison. La cause la plus fréquente est le jeu (ou le "
                    "launcher) resté ouvert.")
        tk.Label(f, text=sous, bg=self.FOND_F, fg=self.DISCRET_F,
                 font=self.p_petit, wraplength=660,
                 justify="left").pack(anchor="w", padx=24, pady=(0, 12))

        def fermer():
            f.destroy()
            self._apres_purge()
        # La croix de la fenêtre doit faire la même chose que le bouton :
        # sinon le Hub reste sur « Tu es à jour » et sa pastille verte alors
        # que la traduction vient d'être supprimée.
        f.protocol("WM_DELETE_WINDOW", fermer)
        self._bouton(f, "Fermer", fermer, accent=True).pack(side="bottom",
                                                            pady=14)
        corps = self._zone_defilante(f, 684, 300)
        for libelle, ok, message in resultats:
            couleur, signe = self.PASTILLES["ok" if ok else "souci"]
            ligne = tk.Frame(corps, bg=self.PANNEAU_F)
            ligne.pack(fill="x", pady=2)
            tk.Label(ligne, text=signe, bg=self.PANNEAU_F, fg=couleur,
                     font=self.p_nom_carte, width=2).pack(side="left",
                                                          padx=(10, 4))
            tk.Label(ligne, text="%s — %s" % (libelle, message),
                     bg=self.PANNEAU_F, fg=self.TEXTE_F, font=self.p_petit,
                     anchor="w", justify="left",
                     wraplength=600).pack(side="left", fill="x", pady=8)

    def _apres_purge(self):
        """Après une désinstallation, le Hub doit se remettre à jour : sinon
        il continue d'afficher « tu es à jour » sur une traduction absente."""
        # On relit le disque et on en DÉDUIT l'état, au lieu de forcer
        # « absente » : une désinstallation partielle (le joueur n'a coché que
        # les voix) laisse la traduction en place, et lui annoncer qu'elle a
        # disparu serait faux dans l'autre sens.
        self.version_locale = (logique.version_installee(self.jeu)
                               if logique.jeu_valide(self.jeu) else None)
        if not self.version_dispo:
            etat = self.etat_trad
        elif not self.version_locale:
            etat = "absente"
        elif logique.mise_a_jour_dispo(self.version_locale,
                                       self.version_dispo):
            etat = "maj"
        else:
            etat = "ajour"
        self.appliquer_trad(etat)
        self.rafraichir_voix()
        self.rafraichir_addons()
        self.rafraichir_accueil()
        self._fil(self._controle_fond)

    # ----------------------------------------------------------- CONTRIBUER
    def _construire_contribuer(self):
        t = ("vue_contribuer",)
        c, cx = self.canvas, M["CX"]
        self._titre_vue("contribuer", t)
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
        # LE BOUTON FANTÔME, REPOSÉ (bloc B du programme 23). Le message
        # d'échec d'envoi renvoyait à « un bouton ci-dessous » qui n'existait
        # nulle part, et le code copiait à la place le RELEVÉ D'INSTALLATION :
        # un joueur qui suivait l'instruction collait la mauvaise chose sur le
        # Discord en croyant bien faire. Le voici, et il copie bien le rapport.
        self.btn_copier = BoutonImage(
            self, "btn_copier", cx + 34 + M["BTN_M_W"] + 20, y + 220,
            commande=self.copier_rapport, tags=t)
        # Le compteur descend SOUS les deux boutons : il occupait la place où
        # le second se pose.
        self.contrib_etat = c.create_text(
            cx + 34, y + 220 + M["BTN_M_H"] + 22,
            anchor="w", text="", font=self.p_petit, fill=ENCRE_DOUCE,
            tags=t)
        self.boutons_contribuer = (self.btn_envoyer, self.btn_copier)
        self.envoi_en_cours = False
        # Case « envoi automatique » — LA VRAIE case du jeu (UI-CheckBox),
        # plus un « [x] » en note de bas de page : elle commande un envoi de
        # données par défaut, elle doit se voir et se cocher (lot 12, pt 9).
        y_case = y + 220 + M["BTN_M_H"] + 58
        self.contrib_case = self.decor.poser(c, "case_vide", cx + 30,
                                             y_case - 13, tags=t)
        self.contrib_auto = c.create_text(
            cx + 30 + 34, y_case, anchor="w",
            text="Envoyer automatiquement ma récolte à chaque ouverture "
                 "du Hub",
            font=self.p_corps, fill=ENCRE, tags=t)
        for item in (self.contrib_case, self.contrib_auto):
            if item is None:
                continue
            c.tag_bind(item, "<Button-1>",
                       lambda e: self._basculer_envoi_auto())
            c.tag_bind(item, "<Enter>",
                       lambda e: c.configure(cursor="hand2"))
            c.tag_bind(item, "<Leave>",
                       lambda e: c.configure(cursor=""))
        self._maj_case_auto()

    def rafraichir_contrib(self):
        total, attente = self.stats
        if total:
            texte = ("Tu as fait traduire %s textes. Merci !"
                     % "{:,}".format(total).replace(",", " "))
        else:
            texte = "Joue avec l'addon, puis reviens envoyer ta récolte."
        self.canvas.itemconfigure(self.contrib_compteur, text=texte)
        if not self.envoi_en_cours:
            # Le compteur en attente (repris de l'ancien Compagnon, redemandé
            # par Dan le 24/07). L'attente vient de lire_stats — les entrées
            # déjà parties ne comptent plus ; il retombe donc à 0 dès l'envoi.
            if attente and attente > 0:
                etat = ("Vous avez %s texte(s) en attente d'envoi."
                        % "{:,}".format(attente).replace(",", " "))
            else:
                etat = "Aucun texte en attente d'envoi."
            self.canvas.itemconfigure(self.contrib_etat, text=etat)
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

    # ------------------------------------------------------ envoi automatique
    def _maj_case_auto(self):
        if self.contrib_case:
            self.canvas.itemconfigure(
                self.contrib_case,
                image=self.decor.photo(
                    "case_cochee" if self.cfg.get("envoi_auto", True)
                    else "case_vide"))

    def _basculer_envoi_auto(self):
        self.cfg["envoi_auto"] = not self.cfg.get("envoi_auto", True)
        logique.sauver_config(self.cfg)
        self._maj_case_auto()

    def envoi_auto_au_lancement(self):
        if not self.cfg.get("envoi_auto", True) or self.envoi_en_cours:
            return
        if not (logique.WEBHOOK_RAPPORTS and logique.jeu_valide(self.jeu)):
            return
        self.envoi_en_cours = True
        self._fil(self._envoi_auto_fond)

    def _envoi_auto_fond(self):
        envoye = 0
        try:
            deja = logique.deja_envoyees()
            rapport, nombre, empreintes = logique.construire_rapport(
                self.jeu, deja)
            if nombre:
                caches, _ = logique.extraire_caches(self.jeu)
                logique.envoyer_rapport_discord(rapport, caches)
                logique.noter_envoyees(self.cfg, empreintes)
                envoye = nombre
        except Exception:
            envoye = -1        # silencieux : on réessaiera au prochain lancement
        self._sur_canvas(self._fin_envoi_auto, envoye)

    def _fin_envoi_auto(self, envoye):
        self.envoi_en_cours = False
        if envoye > 0:
            self.statut("succes",
                        "Merci ! %s texte(s) envoyé(s) automatiquement."
                        % "{:,}".format(envoye).replace(",", " "))
        self._fil(self._lire_stats)

    def envoyer_rapport(self):
        if self.envoi_en_cours:
            return
        self.envoi_en_cours = True
        self.btn_envoyer.configurer("btn_envoyer_gris", actif=False)
        self.canvas.itemconfigure(self.contrib_etat, text="Envoi…")
        self.statut("neutre", "Préparation du rapport…")
        self._fil(self._envoyer_fond)

    def copier_rapport(self):
        """Le repli du bloc B : mettre LE RAPPORT dans le presse-papier.

        Ce n'est pas `copier_diagnostic` — ce sont deux choses différentes, et
        c'est exactement la confusion qu'on répare : le message d'échec parlait
        du rapport, le code copiait le relevé d'installation, et le joueur
        collait la mauvaise chose sur le Discord en croyant bien faire.

        Repris du Compagnon v2 (`compagnon.Compagnon.copier_rapport`), qui est
        une MÉTHODE de son ancienne interface et non une fonction du moteur :
        elle ne pouvait pas être appelée telle quelle depuis le Hub. Même
        règle qu'en v2 : on donne TOUT, même le déjà-envoyé (le joueur peut
        vouloir montrer son rapport complet), et on ne marque donc rien comme
        parti — rien ne prouve qu'il collera."""
        if not logique.jeu_valide(self.jeu):
            self.statut("alerte", "Choisis d'abord le dossier du jeu, dans "
                                  "l'onglet Traduction.")
            return
        try:
            rapport, total, _ = logique.construire_rapport(self.jeu)
        except Exception as e:
            self.statut("erreur", "Lecture impossible — %s"
                        % logique.raison_echec(e))
            return
        if not total:
            self.statut("alerte", "Rien à signaler pour l'instant — joue "
                                  "avec l'addon, puis fais /reload en jeu.")
            return
        if not self._copier_texte(rapport):
            return
        self.statut("succes", "Rapport copié (%s entrée(s)) — colle-le sur "
                              "le Discord avec Ctrl+V."
                    % "{:,}".format(total).replace(",", " "))

    def _copier_texte(self, texte):
        """Le presse-papier, en un seul endroit. Rend False si ça a raté —
        et le dit, au lieu de laisser croire que c'est copié."""
        try:
            self.clipboard_clear()
            self.clipboard_append(texte)
            self.update_idletasks()      # sans ça, Windows perd le contenu
            return True
        except Exception:
            self.statut("erreur", "Copie impossible sur ce système.")
            return False

    def _envoyer_fond(self):
        rapport = None
        try:
            deja = logique.deja_envoyees()
            rapport, nombre, empreintes = logique.construire_rapport(
                self.jeu, deja)
            if not nombre:
                self._sur_canvas(self._apres_envoi, "vide",
                                 "Rien de nouveau à envoyer — tout est "
                                 "déjà parti. Rejoue un peu !")
                return
            # « caches, _ » et PAS « caches » : extraire_caches rend un COUPLE
            # (octets, nombre). Le Hub avait perdu le « , _ » de l'ancien
            # Compagnon (interface_v2.py l. 1438) : on passait alors le tuple
            # entier à l'envoi, qui fait « bytes + caches » -> TypeError. Tout
            # envoi de rapport échouait donc depuis la 3.0.0, et le joueur
            # lisait « vérifie ta connexion » alors que le réseau allait bien.
            # Corrigé le 24/07/2026, reproduit par un test hors ligne.
            caches, _ = logique.extraire_caches(self.jeu)
            logique.envoyer_rapport_discord(rapport, caches)
            logique.noter_envoyees(self.cfg, empreintes)
        except Exception as e:
            # BLOC B DU PROGRAMME 23 — le message et le geste disent enfin la
            # MÊME chose. Avant : le texte renvoyait à « un bouton ci-dessous »
            # qui n'existait pas, et le code copiait `copier_diagnostic`,
            # c'est-à-dire le RELEVÉ D'INSTALLATION — pas le rapport. Le
            # joueur qui suivait l'instruction collait la mauvaise chose.
            # Maintenant : le bouton existe (btn_copier), et c'est bien le
            # rapport qui part dans le presse-papier — comme le faisait déjà
            # le Compagnon v2 (`_envoi_rate`).
            if rapport:
                self._sur_canvas(self._copier_texte, rapport)
                suite = ("  Ton rapport a été COPIÉ à la place : colle-le "
                         "sur le Discord (Ctrl+V).")
            else:
                suite = ("  Réessaie, ou clique « Copier mon rapport » pour "
                         "le coller toi-même sur le Discord.")
            self._sur_canvas(self._apres_envoi, "horsligne",
                             logique.raison_echec(e) + suite)
            return
        self._sur_canvas(self._apres_envoi, "reussi",
                         "Rapport envoyé — merci pour le coup de main !")
        self._sur_canvas(self._lire_stats_apres_envoi)

    def _lire_stats_apres_envoi(self):
        self._fil(self._lire_stats)

    def _apres_envoi(self, etat, message):
        self.envoi_en_cours = False
        # Le message d'issue (« Rapport envoyé », erreur…) va dans la barre de
        # statut ; le compteur (contrib_etat) reste réservé au nombre en
        # attente, pour que Dan le voie toujours et le voie retomber à 0.
        self.statut("succes" if etat in ("reussi", "vide") else "erreur",
                    message)
        if etat in ("reussi", "vide"):
            # Tout est parti : compteur à 0 immédiatement (lire_stats le
            # reconfirmera juste après, mais on ne fait pas attendre l'œil).
            self.stats = (self.stats[0], 0)
        self.rafraichir_contrib()

    # ------------------------------------------------------------- mode démo
    def _peupler_demo(self):
        """États factices pour les captures d'écran (aucun réseau)."""
        self.version_locale, self.version_dispo = "3.0.1", "3.1.0"
        self.note = ("## 3.1.0 — le canal français & la communauté\n"
                     "- Canal « AscensionFR » : retrouve les francophones "
                     "du serveur en un clic\n"
                     "- Pseudos colorés, onglet dédié, recherche de groupe\n"
                     "- AscensionFR-Pêche rejoint le catalogue\n"
                     "- Effets « Utiliser » des objets enfin traduits\n"
                     "- DragonUI : les auras des barres de vie remarchent\n"
                     "\nUn mot de Dan :\n"
                     "On parle surtout anglais sur le serveur — avec le "
                     "canal, on va enfin se retrouver entre francophones. "
                     "Merci pour vos idées et vos retours, c'est vous qui "
                     "faites avancer tout ça. Cœur sur vous <3\n")
        self.stats = (12847, 315)
        self.appliquer_trad({"accueil": "ajour", "traduction": "maj",
                             "voix": "ajour", "addons": "ajour",
                             "contribuer": "ajour"}.get(self.demo, "ajour"))
        self.rafraichir_contrib()
        self.rafraichir_accueil()


# --------------------------------------------------------------------------- #
def _panne_de_fil():
    """Cible de `--planter fil` : la panne arrive dans un fil de fond, là où
    aucun rappel Tk ne peut l'attraper."""
    raise RuntimeError("panne d'essai dans un fil de fond (--planter fil)")


def main():
    """L'enveloppe. RIEN ne doit remonter au-dessus d'ici.

    Sinon, sous Windows, PyInstaller affiche SA boîte — « Unhandled exception
    in script », en anglais, avec le traceback brut — par-dessus la nôtre :
    deux fenêtres pour un seul défaut, et c'est la moins lisible qui reste en
    mémoire. Sous Linux il n'affiche rien du tout. Une seule fenêtre, la
    nôtre, sur les deux systèmes."""
    try:
        _main()
    except Exception:
        montrer_plantage(_APPLI, "le démarrage du Hub")


def _main():
    global _APPLI
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    # Les portes n°2 et n°3 du plantage visible (programme 23). Posées AVANT
    # toute construction : un décor manquant, un assets/ pas embarqué, une
    # dépendance absente lèvent ici, et c'est le pire moment pour être muet.
    sys.excepthook = _sur_hors_boucle
    threading.excepthook = _sur_fil
    args = sys.argv[1:]
    demo = None
    capture = None
    if "--demo" in args:
        i = args.index("--demo")
        demo = args[i + 1] if i + 1 < len(args) else "accueil"
    if "--capture" in args:
        i = args.index("--capture")
        capture = args[i + 1] if i + 1 < len(args) else "hub.png"
    # Une panne d'essai, exprès, pour prouver que le joueur voit bien quelque
    # chose. `--planter rappel` casse un bouton, `--planter demarrage` casse
    # la construction, `--planter fil` casse une tâche de fond : les trois
    # portes. C'est le banc du bloc C — il ne s'active QUE sur l'option.
    planter = None
    if "--planter" in args:
        i = args.index("--planter")
        planter = args[i + 1] if i + 1 < len(args) else "rappel"
    if planter == "demarrage":
        raise RuntimeError("panne d'essai au démarrage (--planter demarrage)")
    app = Hub(demo=demo)
    _APPLI = app
    if planter == "rappel":
        def panne_de_rappel():
            # On se met dans l'état où était le joueur de Tetardtek : il
            # venait de cliquer « Lancer le jeu ».
            app.geste_en_cours = "Lancer le jeu"
            raise RuntimeError("panne d'essai dans un rappel (--planter "
                               "rappel)")
        app.after(1200, panne_de_rappel)
    elif planter == "fil":
        app.after(1200, lambda: app._fil(_panne_de_fil))
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
