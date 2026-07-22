# -*- coding: utf-8 -*-
"""
Ascension FR — Compagnon, interface v2
======================================
La nouvelle habillage « médiéval » du Compagnon, reproduction de la maquette
Claude Design (`Design/compagnon/design-brief-and-assets/project/Compagnon
Ascension FR v2.dc.html`). Ce fichier ne contient QUE l'interface :

  - toute la logique (versions, téléchargement, rapport, caches) est importée
    de `compagnon.py`, qui reste inchangé et continue de fonctionner seul ;
  - les décors (pierre, or, parchemin, bois, boutons) sont des PNG rendus par
    `fabriquer_decor_v2.py` depuis le CSS exact de la maquette — ils vivent
    dans `assets/v2ui/` et sont embarqués dans l'exe comme le reste ;
  - les textes qui changent (états, chemins, compteurs) sont dessinés par le
    canvas avec les polices de la maquette (Cinzel, Alegreya Sans), chargées
    en privé — rien n'est installé sur la machine du joueur.

Version 2.1 — six attentions de plus, sans toucher à `compagnon.py` :
fenêtre remise devant à la fermeture du jeu (psutil, jamais d'envoi
automatique), case « Démarrer réduit », compteur de contribution, résumé du
patch-note dans le bloc Traduction, détection du dossier du jeu proposée (et
jamais enregistrée sans un clic), panneau de diagnostic « Tout va bien ? ».
Les décors ajoutés viennent de `fabriquer_decor_v21.py`.

Point d'entrée : `compagnon_v2.py`.
"""
import ctypes
import json
import os
import re
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import urllib.request
import webbrowser

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageTk

import compagnon as logique

try:
    import psutil                # embarqué dans l'exe (spec v2) ; sans lui,
except ImportError:              # l'appli marche, sans la détection du jeu.
    psutil = None

# --------------------------------------------------------------------------- #
# Plan de la fenêtre — la seule source des cotes, partagée avec le générateur
# de décors (`fabriquer_decor_v2.py` importe ce dictionnaire).
# --------------------------------------------------------------------------- #
METRIQUE = {
    "W": 568, "H": 958,          # fenêtre entière (liseré doré compris)
    "TRIM": 6,                   # liseré doré autour de la pierre
    "CX": 26, "CW": 516,         # colonne de contenu (x gauche, largeur)
    # En-tête : écusson rond + plaque du titre
    "Y_CRETE": 30, "CRETE": 56,
    "Y_PLAQUE": 56, "PLAQUE_W": 420, "PLAQUE_H": 96,
    # Blocs (y, hauteur)
    "Y_B1": 164, "H_B1": 62,     # dossier du jeu
    "Y_B2": 238, "H_B2": 228,    # traduction (dominant)
    "Y_B3": 478, "H_B3": 298,    # contribuer (parchemin)
    "Y_B4": 788, "H_B4": 78,     # soutenir (bois)
    "Y_ETAT": 876, "H_ETAT": 36, # barre d'état
    "Y_PIED": 920,               # pied de page
    # Bloc 2 — géométrie interne (relative au haut du bloc)
    "B2_X": 50, "B2_W": 468,     # colonne interne
    "B2_TITRE": 38,              # y du grand titre
    "B2_SOUS": 78,               # y du sous-titre
    "B2_ACTION": 126,            # y du bouton / de la barre de progression
    "B2_LIEN": 202,              # y (centre) du lien de mise à jour de l'appli
    # Bloc 3 — géométrie interne
    "B3_X": 48, "B3_W": 472,
    "B3_MSG": 150, "B3_ENVOI": 176, "B3_LIGNE": 236,
    # Largeurs fixes des boutons (cuites dans les PNG)
    "BTN_PRINCIPAL_W": 468, "BTN_PRINCIPAL_H": 52,
    "BTN_ENVOYER_W": 472, "BTN_ENVOYER_H": 44,
    "BTN_COPIER_W": 372, "BTN_DISCORD_W": 90, "BTN_LIGNE_H": 40,
    "BTN_CHANGER_W": 94, "BTN_CHANGER_H": 38,
    "BTN_CAFE_W": 140, "BTN_CAFE_H": 36,
    "BARRE_W": 468, "BARRE_H": 22,
}

DECOR_DOSSIER = "v2ui"           # sous assets/
MANIFESTE = "decor_v2.json"

# --------------------------------------------------------------------------- #
# Les états de la maquette — libellés, couleurs, tonalités : copie fidèle du
# `transConfig()` / `contribConfig()` / `tones()` du fichier .dc.html.
# --------------------------------------------------------------------------- #
TONALITES = {
    "neutre": {"texte": "#c2c8d2"},
    "alerte": {"texte": "#e8cf92"},
    "erreur": {"texte": "#f0b39c"},
    "succes": {"texte": "#a9e29a"},
}

ETATS_TRAD = {
    "verification": {
        "titre": "Vérification…", "couleur": "#8a6a2a",
        "sous": "Recherche de la dernière version…",
        "badge": False, "bouton": None, "ton": "neutre",
        "statut": "Vérification des mises à jour…"},
    "introuvable": {
        "titre": "Dossier introuvable", "couleur": "#b8781f",
        "sous": "Choisis d'abord le dossier du jeu ci-dessus pour lancer la "
                "traduction.",
        "badge": False, "bouton": None, "ton": "alerte",
        "statut": "Sélectionne le dossier de World of Warcraft pour "
                  "continuer."},
    "absente": {
        "titre": "Traduction non installée", "couleur": "#8a6a2a",
        "sous": "Dernière version disponible : {vd}",
        "badge": False, "bouton": "installer", "ton": "neutre",
        "statut": "Prêt à installer la version {vd}."},
    "ajour": {
        "titre": "Tu es à jour", "couleur": "#2f8f2a",
        "sous": "Version {vi} installée{textes}",
        "badge": True, "bouton": "fait", "ton": "succes",
        "statut": "Tout est à jour. Bon jeu !"},
    "maj": {
        "titre": "Mise à jour disponible", "couleur": "#a9781f",
        "sous": "Installée : {vi}   →   Disponible : {vd}",
        "badge": False, "bouton": "maj", "ton": "neutre",
        "statut": "Une nouvelle version de la traduction t'attend."},
    "injoignable": {
        "titre": "Serveur injoignable", "couleur": "#b23b1f",
        "sous": "{version_locale} impossible de joindre GitHub",
        "badge": False, "bouton": "reessayer", "ton": "erreur",
        "statut": "Impossible de vérifier les mises à jour. Vérifie ta "
                  "connexion."},
    "telechargement": {
        "titre": "Installation en cours…", "couleur": "#8a6a2a",
        "sous": "Téléchargement de la version {vd}",
        "badge": False, "bouton": None, "ton": "neutre",
        "statut": "Téléchargement… ne ferme pas la fenêtre.",
        "progression": True},
    "protege": {
        "titre": "Dossier protégé", "couleur": "#b8781f",
        "sous": "Windows empêche l'écriture ici. Relance l'application en "
                "administrateur pour installer la traduction.",
        "badge": False, "bouton": "admin", "ton": "alerte",
        "statut": "Droits administrateur requis pour ce dossier."},
    "reussie": {
        "titre": "Installation réussie", "couleur": "#2f8f2a",
        "sous": "En jeu : tape /reload, ou reconnecte-toi.",
        "badge": True, "bouton": None, "ton": "succes",
        "statut": "Traduction installée. Amuse-toi bien !"},
}

ETATS_CONTRIB = {
    "attente":   {"couleur": "#7a5a1a", "bouton": "envoyer"},
    "rien":      {"couleur": "#5a4020", "bouton": "envoyer"},
    "envoi":     {"couleur": "#5a4020", "bouton": "envoi"},
    "reussi":    {"couleur": "#2f7f2a", "bouton": "envoyer_gris"},
    "horsligne": {"couleur": "#b23b1f", "bouton": "envoyer_gris"},
    "vide":      {"couleur": "#2f7f2a", "bouton": "envoyer_gris"},
}

# Drapeaux acceptés en 3e position et suivantes de --demo (captures d'écran).
DRAPEAUX_DEMO = frozenset({"jeuferme", "diag", "note", "propose", "compteur",
                           "reduit"})

# Boutons possibles du bloc Traduction : nom d'image et action à déclencher.
BOUTONS_PRINCIPAUX = {
    "installer": "btn_installer",
    "maj": "btn_maj",
    "reessayer": "btn_reessayer",
    "admin": "btn_admin",
    "fait": "btn_fait",
}


# --------------------------------------------------------------------------- #
# Améliorations v2.1 — aides sans interface
# --------------------------------------------------------------------------- #
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


def detecter_jeu():
    """Amélioration 5 : cherche le dossier du jeu quand rien n'est enregistré
    (registre du launcher, ProgramData, puis les emplacements habituels que
    `compagnon.py` connaît déjà). Rend un chemin VALIDE ou None. L'appelant le
    PROPOSE seulement — l'enregistrement attend toujours le clic du joueur."""
    bases = []
    try:
        bases += _candidats_registre()
    except Exception:
        pass
    programdata = os.environ.get("PROGRAMDATA")
    if programdata and os.path.isdir(programdata):
        try:
            for dossier in os.listdir(programdata):
                if "ascension" in dossier.lower():
                    bases.append(os.path.join(programdata, dossier))
        except OSError:
            pass
    for base in bases:
        for fin in (("resources", "ascension-live"), ("resources", "client"),
                    ("ascension-live",), ("client",), ()):
            essai = os.path.join(base, *fin)
            if logique.jeu_valide(essai):
                return os.path.normpath(essai)
    return logique.chercher_jeu()


def raccourcir(chemin, garder=52):
    """Queue d'un chemin trop long pour le bloc « Dossier du jeu »."""
    if len(chemin) <= garder:
        return chemin
    return "…" + chemin[-(garder - 1):]


def resumer_patchnote(corps, max_lignes=3):
    """Amélioration 4 : résume le corps d'une release GitHub en 2-3 lignes
    propres — sans dièses, étoiles, liens ni lignes décoratives du markdown,
    chaque ligne raccourcie net."""
    lignes = []
    for brute in (corps or "").splitlines():
        t = brute.strip()
        if not t or set(t) <= set("-=*_#"):
            continue
        t = re.sub(r"^#+\s*", "", t)
        t = re.sub(r"^(?:[-*+]|\d+[.)])\s+", "• ", t)
        t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
        t = t.replace("**", "").replace("__", "").replace("`", "")
        # Une ligne-titre « Version 1.8.0 » n'apprend rien : la version est
        # déjà affichée juste au-dessus dans le bloc Traduction.
        if re.match(r"(?i)^(?:version\s*)?v?\d+(?:\.\d+)+\s*$", t):
            continue
        if len(t) > 76:
            t = t[:73].rstrip() + "…"
        lignes.append(t)
        if len(lignes) >= max_lignes:
            break
    return "\n".join(lignes)


# --------------------------------------------------------------------------- #
# Préparation Windows : rendu net (DPI) et polices privées de la maquette
# --------------------------------------------------------------------------- #
def preparer_dpi():
    """Rendu 1:1 : sans cela, Windows étire la fenêtre et floute les décors."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


POLICES = ("Cinzel-VariableFont_wght.ttf", "AlegreyaSans-Regular.ttf",
           "AlegreyaSans-Medium.ttf", "AlegreyaSans-Bold.ttf",
           "AlegreyaSans-ExtraBold.ttf")
FR_PRIVATE = 0x10


def charger_polices():
    """Charge Cinzel et Alegreya Sans pour CETTE application seulement
    (FR_PRIVATE : rien n'est installé, rien ne survit à la fermeture)."""
    for nom in POLICES:
        chemin = logique.ressource(os.path.join("v2", "fonts", nom))
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
# Décors : chargement des PNG et de leur manifeste de cotes
# --------------------------------------------------------------------------- #
class Decor:
    """Les images générées par `fabriquer_decor_v2.py`, avec pour chacune la
    marge transparente (pad) qui entoure l'élément pour garder ses ombres."""

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
    """Un bouton dessiné sur le canvas : image au repos, image de survol,
    enfoncement de 2 px au clic, état désactivé (image grise, sans action)."""

    def __init__(self, app, nom, x, y, commande=None):
        self.app, self.canvas, self.decor = app, app.canvas, app.decor
        self.x, self.y = x, y
        self.commande = commande
        self.nom = None
        self.actif = True
        self.survole = False
        self.enfonce = False
        self.item = self.canvas.create_image(0, 0, anchor="nw")
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
# La fenêtre
# --------------------------------------------------------------------------- #
class CompagnonV2(tk.Tk):
    def __init__(self, demo=None):
        preparer_dpi()
        charger_polices()
        super().__init__()
        self.demo = demo
        self.title("Compagnon Ascension FR")
        self.resizable(False, False)
        self.geometry("%dx%d" % (METRIQUE["W"], METRIQUE["H"]))
        try:
            self.iconbitmap(logique.ressource("logo.ico"))
        except Exception:
            pass

        self.decor = Decor()
        self.cfg = logique.charger_config()
        self.jeu = self.cfg.get("jeu")
        self.jeu_propose = None
        if not logique.jeu_valide(self.jeu):
            # Jamais d'écriture silencieuse : le dossier détecté n'est que
            # PROPOSÉ dans le bloc du haut, le joueur le confirme d'un clic.
            self.jeu = None
            if not demo:
                self.jeu_propose = detecter_jeu()
        self.reduit = bool(self.cfg.get("demarrer_reduit"))
        self.corps_note = None
        self.diag_ouvert = False
        self.derniere = None
        self.url_zip = None
        self.url_exe = None
        self.etat_trad = "verification"
        self.etat_contrib = None
        self.textes_actifs = None
        self.attente = 0
        self.pct = 0
        self.octets = 0.0
        self._decal_barre = 0
        self._toc_barre = None
        self._toc_glow = None
        self._glow_pas = 0
        self._titres = {}

        self._polices()
        self._construire()
        self._rafraichir_jeu()

        if demo:
            self.after(80, self._appliquer_demo)
        else:
            self.after(300, self.verifier_version)
            self.after(600, self.rafraichir_stats)
            if self.reduit:
                # « Démarrer réduit » : la vérification tourne quand même ;
                # la fenêtre ne ressort que s'il y a du nouveau (voir
                # _montrer_version).
                self.iconify()
            self._demarrer_surveillance()
        # Compteur rafraîchi quand la fenêtre revient devant (au plus 1/10 s).
        self.dernier_coup_oeil = 0
        self.bind("<FocusIn>", self._au_retour)

    # --- polices ----------------------------------------------------------- #
    def _polices(self):
        alegreya = police_dispo("Alegreya Sans", "Segoe UI")
        mono = police_dispo("Cascadia Mono", "Consolas")
        # tailles NÉGATIVES = pixels (fidèles aux px de la maquette)
        self.p_mono = tkfont.Font(family=mono, size=-13)
        self.p_reseau = tkfont.Font(family=alegreya, size=-12)
        # Les textes variables sont rendus par PIL (FreeType) et non par le
        # canvas : GDI écrase la chasse des espaces d'Alegreya Sans aux
        # petites tailles (« Toutestàjour » — vu sur la première capture).
        self.f_regulier = logique.ressource(
            os.path.join("v2", "fonts", "AlegreyaSans-Regular.ttf"))
        self.f_gras = logique.ressource(
            os.path.join("v2", "fonts", "AlegreyaSans-Bold.ttf"))
        self._fontes = {}
        self._photos_textes = {}

    def _fonte(self, chemin, taille):
        cle = (chemin, taille)
        if cle not in self._fontes:
            self._fontes[cle] = ImageFont.truetype(chemin, taille)
        return self._fontes[cle]

    def _texte_pil(self, texte, taille, couleur, gras=False, largeur=None,
                   interligne=1.35, souligne=False):
        """Rend un paragraphe en image transparente (avec repli de ligne).

        Le dessin se fait MOT PAR MOT : les fichiers Alegreya Sans embarqués
        ont une espace de 0,14 em (défaut du .ttf, vérifié à la main) que les
        navigateurs corrigent mais pas FreeType — sans cette normalisation,
        « Tout est à jour » s'affichait « Toutestàjour »."""
        fonte = self._fonte(self.f_gras if gras else self.f_regulier, taille)
        espace = max(fonte.getlength(" "), round(taille * 0.26))

        def chasse(mots):
            return (sum(fonte.getlength(m) for m in mots)
                    + espace * max(0, len(mots) - 1))

        lignes = []
        for brut in texte.split("\n"):
            mots = brut.split(" ")
            if not largeur:
                lignes.append(mots)
                continue
            courante = []
            for mot in mots:
                if courante and chasse(courante + [mot]) > largeur:
                    lignes.append(courante)
                    courante = [mot]
                else:
                    courante.append(mot)
            lignes.append(courante)
        pas = round(taille * interligne)
        l = max(4, round(max(chasse(m) for m in lignes))) + 4
        h = pas * len(lignes) + 4
        image = Image.new("RGBA", (l, h), (0, 0, 0, 0))
        dessin = ImageDraw.Draw(image)
        for rang, mots in enumerate(lignes):
            x = 2.0
            for mot in mots:
                dessin.text((x, 2 + rang * pas), mot, font=fonte,
                            fill=couleur)
                x += fonte.getlength(mot) + espace
            if souligne and mots:
                base = 2 + rang * pas + taille + 2
                dessin.line((2, base, 2 + chasse(mots), base), fill=couleur)
        return ImageTk.PhotoImage(image)

    def _poser_texte(self, item, texte, taille, couleur, **kw):
        """Pose (ou remplace) le rendu PIL d'un texte sur un item du canvas."""
        photo = self._texte_pil(texte, taille, couleur, **kw)
        self._photos_textes[item] = photo    # garde la référence (tkinter !)
        self.canvas.itemconfigure(item, image=photo)

    def _titre_pil(self, texte, couleur):
        """Le grand titre d'état, rendu par PIL avec Cinzel graisse 900 et les
        deux ombres de la maquette (rehaut clair dessus, ombre chaude floue)."""
        cle = (texte, couleur)
        if cle in self._titres:
            return self._titres[cle]
        chemin = logique.ressource(os.path.join("v2", "fonts",
                                                "Cinzel-VariableFont_wght.ttf"))
        police = ImageFont.truetype(chemin, 30)
        try:
            police.set_variation_by_axes([900])
        except Exception:
            pass
        essai = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
        boite = essai.textbbox((0, 0), texte, font=police)
        l, h = boite[2] - boite[0] + 8, boite[3] - boite[1] + 10
        origine = (4 - boite[0], 4 - boite[1])
        image = Image.new("RGBA", (l, h), (0, 0, 0, 0))
        # ombre chaude floutée (0 2px 3px rgba(90,60,15,.3))
        ombre = Image.new("RGBA", (l, h), (0, 0, 0, 0))
        ImageDraw.Draw(ombre).text((origine[0], origine[1] + 2), texte,
                                   font=police, fill=(90, 60, 15, 95))
        image = Image.alpha_composite(image,
                                      ombre.filter(ImageFilter.GaussianBlur(1.4)))
        dessin = ImageDraw.Draw(image)
        # rehaut clair (0 1px 0 rgba(255,255,255,.45))
        dessin.text((origine[0], origine[1] + 1), texte, font=police,
                    fill=(255, 255, 255, 115))
        dessin.text(origine, texte, font=police, fill=couleur)
        photo = ImageTk.PhotoImage(image)
        self._titres[cle] = photo
        return photo

    # --- construction ------------------------------------------------------ #
    def _construire(self):
        M = METRIQUE
        self.canvas = tk.Canvas(self, width=M["W"], height=M["H"], bd=0,
                                highlightthickness=0, bg="#14161b")
        self.canvas.pack()
        d, c = self.decor, self.canvas

        d.poser(c, "fond", 0, 0)
        d.poser(c, "pan_dossier", M["CX"], M["Y_B1"])
        d.poser(c, "pan_or", M["CX"], M["Y_B2"])
        d.poser(c, "pan_parchemin", M["CX"], M["Y_B3"])
        d.poser(c, "pan_bois", M["CX"], M["Y_B4"])
        d.poser(c, "plaque", (M["W"] - M["PLAQUE_W"]) // 2, M["Y_PLAQUE"])
        d.poser(c, "crete", (M["W"] - M["CRETE"]) // 2, M["Y_CRETE"])

        # -- Bloc 1 : dossier du jeu
        self.txt_jeu = c.create_text(
            M["CX"] + 15, M["Y_B1"] + 40, anchor="w", font=self.p_mono,
            fill="#b4bac4", text="…", width=M["CW"] - 140)
        BoutonImage(self, "btn_changer", M["CX"] + M["CW"] - 15
                    - M["BTN_CHANGER_W"], M["Y_B1"] + 12, self.choisir_jeu)
        # « Utiliser » : confirmation du dossier détecté (amélioration 5) —
        # visible seulement quand un dossier est proposé.
        self.btn_utiliser = BoutonImage(
            self, "btn_utiliser", M["CX"] + M["CW"] - 25
            - 2 * M["BTN_CHANGER_W"], M["Y_B1"] + 12, self.adopter_propose)
        self.btn_utiliser.cacher()

        # -- Bloc 2 : traduction
        x2 = M["CX"] + M["B2_X"] - 26
        self.img_titre = c.create_image(x2, M["Y_B2"] + M["B2_TITRE"],
                                        anchor="nw")
        self.txt_sous = c.create_image(x2, M["Y_B2"] + M["B2_SOUS"],
                                       anchor="nw")
        self.img_badge = d.poser(c, "badge", M["CX"] + M["CW"] - 84,
                                 M["Y_B2"] + 30, state="hidden")
        self.btn_principal = BoutonImage(self, "btn_fait", x2,
                                         M["Y_B2"] + M["B2_ACTION"],
                                         self.action_maj)
        self.btn_principal.cacher()
        # barre de progression (creux + remplissage animé)
        self.it_creux = d.poser(c, "barre_creuse", x2,
                                M["Y_B2"] + M["B2_ACTION"] + 8,
                                state="hidden")
        self.it_barre = c.create_image(x2 + 1, M["Y_B2"] + M["B2_ACTION"] + 9,
                                       anchor="nw", state="hidden")
        self.txt_pct = c.create_image(x2 + M["B2_W"],
                                      M["Y_B2"] + M["B2_ACTION"] + 36,
                                      anchor="ne", state="hidden")
        self._photo_barre = None
        self.txt_lien = c.create_image(M["W"] // 2, M["Y_B2"] + M["B2_LIEN"],
                                       anchor="center", state="hidden")
        c.tag_bind(self.txt_lien, "<Button-1>", lambda _: self.maj_compagnon())
        self._curseur_main(self.txt_lien)
        # Résumé du patch-note de la release (amélioration 4) — position et
        # ancre posées par _montrer_note selon l'état du bloc.
        self.txt_note = c.create_image(0, 0, anchor="nw", state="hidden")

        # -- Bloc 3 : contribuer
        x3 = M["CX"] + M["B3_X"] - 26
        self.txt_msg = c.create_image(x3, M["Y_B3"] + M["B3_MSG"],
                                      anchor="nw")
        self.btn_envoyer = BoutonImage(self, "btn_envoyer", x3,
                                       M["Y_B3"] + M["B3_ENVOI"],
                                       self.envoyer_rapport)
        if not logique.WEBHOOK_RAPPORTS:
            self.btn_envoyer.cacher()
        BoutonImage(self, "btn_copier", x3, M["Y_B3"] + M["B3_LIGNE"],
                    self.copier_rapport)
        BoutonImage(self, "btn_discord",
                    x3 + M["B3_W"] - M["BTN_DISCORD_W"],
                    M["Y_B3"] + M["B3_LIGNE"],
                    lambda: webbrowser.open(logique.DISCORD))
        # Compteur de contribution (amélioration 3), au bas du parchemin.
        self.txt_compteur = c.create_image(M["W"] // 2, M["Y_B3"] + 285,
                                           anchor="center", state="hidden")
        self._maj_compteur()
        # Bandeau « le jeu vient de se fermer » (amélioration 1) : posé sur la
        # couture entre les blocs, cliquer le range.
        self.it_bandeau = d.poser(c, "bandeau_jeu", M["CX"], M["Y_B3"] - 26,
                                  state="hidden")
        c.tag_bind(self.it_bandeau, "<Button-1>",
                   lambda _: c.itemconfigure(self.it_bandeau, state="hidden"))
        self._curseur_main(self.it_bandeau)

        # -- Bloc 4 : soutenir
        BoutonImage(self, "btn_cafe",
                    M["CX"] + M["CW"] - 78 - M["BTN_CAFE_W"],
                    M["Y_B4"] + 21, lambda: webbrowser.open(logique.SOUTIEN))
        lx = M["CX"] + M["CW"] - 42
        t_twitch = c.create_text(lx, M["Y_B4"] + 30, anchor="center",
                                 font=self.p_reseau, fill="#a98cff",
                                 text="Twitch")
        t_youtube = c.create_text(lx, M["Y_B4"] + 50, anchor="center",
                                  font=self.p_reseau, fill="#e07070",
                                  text="YouTube")
        c.tag_bind(t_twitch, "<Button-1>",
                   lambda _: webbrowser.open(logique.TWITCH))
        c.tag_bind(t_youtube, "<Button-1>",
                   lambda _: webbrowser.open(logique.YOUTUBE))
        self._curseur_main(t_twitch)
        self._curseur_main(t_youtube)

        # -- Voix françaises (2.1) : téléchargées depuis le dépôt SÉPARÉ,
        # posées en fichiers libres (le client les lit ; le launcher ne
        # nettoie que Data\). Lien discret sous Twitch/YouTube.
        self._voix_en_cours = False
        voix_deja = logique.jeu_valide(self.jeu) and os.path.exists(
            os.path.join(self.jeu, logique.TEMOIN_VOIX))
        # UN VRAI BOUTON doré (demande de Dan), juste sous le grand bouton
        # de mise à jour — même style, plus fin (btn_voix* du fabricant de
        # décor). Trois états : installer / téléchargement / installées.
        self.btn_voix = BoutonImage(
            self, "btn_voix_fait" if voix_deja else "btn_voix",
            M["CX"] + (M["CW"] - M["BTN_PRINCIPAL_W"]) // 2,
            M["Y_B2"] + M["B2_ACTION"] + M["BTN_PRINCIPAL_H"] + 8,
            self._lancer_voix)
        if voix_deja:
            self.btn_voix.configurer("btn_voix_fait", actif=False)

        # -- Barre d'état
        self.it_ton = d.poser(c, "etat_neutre", M["CX"], M["Y_ETAT"])
        self.txt_statut = c.create_image(M["CX"] + 33, M["Y_ETAT"]
                                         + M["H_ETAT"] // 2, anchor="w")

        # -- Pied de page
        p = d.manifeste.get("pied", {})
        it_pied = d.poser(c, "pied", (M["W"] - p.get("w", 160)) // 2,
                          M["Y_PIED"])
        c.tag_bind(it_pied, "<Button-1>", lambda _: webbrowser.open(
            "https://github.com/" + logique.DEPOT))
        self._curseur_main(it_pied)

        # -- Case « Démarrer réduit » (amélioration 2), à gauche du pied
        self.it_case = d.poser(c, "case_coche" if self.reduit else "case",
                               M["CX"] + 8, M["Y_PIED"] + 4)
        self.txt_case = c.create_image(M["CX"] + 34, M["Y_PIED"] + 13,
                                       anchor="w")
        self._poser_texte(self.txt_case, "Démarrer réduit", 13, "#8a919c")
        for it in (self.it_case, self.txt_case):
            c.tag_bind(it, "<Button-1>", lambda _: self._basculer_reduit())
            self._curseur_main(it)

        # -- Lien « Tout va bien ? » (amélioration 6), à droite du pied
        self.txt_diag = c.create_image(M["W"] - M["CX"] - 8, M["Y_PIED"] + 13,
                                       anchor="e")
        self._poser_texte(self.txt_diag, "Tout va bien ?", 13, "#8a919c",
                          souligne=True)
        c.tag_bind(self.txt_diag, "<Button-1>", lambda _: self.basculer_diag())
        self._curseur_main(self.txt_diag)

        # -- Panneau du diagnostic, créé en DERNIER : il passe devant tout
        dx = (M["W"] - self.decor.manifeste["pan_diag"]["w"]) // 2
        dy = 452
        self.it_diag_fond = d.poser(c, "pan_diag", dx, dy, state="hidden")
        c.tag_bind(self.it_diag_fond, "<Button-1>",
                   lambda _: self.basculer_diag())
        self.diag_lignes = []
        for rang in range(3):
            ico = c.create_image(dx + 20, dy + 54 + rang * 46, anchor="nw",
                                 state="hidden")
            txt = c.create_image(dx + 52, dy + 53 + rang * 46, anchor="nw",
                                 state="hidden")
            self.diag_lignes.append((ico, txt))

        self._appliquer_trad("verification")
        self._appliquer_contrib("rien", "Lecture de ta sauvegarde…")

    def _curseur_main(self, item):
        self.canvas.tag_bind(item, "<Enter>",
                             lambda _: self.canvas.configure(cursor="hand2"),
                             add="+")
        self.canvas.tag_bind(item, "<Leave>",
                             lambda _: self.canvas.configure(cursor=""),
                             add="+")

    # --- application des états --------------------------------------------- #
    def _valeurs(self):
        textes = ""
        if self.textes_actifs:
            textes = " · %s textes actifs" % format(
                self.textes_actifs, ",").replace(",", " ")
        vi = (logique.jeu_valide(self.jeu)
              and logique.version_installee(self.jeu)) or "?"
        version_locale = ("Version %s installée ·" % vi) if vi != "?" else ""
        return {"vi": vi, "vd": self.derniere or "?", "textes": textes,
                "version_locale": version_locale}

    def _appliquer_trad(self, etat):
        self.etat_trad = etat
        e = ETATS_TRAD[etat]
        v = self._valeurs()
        c = self.canvas
        c.itemconfigure(self.img_titre,
                        image=self._titre_pil(e["titre"], e["couleur"]))
        self._poser_texte(self.txt_sous, e["sous"].format(**v), 16, "#4a3313",
                          largeur=(METRIQUE["B2_W"] - 88) if e["badge"]
                          else (METRIQUE["B2_W"] - 4))
        c.itemconfigure(self.img_badge,
                        state="normal" if e["badge"] else "hidden")
        if e.get("progression"):
            self.btn_principal.cacher()
            for it in (self.it_creux, self.it_barre, self.txt_pct):
                c.itemconfigure(it, state="normal")
            self._animer_barre()
        else:
            for it in (self.it_creux, self.it_barre, self.txt_pct):
                c.itemconfigure(it, state="hidden")
            if self._toc_barre:
                self.after_cancel(self._toc_barre)
                self._toc_barre = None
            if e["bouton"]:
                self.btn_principal.montrer()
                self.btn_principal.configurer(
                    BOUTONS_PRINCIPAUX[e["bouton"]],
                    self._relancer_admin if e["bouton"] == "admin"
                    else self.action_maj,
                    actif=(e["bouton"] != "fait"))
            else:
                self.btn_principal.cacher()
        if etat == "maj":
            self._animer_glow()
        elif self._toc_glow:
            self.after_cancel(self._toc_glow)
            self._toc_glow = None
        self.statut(e["statut"].format(**v), e["ton"])
        self._montrer_note()

    def _appliquer_contrib(self, etat, message):
        self.etat_contrib = etat
        e = ETATS_CONTRIB[etat]
        self._poser_texte(self.txt_msg, message, 14, e["couleur"], gras=True,
                          largeur=METRIQUE["B3_W"])
        if logique.WEBHOOK_RAPPORTS:
            self.btn_envoyer.configurer("btn_" + e["bouton"],
                                        actif=(e["bouton"] == "envoyer"))

    def statut(self, texte, ton="neutre"):
        self.canvas.itemconfigure(self.it_ton,
                                  image=self.decor.photo("etat_" + ton))
        couleur = TONALITES[ton]["texte"]
        photo = self._texte_pil(texte, 14, couleur,
                                largeur=METRIQUE["CW"] - 50, interligne=1.15)
        if photo.height() > METRIQUE["H_ETAT"] - 4:   # long : on resserre
            photo = self._texte_pil(texte, 12, couleur,
                                    largeur=METRIQUE["CW"] - 50,
                                    interligne=1.15)
        self._photos_textes[self.txt_statut] = photo
        self.canvas.itemconfigure(self.txt_statut, image=photo)

    # --- animations -------------------------------------------------------- #
    def _animer_barre(self):
        """Fait défiler les rayures dorées de la barre de progression."""
        M = METRIQUE
        largeur = max(0, min(M["BARRE_W"] - 2,
                             int((M["BARRE_W"] - 2) * self.pct / 100.0)))
        if largeur > 6:
            bande = self.decor.pil("barre_bande")
            self._decal_barre = (self._decal_barre + 3) % 32
            zone = bande.crop((32 - self._decal_barre, 0,
                               32 - self._decal_barre + largeur,
                               bande.size[1]))
            masque = Image.new("L", zone.size, 0)
            ImageDraw.Draw(masque).rounded_rectangle(
                (0, 0, zone.size[0] - 1, zone.size[1] - 1), 10, fill=255)
            zone.putalpha(masque)
            self._photo_barre = ImageTk.PhotoImage(zone)
            self.canvas.itemconfigure(self.it_barre, image=self._photo_barre)
        if self.pct > 0:
            self._poser_texte(self.txt_pct, "%d %%" % self.pct, 13,
                              "#6b4c1c", gras=True)
        elif self.octets:
            self._poser_texte(self.txt_pct, "%.1f Mo" % self.octets, 13,
                              "#6b4c1c", gras=True)
        self._toc_barre = self.after(90, self._animer_barre)

    def _animer_glow(self):
        """Pouls lumineux du bouton « Mettre à jour » (3 images d'intensité)."""
        if self.etat_trad != "maj":
            self._toc_glow = None
            return
        cadence = (1, 2, 3, 2)
        self._glow_pas = (self._glow_pas + 1) % len(cadence)
        nom = "btn_maj" if self.btn_principal.survole else \
            "btn_maj_glow%d" % cadence[self._glow_pas]
        if not self.btn_principal.survole and self.decor.existe(nom):
            self.canvas.itemconfigure(self.btn_principal.item,
                                      image=self.decor.photo(nom))
        self._toc_glow = self.after(240, self._animer_glow)

    # --- dossier du jeu ---------------------------------------------------- #
    def _rafraichir_jeu(self):
        if logique.jeu_valide(self.jeu):
            self.canvas.itemconfigure(self.txt_jeu, text=self.jeu,
                                      width=METRIQUE["CW"] - 140)
            self.btn_utiliser.cacher()
            self.cfg["jeu"] = self.jeu
            if not self.demo:
                logique.sauver_config(self.cfg)
        elif self.jeu_propose:
            # Dossier détecté : simplement PROPOSÉ (amélioration 5), le clic
            # sur « Utiliser » l'enregistre — jamais d'écriture silencieuse.
            # Une seule ligne courte : la place est comptée entre l'étiquette
            # du bloc et les deux boutons.
            self.canvas.itemconfigure(
                self.txt_jeu, text=raccourcir(self.jeu_propose, 34),
                width=METRIQUE["CW"] - 240)
            self.btn_utiliser.montrer()
        else:
            self.canvas.itemconfigure(
                self.txt_jeu, text="— aucun dossier sélectionné —",
                width=METRIQUE["CW"] - 140)
            self.btn_utiliser.cacher()

    def adopter_propose(self):
        """Le joueur confirme le dossier détecté : c'est SON clic qui écrit."""
        if not self.jeu_propose:
            return
        self.jeu, self.jeu_propose = self.jeu_propose, None
        self._rafraichir_jeu()
        self.statut("Dossier du jeu enregistré.", "succes")
        if not self.demo:
            self.verifier_version()
            self.rafraichir_stats()

    def choisir_jeu(self):
        from tkinter import filedialog
        choix = filedialog.askdirectory(
            title="Dossier du jeu Ascension (contient « Interface »)")
        if not choix:
            return
        choix = os.path.normpath(choix)
        for essai in (choix,
                      os.path.join(choix, "resources", "ascension-live"),
                      os.path.join(choix, "resources", "client"),
                      os.path.join(choix, "ascension-live"),
                      os.path.join(choix, "client")):
            if logique.jeu_valide(essai):
                self.jeu = essai
                self._rafraichir_jeu()
                self.verifier_version()
                self.rafraichir_stats()
                return
        self.statut("Ce dossier ne contient pas « Interface ».", "alerte")

    # --- statistiques / rapport en attente --------------------------------- #
    def _au_retour(self, _e=None):
        maintenant = time.time()
        if maintenant - self.dernier_coup_oeil < 10:
            return
        self.dernier_coup_oeil = maintenant
        if not self.demo:
            self.rafraichir_stats()

    def rafraichir_stats(self):
        if not logique.jeu_valide(self.jeu):
            self._appliquer_contrib(
                "rien", "Choisis d'abord le dossier du jeu ci-dessus.")
            return

        def travail():
            try:
                total, attente = logique.lire_stats(self.jeu)
            except Exception:
                total, attente = None, 0
            self.after(0, lambda: self._montrer_stats(total, attente))
        threading.Thread(target=travail, daemon=True).start()

    def _montrer_stats(self, total, attente):
        if total:
            self.textes_actifs = total
            if self.etat_trad == "ajour":
                self._appliquer_trad("ajour")   # complète le sous-titre
        self.attente = attente
        if self.etat_contrib in ("envoi", "reussi", "horsligne", "vide"):
            return                              # ne pas écraser un état en cours
        dernier = self.cfg.get("dernier_envoi")
        queue = (" · dernier envoi : %s" % dernier) if dernier else ""
        if attente > 0:
            self._appliquer_contrib(
                "attente", "%d entrée(s) prête(s) à partir%s"
                % (attente, queue))
        else:
            self._appliquer_contrib(
                "rien", "Rien de nouveau à signaler%s" % queue)

    # --- vérification / mise à jour de la traduction ------------------------ #
    def verifier_version(self):
        self._appliquer_trad("verification")

        def travail():
            try:
                derniere, url, url_exe = logique.derniere_release()
            except Exception:
                derniere, url, url_exe = None, None, None
            self.after(0, lambda: self._montrer_version(derniere, url,
                                                        url_exe))
        threading.Thread(target=travail, daemon=True).start()

    def _montrer_version(self, derniere, url, url_exe):
        self.derniere, self.url_zip = derniere, url
        self.url_exe = url_exe
        lien = bool(derniere and logique.en_tuple(derniere)
                    > logique.en_tuple(logique.VERSION_COMPAGNON))
        if lien:
            self.canvas.itemconfigure(self.txt_lien, state="normal")
            self._poser_texte(
                self.txt_lien,
                "Une nouvelle version de l'application (%s) est "
                "disponible ›" % derniere, 13, "#7d5518", souligne=True)
        else:
            self.canvas.itemconfigure(self.txt_lien, state="hidden")
        if not logique.jeu_valide(self.jeu):
            self._appliquer_trad("introuvable")
            if self.jeu_propose:
                self.statut("Dossier du jeu détecté — confirme-le d'un clic "
                            "sur « Utiliser ».", "alerte")
            return
        installee = logique.version_installee(self.jeu)
        if not installee:
            self._appliquer_trad("absente" if derniere else "injoignable")
            if derniere:
                self._sortir_du_reduit()
            return
        if derniere is None:
            self._appliquer_trad("injoignable")
            return
        if logique.mise_a_jour_dispo(installee, derniere):
            self._appliquer_trad("maj")
            self._sortir_du_reduit()
        else:
            self._appliquer_trad("ajour")
            if lien:
                self._sortir_du_reduit()
            # Premier lancement d'une version fraîchement installée : son
            # patch-note s'affiche une fois (amélioration 4).
            if derniere == installee and self.cfg.get("note_vue") != installee:
                self.cfg["note_vue"] = installee
                if not self.demo:
                    logique.sauver_config(self.cfg)
                self._charger_note()

    def action_maj(self):
        if self.etat_trad == "injoignable" or not self.url_zip:
            self.verifier_version()
            return
        if not logique.jeu_valide(self.jeu):
            self._appliquer_trad("introuvable")
            return
        # Garde-fou ATELIER : sur la machine du mainteneur, installer la
        # release écraserait les corrections pas encore publiées (vécu le
        # 18/07/2026). Les joueurs ne verront jamais ce message.
        if os.path.isdir(r"D:\WOW_Priv\traduction"):
            self.statut("Atelier de traduction détecté : installer la release "
                        "écraserait le travail en cours. Utilise l'Atelier, "
                        "pas ce bouton.", "alerte")
            return
        self.pct, self.octets = 0, 0.0
        self._appliquer_trad("telechargement")

        def progres(fait, total):
            if total > 0:
                self.pct = fait * 100 // total
            else:
                self.octets = fait / 1048576.0

        def travail():
            try:
                chemin = logique.telecharger_fichier(self.url_zip, progres)
                self.pct = 100
                logique.installer_zip(chemin, self.jeu)
                self.after(0, self._maj_finie)
            except PermissionError:
                self.after(0, lambda: self._appliquer_trad("protege"))
            except Exception as e:
                self.after(0, lambda err=e: self._maj_ratee(err))
        threading.Thread(target=travail, daemon=True).start()

    def _maj_finie(self):
        self._appliquer_trad("reussie")
        self.rafraichir_stats()
        if self.derniere:
            self.cfg["note_vue"] = self.derniere
            logique.sauver_config(self.cfg)
        self._charger_note()

    def _maj_ratee(self, err):
        self._appliquer_trad("injoignable")
        self.statut("Échec : %s" % err, "erreur")

    def _relancer_admin(self):
        if getattr(sys, "frozen", False):
            programme, arguments = sys.executable, ""
        else:
            programme = sys.executable
            arguments = '"%s"' % os.path.abspath(
                os.path.join(os.path.dirname(__file__), "compagnon_v2.py"))
        r = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", programme, arguments, None, 1)
        if r <= 32:
            self.statut("Élévation refusée — clic droit sur le Compagnon → "
                        "« Exécuter en tant qu'administrateur ».", "alerte")
            return
        self.after(300, self.destroy)

    # --- améliorations v2.1 -------------------------------------------------- #
    def _reveiller(self):
        """Ramène la fenêtre devant (démarrage réduit avec du nouveau, ou jeu
        qui vient de se fermer) — façon ALERTE (demande de Dan, 21/07) :
        premier plan tenu plus longtemps + barre des tâches qui clignote."""
        try:
            if self.state() == "iconic":
                self.deiconify()
            self.lift()
            self.attributes("-topmost", True)
            self.after(4000, lambda: self.attributes("-topmost", False))
            # clignotement de la barre des tâches (Windows, sans dépendance)
            try:
                import ctypes
                ctypes.windll.user32.FlashWindow(
                    int(self.wm_frame(), 16), True)
            except Exception:
                pass
        except Exception:
            pass

    def _sortir_du_reduit(self):
        """Démarré réduit : la fenêtre ne ressort que s'il y a du nouveau."""
        if self.reduit and not self.demo:
            self._reveiller()

    def _basculer_reduit(self):
        """Case « Démarrer réduit » — l'état vit dans le fichier d'état local
        du Compagnon (compagnon.json, le même que le dossier du jeu)."""
        self.reduit = not self.reduit
        self.canvas.itemconfigure(
            self.it_case,
            image=self.decor.photo("case_coche" if self.reduit else "case"))
        self.cfg["demarrer_reduit"] = self.reduit
        if not self.demo:
            logique.sauver_config(self.cfg)

    def _total_contribue(self):
        """Total d'entrées envoyées depuis toujours. Au premier lancement, on
        part du nombre d'entrées déjà parties (mémoire des envois) si connu."""
        total = self.cfg.get("contribue_total")
        if total is None:
            total = len(self.cfg.get("envoyees") or [])
        try:
            return max(0, int(total))
        except (TypeError, ValueError):
            return 0

    def _maj_compteur(self):
        total = self._total_contribue()
        if total > 0:
            self.canvas.itemconfigure(self.txt_compteur, state="normal")
            self._poser_texte(
                self.txt_compteur,
                "Tu as fait traduire %s texte%s pour la communauté."
                % (format(total, ",").replace(",", " "),
                   "" if total == 1 else "s"),
                12, "#7a5a1a", gras=True)
        else:
            self.canvas.itemconfigure(self.txt_compteur, state="hidden")

    # Fermeture du jeu (amélioration 1) — boucle douce : une lecture toutes
    # les 10 s, et JAMAIS d'envoi automatique, seulement une invitation.
    def _demarrer_surveillance(self):
        if psutil is not None:
            threading.Thread(target=self._surveiller_jeu,
                             daemon=True).start()

    def _noms_exe_jeu(self):
        """Les exécutables plausibles du jeu : ceux VUS dans son dossier,
        plus les noms connus des clients Ascension."""
        noms = {"ascension.exe", "wow.exe", "project-ascension.exe"}
        jeu = self.jeu
        if logique.jeu_valide(jeu):
            try:
                for fichier in os.listdir(jeu):
                    if fichier.lower().endswith(".exe"):
                        noms.add(fichier.lower())
            except OSError:
                pass
        return noms

    def _surveiller_jeu(self):
        vivant = False
        while True:
            try:
                cibles = self._noms_exe_jeu()
                actuel = False
                for proc in psutil.process_iter(["name"]):
                    if (proc.info.get("name") or "").lower() in cibles:
                        actuel = True
                        break
                if vivant and not actuel:
                    self.after(0, self._jeu_ferme)
                vivant = actuel
            except Exception:
                pass                       # fenêtre fermée, accès refusé…
            time.sleep(10)

    # Voix françaises (2.1) — téléchargement + installation en un clic.
    # Fichiers LIBRES dans le dossier du jeu : le client les lit tel quel,
    # et le launcher ne nettoie que Data\ (prouvé le 21/07).
    def _lancer_voix(self):
        if self._voix_en_cours:
            return
        if not logique.jeu_valide(self.jeu):
            self.statut("Choisis d'abord le dossier du jeu pour installer "
                        "les voix.", "alerte")
            return
        self._voix_en_cours = True
        self.btn_voix.configurer("btn_voix_telech", actif=False)
        self.statut("Téléchargement des voix françaises (≈ 1 Go, sois "
                    "patient)…")

        def travail():
            try:
                dernier = [-1]

                def progres(fait, total):
                    if total:
                        p = fait * 100 // total
                        if p != dernier[0]:
                            dernier[0] = p
                            self.after(0, lambda v=p: self.statut(
                                "Téléchargement des voix françaises : "
                                "%d %%…" % v))
                chemin = logique.telecharger_fichier(logique.VOIX_URL,
                                                     progres)
                self.after(0, lambda: self.statut(
                    "Installation des voix dans le dossier du jeu…"))
                logique.installer_zip(chemin, self.jeu)
                self.after(0, self._voix_finies)
            except Exception as e:
                self.after(0, lambda err=e: self._voix_ratees(err))

        threading.Thread(target=travail, daemon=True).start()

    def _voix_finies(self):
        self._voix_en_cours = False
        self.btn_voix.configurer("btn_voix_fait", actif=False)
        self.statut("Voix françaises installées ! Redémarre complètement "
                    "le jeu pour les entendre. 🔊", "succes")

    def _voix_ratees(self, erreur):
        self._voix_en_cours = False
        self.btn_voix.configurer("btn_voix", actif=True)
        self.statut("Voix : téléchargement impossible (%s). Réessaie plus "
                    "tard." % erreur, "erreur")

    def _jeu_ferme(self):
        """Le jeu vient de se quitter : fenêtre devant + bandeau sur le bloc
        Contribuer. L'envoi reste uniquement au clic du joueur."""
        self._reveiller()
        self.canvas.itemconfigure(self.it_bandeau, state="normal")
        if not self.demo:
            self.rafraichir_stats()

    # Patch-note (amélioration 4) — réutilise l'adresse et les en-têtes que
    # compagnon.py connaît déjà pour lire les releases.
    def _charger_note(self):
        def travail():
            try:
                req = urllib.request.Request(logique.API_RELEASE,
                                             headers=logique.UA)
                with urllib.request.urlopen(
                        req, timeout=20,
                        context=logique.CONTEXTE_SSL) as r:
                    corps = json.load(r).get("body") or ""
            except Exception:
                corps = ""
            if corps:
                self.after(0, lambda: self._noter_corps(corps))
        threading.Thread(target=travail, daemon=True).start()

    def _noter_corps(self, corps):
        self.corps_note = corps
        self._montrer_note()

    def _montrer_note(self):
        """Pose le résumé du patch-note là où le bloc Traduction a la place :
        sous le titre après une installation réussie, à la place du lien
        (quand il est libre) une fois à jour. Caché partout ailleurs."""
        c, M = self.canvas, METRIQUE
        c.itemconfigure(self.txt_note, state="hidden")
        if not self.corps_note:
            return
        if self.etat_trad == "reussie":
            texte = resumer_patchnote(self.corps_note, 3)
            if not texte:
                return
            c.coords(self.txt_note, M["CX"] + M["B2_X"] - 26,
                     M["Y_B2"] + M["B2_ACTION"] - 6)
            c.itemconfigure(self.txt_note, anchor="nw", state="normal")
            self._poser_texte(self.txt_note, texte, 13, "#5a4020",
                              largeur=M["B2_W"] - 4, interligne=1.3)
        elif self.etat_trad == "ajour" and \
                c.itemcget(self.txt_lien, "state") != "normal":
            texte = resumer_patchnote(self.corps_note, 2)
            if not texte:
                return
            # Sous l'ombre du bouton « Tu es à jour », dans la réserve basse
            # du panneau doré — 2 lignes serrées au maximum.
            c.coords(self.txt_note, M["W"] // 2, M["Y_B2"] + 200)
            c.itemconfigure(self.txt_note, anchor="center", state="normal")
            self._poser_texte(self.txt_note, texte, 12, "#6b4c1c",
                              largeur=M["B2_W"] - 4, interligne=1.15)

    # Diagnostic « Tout va bien ? » (amélioration 6)
    def basculer_diag(self):
        self.diag_ouvert = not self.diag_ouvert
        etat = "normal" if self.diag_ouvert else "hidden"
        self.canvas.itemconfigure(self.it_diag_fond, state=etat)
        for ico, txt in self.diag_lignes:
            self.canvas.itemconfigure(ico, state="hidden")
            self.canvas.itemconfigure(txt, state=etat)
        if not self.diag_ouvert:
            return
        if self.demo:
            self._montrer_diag([
                (True, "Dossier du jeu : trouvé."),
                (True, "Addon installé : version 1.7.5 — à jour."),
                (False, "Sauvegarde illisible — lance le jeu une fois, puis "
                        "déconnecte-toi (ou /reload).")])
            return
        for _, txt in self.diag_lignes:
            self._poser_texte(txt, "Vérification…", 13, "#b4bac4")
        threading.Thread(target=self._diag_travail, daemon=True).start()

    def _diag_travail(self):
        resultats = []
        jeu_ok = logique.jeu_valide(self.jeu)
        resultats.append((bool(jeu_ok),
                          "Dossier du jeu : trouvé." if jeu_ok else
                          "Dossier du jeu introuvable — clique sur "
                          "« Changer… » et choisis-le."))
        version = jeu_ok and logique.version_installee(self.jeu)
        if version:
            if self.derniere and logique.mise_a_jour_dispo(version,
                                                           self.derniere):
                texte = ("Addon installé : version %s — la %s est disponible."
                         % (version, self.derniere))
            elif self.derniere:
                texte = "Addon installé : version %s — à jour." % version
            else:
                texte = "Addon installé : version %s." % version
            resultats.append((True, texte))
        else:
            resultats.append((False, "Addon non installé — utilise le grand "
                                     "bouton doré ci-dessus."))
        lisible = False
        if jeu_ok:
            for chemin in logique.fichiers_sauvegarde(self.jeu):
                try:
                    if logique.lire_sauvegarde(chemin) is not None:
                        lisible = True
                        break
                except Exception:
                    continue
        resultats.append((lisible,
                          "Sauvegarde lisible — tes découvertes sont prêtes "
                          "à partir." if lisible else
                          "Sauvegarde introuvable ou illisible — lance le "
                          "jeu une fois, puis déconnecte-toi (ou /reload)."))
        self.after(0, lambda: self._montrer_diag(resultats))

    def _montrer_diag(self, resultats):
        if not self.diag_ouvert:
            return
        for (ok, texte), (ico, txt) in zip(resultats, self.diag_lignes):
            self.canvas.itemconfigure(
                ico, state="normal",
                image=self.decor.photo("ico_ok" if ok else "ico_ko"))
            self._poser_texte(txt, texte, 13,
                              "#a9e29a" if ok else "#f0b39c", largeur=356)

    # --- mise à jour du Compagnon lui-même ---------------------------------- #
    def maj_compagnon(self):
        if not getattr(sys, "frozen", False) or not self.url_exe:
            webbrowser.open(logique.PAGE_RELEASES)
            return
        self._poser_texte(self.txt_lien, "Téléchargement du nouveau "
                          "Compagnon…", 13, "#7d5518", souligne=True)

        def progres(fait, total):
            if total > 0:
                self.after(0, lambda p=fait * 100 // total:
                           self._poser_texte(
                               self.txt_lien,
                               "Nouveau Compagnon… %d %%" % p, 13,
                               "#7d5518", souligne=True))

        def travail():
            try:
                nouveau = logique.telecharger_fichier(self.url_exe, progres,
                                                      ".exe")
                self.after(0, lambda n=nouveau: self._redemarrer_avec(n))
            except Exception as e:
                self.after(0, lambda err=e: self._maj_compagnon_ratee(err))
        threading.Thread(target=travail, daemon=True).start()

    def _redemarrer_avec(self, nouveau):
        self.statut("Nouvelle version téléchargée — redémarrage…", "succes")
        logique.lancer_remplacement(nouveau, sys.executable)
        self.after(500, self.destroy)

    def _maj_compagnon_ratee(self, err):
        self._poser_texte(self.txt_lien, "Mise à jour impossible — clique "
                          "ici pour la page de téléchargement ›", 13,
                          "#7d5518", souligne=True)
        self.statut("Échec : %s" % err, "erreur")

    # --- rapport de contribution -------------------------------------------- #
    def envoyer_rapport(self):
        if not logique.jeu_valide(self.jeu):
            self.statut("Choisis d'abord le dossier du jeu.", "alerte")
            return
        try:
            rapport, total, empreintes = logique.construire_rapport(
                self.jeu, logique.deja_envoyees())
        except Exception as e:
            self.statut("Lecture impossible : %s" % e, "erreur")
            return
        if total == 0:
            self._appliquer_contrib(
                "vide", "Tout ce que tu avais est déjà parti — merci !")
            self.statut("Rejoue un peu : l'addon notera du nouveau.",
                        "succes")
            self.after(6000, self.rafraichir_stats)
            return
        self._appliquer_contrib("envoi", "Envoi en cours…")
        self.statut("Envoi du rapport…", "neutre")

        def travail():
            try:
                caches, _ = logique.extraire_caches(self.jeu)
                logique.envoyer_rapport_discord(rapport, caches)
                self.after(0, lambda: self._envoi_reussi(total, empreintes))
            except Exception:
                self.after(0, lambda: self._envoi_rate(rapport))
        threading.Thread(target=travail, daemon=True).start()

    def _envoi_reussi(self, total, empreintes):
        self._appliquer_contrib(
            "reussi", "Rapport envoyé (%d entrée(s)) — merci !" % total)
        self.statut("Chaque rapport fait avancer la traduction.", "succes")
        self.canvas.itemconfigure(self.it_bandeau, state="hidden")
        # Compteur de contribution : le cumul AVANT d'ajouter les empreintes
        # (le premier total par défaut se lit dans les envois passés).
        self.cfg["contribue_total"] = self._total_contribue() + total
        self.cfg["dernier_envoi"] = time.strftime("%d/%m/%Y")
        logique.noter_envoyees(self.cfg, empreintes)   # sauve aussi le cumul
        self._maj_compteur()
        self.after(6000, self._rearmer_envoi)

    def _rearmer_envoi(self):
        self.etat_contrib = None
        self.rafraichir_stats()

    def _envoi_rate(self, rapport):
        self.clipboard_clear()
        self.clipboard_append(rapport)
        self._appliquer_contrib(
            "horsligne", "Hors ligne : ton rapport a été copié. Colle-le sur "
                         "Discord pour l'envoyer.")
        self.statut("Envoi impossible (hors ligne ?) — rapport copié à la "
                    "place.", "alerte")
        self.after(8000, self._rearmer_envoi)

    def copier_rapport(self):
        if not logique.jeu_valide(self.jeu):
            self.statut("Choisis d'abord le dossier du jeu.", "alerte")
            return
        try:
            rapport, total, _ = logique.construire_rapport(self.jeu)
        except Exception as e:
            self.statut("Lecture impossible : %s" % e, "erreur")
            return
        if total == 0:
            self.statut("Rien à signaler pour l'instant — joue, l'addon note "
                        "tout seul ! (Ou fais /reload en jeu.)", "alerte")
            return
        self.clipboard_clear()
        self.clipboard_append(rapport)
        self.statut("Rapport copié (%d entrées) ! Colle-le sur le Discord "
                    "(Ctrl+V)." % total, "succes")

    # --- mode démonstration (captures d'écran, jamais en production) -------- #
    def _appliquer_demo(self):
        trans, contrib = self.demo[0], self.demo[1]
        drapeaux = self.demo[2] if len(self.demo) > 2 else frozenset()
        self.derniere = "1.8.0"
        self.textes_actifs = 338276
        if trans == "telechargement":
            self.pct = 34
        self._appliquer_trad(trans)
        if trans == "ajour" and "note" not in drapeaux:
            self.canvas.itemconfigure(self.txt_lien, state="normal")
            self._poser_texte(
                self.txt_lien, "Une nouvelle version de l'application (1.8) "
                "est disponible ›", 13, "#7d5518", souligne=True)
        messages = {
            "attente": "12 entrées prêtes à partir · dernier envoi : "
                       "15/07/2026",
            "rien": "Rien de nouveau à signaler · dernier envoi : 18/07/2026",
            "envoi": "Envoi en cours…",
            "reussi": "Rapport envoyé (12 entrées) — merci !",
            "horsligne": "Hors ligne : ton rapport a été copié. Colle-le sur "
                         "Discord pour l'envoyer.",
            "vide": "Tout ce que tu avais est déjà parti — merci !",
        }
        self._appliquer_contrib(contrib, messages[contrib])
        # Drapeaux v2.1 (rien n'est écrit sur disque en démo).
        if "compteur" in drapeaux:
            self.cfg["contribue_total"] = 3147
            self._maj_compteur()
        if "propose" in drapeaux:
            self.jeu, self.jeu_propose = None, (
                r"C:\Program Files\Ascension Launcher\resources\client")
            self._rafraichir_jeu()
            self.statut("Dossier du jeu détecté — confirme-le d'un clic sur "
                        "« Utiliser ».", "alerte")
        if "reduit" in drapeaux:
            self.reduit = True
            self.canvas.itemconfigure(self.it_case,
                                      image=self.decor.photo("case_coche"))
        if "note" in drapeaux:
            self.corps_note = (
                "## Version 1.8.0\n"
                "- 2 400 nouveaux textes de quêtes traduits\n"
                "- Les fenêtres propres à Ascension passent en français\n"
                "- Corrections signalées par la communauté")
            self._montrer_note()
        if "jeuferme" in drapeaux:
            self._jeu_ferme()
        if "diag" in drapeaux:
            self.basculer_diag()


def lancer(demo=None):
    CompagnonV2(demo).mainloop()
