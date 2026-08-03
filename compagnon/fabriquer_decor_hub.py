# -*- coding: utf-8 -*-
"""
Fabrique les décors PNG du HUB (interface v3) — vraies textures de WoW.
=======================================================================
Outil de CONSTRUCTION, jamais livré aux joueurs. Contrairement aux décors v2
(rendus depuis le CSS d'une maquette), ceux du Hub sont assemblés directement
depuis les textures officielles du jeu (pack wow-ui-textures fourni par Dan)
et les polices extraites du client (Morpheus, Friz Quadrata) :

  - le cadre doré ornementé des fenêtres légendaires (atlas 8 cases —
    étalonnage du 22/07 : case 3 tournée 270°/90° pour les bords haut/bas,
    case 4 ignorée) ;
  - le parchemin des hauts faits pour la zone de contenu (pourtour rogné
    avant tuilage, sinon coutures) ;
  - le fond sombre des boîtes de dialogue pour la barre latérale ;
  - le bouton rouge classique en 3 tranches (marges transparentes
    asymétriques : recadrage bbox obligatoire avant découpe) ;
  - les cases d'objets (UI-Quickslot2) pour encadrer les icônes.

Écrit `assets/hub/*.png`, le manifeste `decor_hub.json` (taille + marge
d'ombre de chaque pièce) et copie les polices dans `assets/hub/fonts/`.

Usage : `python fabriquer_decor_hub.py`
"""
import json
import os
import shutil

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from interface_hub import METRIQUE as M

ICI = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(ICI)
PACK = os.path.join(BASE, "Ajouter par Dan", "wow-ui-textures")
POLICES = os.path.join(BASE, "sources", "fonts")
SORTIE = os.path.join(ICI, "assets", "hub")

OR_VIF = (255, 209, 0, 255)          # l'or de WoW (#ffd100)
OR_SOMBRE = (138, 106, 42, 255)
ENCRE = (61, 43, 18, 255)
ENCRE_DOUCE = (90, 64, 32, 255)
BEIGE = (233, 220, 187, 255)
BEIGE_VIF = (255, 242, 204, 255)
GRIS_INACTIF = (154, 160, 171, 255)
VERT_DOUX = (143, 191, 127, 255)

MANIFESTE = {}
_CACHE = {}


def texture(*chemin):
    cle = "/".join(chemin)
    if cle not in _CACHE:
        _CACHE[cle] = Image.open(os.path.join(PACK, *chemin)).convert("RGBA")
    return _CACHE[cle].copy()


def police(nom, px):
    return ImageFont.truetype(os.path.join(POLICES, nom), px)


def sauver(nom, image, pad=0):
    image.save(os.path.join(SORTIE, nom + ".png"))
    MANIFESTE[nom] = {"w": image.width - 2 * pad,
                      "h": image.height - 2 * pad, "pad": pad}
    print("  %-26s %dx%d (marge %d)" % (nom, image.width, image.height, pad))


# --------------------------------------------------------------------------- #
# Aides de dessin
# --------------------------------------------------------------------------- #
def degrade_vertical(l, h, haut, bas):
    """Rectangle en dégradé vertical (interpolation ligne à ligne)."""
    img = Image.new("RGBA", (l, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (l, y)], fill=tuple(
            int(haut[i] + (bas[i] - haut[i]) * t) for i in range(4)))
    return img


def coin_arrondi(l, h, rayon, remplir):
    img = Image.new("RGBA", (l, h))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, l - 1, h - 1), rayon,
                                          fill=remplir)
    return img


def panneau_ombre(l, h, pad, dessiner):
    """Toile (l+2·pad)×(h+2·pad) : ombre portée douce sous la forme, puis le
    contenu dessiné par `dessiner(toile, pad)` (coin utile à (pad, pad))."""
    toile = Image.new("RGBA", (l + 2 * pad, h + 2 * pad))
    if pad:
        ombre = Image.new("RGBA", toile.size)
        ImageDraw.Draw(ombre).rounded_rectangle(
            (pad, pad + 3, pad + l, pad + h + 3), 12, fill=(15, 8, 0, 110))
        toile.alpha_composite(ombre.filter(ImageFilter.GaussianBlur(6)))
    dessiner(toile, pad)
    return toile


def parchemin_creuse(toile, x, y, l, h, rayon=10, clair=False):
    """Un panneau « taillé dans le parchemin » : fond légèrement plus clair,
    liseré sombre, filet d'or, ligne de lumière en haut."""
    d = ImageDraw.Draw(toile)
    haut = (242, 229, 194, 255) if clair else (239, 224, 184, 255)
    bas = (224, 203, 152, 255) if clair else (226, 205, 151, 255)
    fond = degrade_vertical(l, h, haut, bas)
    masque = coin_arrondi(l, h, rayon, (255, 255, 255, 255))
    toile.paste(fond, (x, y), masque)
    d.rounded_rectangle((x, y, x + l - 1, y + h - 1), rayon,
                        outline=(138, 106, 42, 255), width=1)
    d.rounded_rectangle((x + 1, y + 1, x + l - 2, y + h - 2), rayon - 1,
                        outline=(201, 173, 114, 200), width=1)
    d.line([(x + rayon, y + 2), (x + l - rayon, y + 2)],
           fill=(255, 248, 224, 130))


def texte_grave(toile, xy, texte, fonte, remplir, ancre="mm", relief=True):
    """Texte à la manière du jeu : ombre douce dessous, trait net dessus."""
    d = ImageDraw.Draw(toile)
    x, y = xy
    if relief:
        d.text((x + 1, y + 1), texte, font=fonte, fill=(20, 10, 0, 150),
               anchor=ancre)
    d.text((x, y), texte, font=fonte, fill=remplir, anchor=ancre)


def texte_or(toile, xy, texte, fonte, ancre="mm", remplir=OR_VIF,
             contour=(56, 22, 8, 255), epaisseur=2):
    """Le libellé doré des boutons WoW : or vif, contour brun sombre."""
    d = ImageDraw.Draw(toile)
    d.text(xy, texte, font=fonte, fill=remplir, anchor=ancre,
           stroke_width=epaisseur, stroke_fill=contour)


# --------------------------------------------------------------------------- #
# La PLAQUE d'infobulle du jeu (lot 12, règle n° 1) : jamais d'encre sur le
# bois — tout texte posé sur la texture bruitée passe sur cette plaque, comme
# WoW le fait lui-même. Fond `Tooltips/UI-Tooltip-Background` teinté du bleu
# nuit des infobulles du jeu, entouré des 8 bords `UI-Tooltip-TL/T/TR/L/R/
# BL/B/BR` (⚠️ pas l'atlas `UI-Tooltip-Border`, qui est une autre pièce).
# --------------------------------------------------------------------------- #
def plaque_infobulle(l, h):
    fond_tex = texture("Tooltips", "UI-Tooltip-Background.PNG")
    # La texture est un gris translucide : le jeu la teinte au rendu
    # (TOOLTIP_DEFAULT_BACKGROUND_COLOR, bleu nuit). On fait pareil.
    teinte = Image.new("RGBA", fond_tex.size, (18, 18, 38, 255))
    fond_tex = Image.composite(
        teinte, fond_tex, Image.new("L", fond_tex.size, 205))
    toile = Image.new("RGBA", (l, h))
    for y in range(0, h, fond_tex.height):
        for x in range(0, l, fond_tex.width):
            toile.alpha_composite(fond_tex, (x, y))
    # Un léger dégradé pour ne pas être un aplat mort
    toile.alpha_composite(degrade_vertical(l, h, (255, 255, 255, 10),
                                           (0, 0, 0, 40)))
    b = 8                                  # les bords font 8×8
    bords = {n: texture("Tooltips", "UI-Tooltip-%s.PNG" % n)
             for n in ("TL", "T", "TR", "L", "R", "BL", "B", "BR")}
    toile.alpha_composite(bande(bords["T"], l - 2 * b, False), (b, 0))
    toile.alpha_composite(bande(bords["B"], l - 2 * b, False), (b, h - b))
    toile.alpha_composite(bande(bords["L"], h - 2 * b, True), (0, b))
    toile.alpha_composite(bande(bords["R"], h - 2 * b, True), (l - b, b))
    toile.alpha_composite(bords["TL"], (0, 0))
    toile.alpha_composite(bords["TR"], (l - b, 0))
    toile.alpha_composite(bords["BL"], (0, h - b))
    toile.alpha_composite(bords["BR"], (l - b, h - b))
    return toile


# --------------------------------------------------------------------------- #
# Cadre doré (atlas 8 cases) et fonds — recettes éprouvées de la vitrine
# --------------------------------------------------------------------------- #
def decouper_bordure():
    atlas = texture("DialogFrame", "UI-DialogBox-Gold-Border.PNG")
    case = atlas.width // 8
    return [atlas.crop((i * case, 0, (i + 1) * case, atlas.height))
            for i in range(8)], case


def bande(piece, longueur, verticale):
    c = piece.width
    if verticale:
        strip = Image.new("RGBA", (c, longueur))
        for y in list(range(0, longueur - c, c)) + [longueur - c]:
            strip.paste(piece, (0, y))
    else:
        strip = Image.new("RGBA", (longueur, c))
        for x in list(range(0, longueur - c, c)) + [longueur - c]:
            strip.paste(piece, (x, 0))
    return strip


def poser_cadre(toile):
    pieces, c = decouper_bordure()
    gauche, droite, barre, _fine, hg, hd, bg, bd = pieces
    haut = barre.transpose(Image.ROTATE_270)
    bas = barre.transpose(Image.ROTATE_90)
    L, H = toile.size
    toile.alpha_composite(bande(haut, L - 2 * c, False), (c, 0))
    toile.alpha_composite(bande(bas, L - 2 * c, False), (c, H - c))
    toile.alpha_composite(bande(gauche, H - 2 * c, True), (0, c))
    toile.alpha_composite(bande(droite, H - 2 * c, True), (L - c, c))
    toile.alpha_composite(hg, (0, 0))
    toile.alpha_composite(hd, (L - c, 0))
    toile.alpha_composite(bg, (0, H - c))
    toile.alpha_composite(bd, (L - c, H - c))


def fond_parchemin(l, h):
    parchemin = texture("ACHIEVEMENTFRAME",
                        "UI-Achievement-Parchment-Horizontal.PNG")
    r = 20                        # pourtour assombri : rogné avant tuilage
    parchemin = parchemin.crop((r, r, parchemin.width - r,
                                parchemin.height - r))
    tuile = parchemin.resize((h * 2, h), Image.LANCZOS)
    fond = Image.new("RGBA", (l, h))
    x, miroir = 0, False
    while x < l:
        fond.paste(tuile.transpose(Image.FLIP_LEFT_RIGHT) if miroir
                   else tuile, (x, 0))
        x += tuile.width
        miroir = not miroir
    return fond


def fond_sombre(l, h):
    """La barre latérale : fond de boîte de dialogue tuilé, assombri vers le
    bas pour donner de la profondeur."""
    tuile = texture("DialogFrame", "UI-DialogBox-Background-Dark.PNG")
    fond = Image.new("RGBA", (l, h))
    for y in range(0, h, tuile.height):
        for x in range(0, l, tuile.width):
            fond.paste(tuile, (x, y))
    voile = degrade_vertical(l, h, (0, 0, 0, 40), (0, 0, 0, 120))
    fond.alpha_composite(voile)
    return fond


def icone_encadree(nom_icone, cote):
    """Une icône du jeu dans sa case d'objet (UI-Quickslot2), comme dans les
    sacs : l'icône SOUS la case, qui déborde d'environ 12/64 autour du trou."""
    case = texture("Buttons", "UI-Quickslot2.PNG")
    icone = texture("ICONS", nom_icone)
    r = 5                                    # liseré sombre baké dans l'icône
    icone = icone.crop((r, r, icone.width - r, icone.height - r))
    toile = Image.new("RGBA", (cote, cote))
    marge = round(cote * 12 / case.width)
    toile.alpha_composite(
        icone.resize((cote - 2 * marge, cote - 2 * marge), Image.LANCZOS),
        (marge, marge))
    toile.alpha_composite(case.resize((cote, cote), Image.LANCZOS), (0, 0))
    return toile


# --------------------------------------------------------------------------- #
# Le fond de la fenêtre
# --------------------------------------------------------------------------- #
def fabriquer_fond():
    L, H = M["W"], M["H"]
    toile = Image.new("RGBA", (L, H), (10, 10, 12, 255))
    # Barre latérale sombre et zone de contenu parchemin
    toile.paste(fond_sombre(M["SB_W"], M["SB_H"]), (M["SB_X"], M["SB_Y"]))
    toile.paste(fond_parchemin(M["CT_W"], M["SB_H"]), (M["CT_X"], M["SB_Y"]))
    d = ImageDraw.Draw(toile)
    # Couture dorée entre les deux
    x = M["CT_X"]
    d.line([(x - 2, M["SB_Y"]), (x - 2, M["SB_Y"] + M["SB_H"])],
           fill=(30, 18, 6, 220), width=2)
    d.line([(x, M["SB_Y"]), (x, M["SB_Y"] + M["SB_H"])],
           fill=(125, 85, 24, 255), width=1)
    d.line([(x + 1, M["SB_Y"]), (x + 1, M["SB_Y"] + M["SB_H"])],
           fill=(199, 154, 62, 180), width=1)
    # Écusson de la barre latérale : anneau d'or autour du logo
    centre_sb = M["SB_X"] + M["SB_W"] // 2
    cote = M["CRETE"]
    logo = Image.open(os.path.join(ICI, "assets", "logo.png")) \
        .convert("RGBA").resize((cote - 6, cote - 6), Image.LANCZOS)
    masque = Image.new("L", logo.size, 0)
    ImageDraw.Draw(masque).ellipse((0, 0) + logo.size, fill=255)
    x0, y0 = centre_sb - cote // 2, M["Y_CRETE"]
    d.ellipse((x0 - 2, y0 - 2, x0 + cote + 2, y0 + cote + 2),
              fill=(35, 24, 10, 255))
    toile.paste(logo, (x0 + 3, y0 + 3), masque)
    for ecart, coul in ((0, (125, 85, 24, 255)), (1, (246, 221, 149, 255)),
                        (2, (199, 154, 62, 255)), (3, (110, 76, 20, 255))):
        d.ellipse((x0 - ecart, y0 - ecart, x0 + cote + ecart,
                   y0 + cote + ecart), outline=coul, width=1)
    # Le dragon doré LOVÉ AUTOUR de l'écusson (demande de Dan, 23/07) —
    # même recette que la vitrine : posé APRÈS l'anneau pour passer devant,
    # sa courbe épouse le logo (ratios d'essais visuels de la bannière).
    dragon = texture("DialogFrame", "UI-DialogBox-Gold-Dragon.PNG")
    cote_d = int(cote * 1.9)
    dragon = dragon.resize((cote_d, cote_d), Image.LANCZOS)
    toile.alpha_composite(dragon, (int(x0 - cote_d * 0.30),
                                   int(y0 - cote_d * 0.18)))
    texte_grave(toile, (centre_sb, y0 + cote + 22), "Le jeu en français.",
                police("FRIZQT__.TTF", 13), (183, 154, 118, 255))
    # Petit trait décoratif : un filet d'or qui s'estompe aux deux bouts
    # (la texture Divider ressortait en barre grise terne).
    y_filet = y0 + cote + 40
    demi = 80
    for dx in range(-demi, demi + 1):
        force = 1 - abs(dx) / demi
        alpha = int(190 * force)
        d.point((centre_sb + dx, y_filet),
                fill=(199, 154, 62, alpha))
        d.point((centre_sb + dx, y_filet + 1),
                fill=(90, 60, 18, int(alpha * 0.7)))
    # Cadre doré par-dessus tout
    poser_cadre(toile)
    # Fronton du titre, centré sur la fenêtre. La texture traîne une grande
    # ombre douce sous la plaque : elle grisait tous les textes des vues qui
    # passaient dessous — on coupe la texture à la dernière ligne franche.
    fronton = texture("DialogFrame", "UI-DialogBox-Gold-Header.PNG")
    alpha = fronton.split()[3]
    bas = fronton.height
    for yy in range(fronton.height - 1, -1, -1):
        if alpha.crop((0, yy, fronton.width, yy + 1)).getextrema()[1] > 110:
            bas = yy + 1
            break
    fronton = fronton.crop((0, 0, fronton.width, bas))
    h_fronton = round(M["FRONTON_W"] * bas / fronton.width)
    fronton = fronton.resize((M["FRONTON_W"], h_fronton), Image.LANCZOS)
    fx = (L - M["FRONTON_W"]) // 2
    toile.alpha_composite(fronton, (fx, 0))
    texte_or(toile, (L // 2, 34), "ASCENSION FR",
             police("MORPHEUS.TTF", 28), epaisseur=2)
    sauver("fond", toile)


# --------------------------------------------------------------------------- #
# Navigation
# --------------------------------------------------------------------------- #
NAV = (
    ("accueil", "Accueil", "INV_Misc_Map_01.PNG"),
    ("traduction", "Traduction", "INV_Misc_Book_09.PNG"),
    ("voix", "Voix", "Ability_Warrior_RallyingCry.PNG"),
    ("addons", "Addons", "INV_Misc_Bag_08.PNG"),
    ("contribuer", "Contribuer", "INV_Letter_15.PNG"),
)


def fabriquer_navigation():
    l, h = M["NAV_W"], M["NAV_H"]
    fonte = police("FRIZQT__.TTF", 17)
    for vue, libelle, icone in NAV:
        for etat in ("", "survol", "actif"):
            toile = Image.new("RGBA", (l, h))
            d = ImageDraw.Draw(toile)
            if etat == "survol":
                d.rounded_rectangle((0, 0, l - 1, h - 1), 8,
                                    fill=(255, 235, 170, 26),
                                    outline=(255, 235, 170, 45))
            elif etat == "actif":
                voile = degrade_vertical(l, h, (255, 209, 0, 52),
                                         (255, 209, 0, 10))
                masque = coin_arrondi(l, h, 8, (255, 255, 255, 255))
                toile.paste(voile, (0, 0), masque)
                d.rounded_rectangle((0, 0, l - 1, h - 1), 8,
                                    outline=(199, 154, 62, 120))
                d.rounded_rectangle((0, h // 2 - 12, 3, h // 2 + 12), 2,
                                    fill=OR_VIF)
            toile.alpha_composite(icone_encadree(icone, 34), (8, 6))
            couleur = {"": BEIGE, "survol": BEIGE_VIF,
                       "actif": OR_VIF}[etat]
            texte_grave(toile, (52, h // 2), libelle, fonte, couleur,
                        ancre="lm")
            nom = "nav_" + vue + ("_" + etat if etat else "")
            sauver(nom, toile)


# --------------------------------------------------------------------------- #
# Boutons rouges classiques (3 tranches + libellé doré)
# --------------------------------------------------------------------------- #
def base_bouton(l, h, etat="up"):
    nom = {"up": "UI-Panel-Button-Up.PNG",
           "off": "UI-Panel-Button-Disabled.PNG"}[etat]
    bouton = texture("Buttons", nom)
    bouton = bouton.crop(bouton.getbbox())    # marges asymétriques : rognées
    bout = 12
    ech = h / bouton.height
    lb = max(1, round(bout * ech))
    gauche = bouton.crop((0, 0, bout, bouton.height)) \
        .resize((lb, h), Image.LANCZOS)
    droite = bouton.crop((bouton.width - bout, 0, bouton.width,
                          bouton.height)).resize((lb, h), Image.LANCZOS)
    centre = bouton.crop((bout, 0, bouton.width - bout, bouton.height)) \
        .resize((l - 2 * lb, h), Image.LANCZOS)
    toile = Image.new("RGBA", (l, h))
    toile.alpha_composite(gauche, (0, 0))
    toile.alpha_composite(centre, (lb, 0))
    toile.alpha_composite(droite, (l - lb, 0))
    return toile


def bouton_rouge(nom, l, h, libelle, px=18, survol=True, etat="up",
                 couleur=OR_VIF, fleche=False):
    toile = base_bouton(l, h, etat)
    fonte = police("FRIZQT__.TTF", px)
    d = ImageDraw.Draw(toile)
    x = l // 2
    if fleche:
        larg = d.textlength(libelle, font=fonte)
        x0 = (l - (14 + 8 + larg)) // 2
        cy = h // 2
        d.polygon([(x0, cy - 7), (x0, cy + 7), (x0 + 12, cy)],
                  fill=couleur, outline=(56, 22, 8, 255))
        texte_or(toile, (x0 + 20, cy), libelle, fonte, ancre="lm",
                 remplir=couleur)
    else:
        texte_or(toile, (x, h // 2), libelle, fonte, remplir=couleur)
    sauver(nom, toile)
    if survol:
        clair = ImageEnhance.Brightness(toile).enhance(1.16)
        sauver(nom + "_survol", clair)


def bouton_neutre(nom, l, h, libelle, px=15):
    """Un bouton SECONDAIRE : la matière du bouton du jeu, désaturée vers la
    pierre. Arbitrage de Dan (28/07) : le rouge appartient à l'action
    principale — « Couper les voix » ne doit plus concurrencer « Mettre à
    jour » à l'œil."""
    toile = base_bouton(l, h)
    toile = ImageEnhance.Color(toile).enhance(0.18)
    toile = ImageEnhance.Brightness(toile).enhance(0.92)
    fonte = police("FRIZQT__.TTF", px)
    texte_or(toile, (l // 2, h // 2), libelle, fonte, remplir=BEIGE_VIF,
             contour=(25, 20, 12, 255))
    sauver(nom, toile)
    clair = ImageEnhance.Brightness(toile).enhance(1.16)
    sauver(nom + "_survol", clair)


def fabriquer_boutons():
    L, H = M["BTN_L_W"], M["BTN_L_H"]
    bouton_rouge("btn_lancer", M["BTN_LANCER_W"], M["BTN_LANCER_H"],
                 "Lancer le jeu", px=18, fleche=True)
    bouton_rouge("btn_installer", L, H, "Installer la traduction")
    bouton_rouge("btn_maj", L, H, "Mettre à jour")
    bouton_rouge("btn_reessayer", L, H, "Réessayer")
    bouton_rouge("btn_admin", L, H, "Relancer en administrateur", px=16)
    # (« btn_fait » et « btn_voix_fait » ne sont plus cuits : un état ne doit
    # pas ressembler à un bouton — lot 12, point 6. L'état vit désormais dans
    # le titre du panneau, le badge et la pastille.)
    bouton_rouge("btn_voix", L, H, "Installer les voix françaises", px=17)
    # Bascule « couper / remettre » (demande d'un joueur, 23/07) : les
    # voix sont des fichiers, la bascule renomme le dossier Sound.
    # « Couper » est NEUTRE (voir bouton_neutre) ; « Remettre » reste rouge :
    # quand les voix sont coupées, le remettre EST l'action principale.
    bouton_neutre("btn_voix_couper", 220, 36, "Couper les voix", px=15)
    bouton_rouge("btn_voix_remettre", 220, 36, "Remettre les voix", px=15)
    bouton_rouge("btn_envoyer", M["BTN_M_W"], M["BTN_M_H"],
                 "Envoyer mon rapport", px=17)
    bouton_rouge("btn_envoyer_gris", M["BTN_M_W"], M["BTN_M_H"],
                 "Envoyer mon rapport", px=17, survol=False, etat="off",
                 couleur=GRIS_INACTIF)
    # LE BOUTON FANTÔME (bloc B du programme 23, 02/08/2026). Quand un envoi
    # ratait, le Hub écrivait « copie le rapport (bouton ci-dessous) » — et ce
    # bouton n'existait pas. Il existe maintenant. SECONDAIRE (pierre) :
    # l'action principale reste « Envoyer », l'arbitrage de Dan du 28/07 vaut
    # ici comme pour « Couper les voix ».
    # Pas d'état « gris » : copier est TOUJOURS possible, et c'est même le
    # SEUL chemin quand le webhook est absent (compagnon.py l. 69-72). Un
    # bouton grisé mentirait ; s'il n'y a rien à copier, la barre d'état le
    # dit — exactement comme le faisait le Compagnon v2.
    bouton_neutre("btn_copier", M["BTN_M_W"], M["BTN_M_H"],
                  "Copier mon rapport", px=17)
    bouton_rouge("btn_changer", M["BTN_P_W"], M["BTN_P_H"], "Changer…",
                 px=14)
    lc, hc = M["BTN_C_W"], M["BTN_C_H"]
    bouton_rouge("btn_carte_installer", lc, hc, "Installer", px=14)
    bouton_rouge("btn_carte_maj", lc, hc, "Mettre à jour", px=14)
    # Il existait sur le disque sans recette (fait à part, préservé par la
    # fusion du manifeste) : maintenant il se régénère comme les autres.
    bouton_rouge("btn_carte_desinstaller", lc, hc, "Désinstaller", px=14)
    bouton_rouge("btn_carte_installe", lc, hc, "Installé", px=14,
                 survol=False, etat="off", couleur=VERT_DOUX)
    bouton_rouge("btn_carte_bientot", lc, hc, "Bientôt…", px=14,
                 survol=False, etat="off", couleur=GRIS_INACTIF)
    bouton_rouge("btn_carte_absent", lc, hc, "Indisponible", px=14,
                 survol=False, etat="off", couleur=GRIS_INACTIF)


# --------------------------------------------------------------------------- #
# Panneaux, tuiles, cartes
# --------------------------------------------------------------------------- #
def fabriquer_panneaux():
    pad = 12

    def tuile(toile, p):
        parchemin_creuse(toile, p, p, M["TUILE_W"], M["TUILE_H"], clair=True)
    sauver("tuile", panneau_ombre(M["TUILE_W"], M["TUILE_H"], pad, tuile),
           pad)

    def carte(toile, p):
        parchemin_creuse(toile, p, p, M["CARTE_W"], M["CARTE_H"], clair=True)
    sauver("carte", panneau_ombre(M["CARTE_W"], M["CARTE_H"], pad, carte),
           pad)

    def nouvelles(toile, p):
        parchemin_creuse(toile, p, p, M["CW"], M["PAN_NOUV_H"])
    sauver("panneau_nouvelles",
           panneau_ombre(M["CW"], M["PAN_NOUV_H"], pad, nouvelles), pad)

    def panneau_or(toile, p):
        l, h = M["CW"], M["PAN_OR_H"]
        parchemin_creuse(toile, p, p, l, h, rayon=12)
        d = ImageDraw.Draw(toile)
        d.rounded_rectangle((p + 3, p + 3, p + l - 4, p + h - 4), 10,
                            outline=(125, 85, 24, 255), width=2)
        d.rounded_rectangle((p + 5, p + 5, p + l - 6, p + h - 6), 9,
                            outline=(246, 221, 149, 140), width=1)
        for cx, cy in ((p + 13, p + 13), (p + l - 13, p + 13),
                       (p + 13, p + h - 13), (p + l - 13, p + h - 13)):
            d.ellipse((cx - 5, cy - 5, cx + 5, cy + 5),
                      fill=(199, 154, 62, 255),
                      outline=(110, 76, 20, 255))
            d.ellipse((cx - 5, cy - 5, cx + 1, cy + 1),
                      fill=(246, 221, 149, 160))
    sauver("panneau_or",
           panneau_ombre(M["CW"], M["PAN_OR_H"], pad, panneau_or), pad)

    def lettre(toile, p):
        l, h = M["CW"], M["PAN_LETTRE_H"]
        feuille = Image.new("RGBA", (l, h))
        fond = degrade_vertical(l, h, (242, 229, 194, 255),
                                (224, 203, 152, 255))
        masque = coin_arrondi(l, h, 9, (255, 255, 255, 255))
        feuille.paste(fond, (0, 0), masque)
        df = ImageDraw.Draw(feuille)
        df.rounded_rectangle((0, 0, l - 1, h - 1), 9,
                             outline=(120, 85, 35, 160), width=1)
        # Sceau de cire en haut à droite
        sx, sy, r = l - 62, 40, 21
        for ecart, coul in ((0, (106, 23, 13, 255)),
                            (-3, (142, 36, 23, 255)),
                            (-7, (208, 73, 47, 255))):
            df.ellipse((sx - r - ecart // 2, sy - r - ecart // 2,
                        sx + r + ecart, sy + r + ecart), fill=coul)
        df.ellipse((sx - r + 7, sy - r + 7, sx + r - 7, sy + r - 7),
                   outline=(60, 10, 5, 150), width=2)
        feuille = feuille.rotate(-0.6, expand=True, resample=Image.BICUBIC)
        toile.alpha_composite(feuille, (p - 2, p - 2))
    sauver("parchemin_lettre",
           panneau_ombre(M["CW"], M["PAN_LETTRE_H"], 14, lettre), 14)


# --------------------------------------------------------------------------- #
# Badges, barres, états
# --------------------------------------------------------------------------- #
def fabriquer_badges():
    # Le badge « tout va bien » : pièce d'or, coche verte
    cote, pad = 56, 6
    toile = Image.new("RGBA", (cote + 2 * pad, cote + 2 * pad))
    ombre = Image.new("RGBA", toile.size)
    ImageDraw.Draw(ombre).ellipse((pad, pad + 3, pad + cote, pad + cote + 3),
                                  fill=(15, 8, 0, 120))
    toile.alpha_composite(ombre.filter(ImageFilter.GaussianBlur(4)))
    d = ImageDraw.Draw(toile)
    d.ellipse((pad, pad, pad + cote, pad + cote), fill=(183, 134, 47, 255))
    d.ellipse((pad + 2, pad + 2, pad + cote - 2, pad + cote - 2),
              fill=(244, 221, 148, 255))
    d.ellipse((pad + 6, pad + 6, pad + cote - 6, pad + cote - 6),
              fill=(214, 178, 94, 255), outline=(110, 76, 20, 200))
    # La coche est DESSINÉE : Friz Quadrata n'a pas le caractère « ✓ »
    # (il sortait en carré vide).
    cx, cy = pad + cote // 2, pad + cote // 2
    coche = [(cx - 13, cy + 1), (cx - 4, cy + 10), (cx + 13, cy - 10)]
    d.line(coche, fill=(30, 70, 26, 120), width=8, joint="curve")
    d.line(coche, fill=(47, 127, 42, 255), width=5, joint="curve")
    sauver("badge_ok", toile, pad)

    # Le badge « FR » des cartes d'addons
    l, h = 46, 24
    toile = Image.new("RGBA", (l, h))
    d = ImageDraw.Draw(toile)
    d.rounded_rectangle((0, 0, l - 1, h - 1), 5, fill=(244, 228, 188, 255),
                        outline=(138, 106, 42, 255))
    tiers = (l - 10) // 3
    for i, coul in enumerate(((0, 32, 159, 255), (255, 255, 255, 255),
                              (210, 16, 52, 255))):
        d.rectangle((5 + i * tiers, h - 7, 5 + (i + 1) * tiers, h - 4),
                    fill=coul)
    texte_grave(toile, (l // 2, 10), "FR", police("FRIZQT__.TTF", 13),
                ENCRE, relief=False)
    sauver("badge_fr", toile)


def fabriquer_barres():
    l, h = M["BARRE_W"], M["BARRE_H"]
    toile = degrade_vertical(l, h, (58, 44, 16, 255), (90, 68, 28, 255))
    masque = coin_arrondi(l, h, h // 2, (255, 255, 255, 255))
    creuse = Image.new("RGBA", (l, h))
    creuse.paste(toile, (0, 0), masque)
    d = ImageDraw.Draw(creuse)
    d.rounded_rectangle((0, 0, l - 1, h - 1), h // 2,
                        outline=(125, 85, 24, 255))
    d.line([(h // 2, 1), (l - h // 2, 1)], fill=(20, 12, 4, 160))
    sauver("barre_creuse", creuse)

    lb, hb = l - 4, h - 4
    bande_or = degrade_vertical(lb, hb, (248, 230, 164, 255),
                                (169, 120, 31, 255))
    rayures = Image.new("RGBA", (lb, hb))
    dr = ImageDraw.Draw(rayures)
    for x in range(-hb, lb + hb, 16):
        dr.polygon([(x, hb), (x + hb, 0), (x + hb + 8, 0), (x + 8, hb)],
                   fill=(255, 255, 255, 42))
    bande_or.alpha_composite(rayures)
    ImageDraw.Draw(bande_or).line([(0, 0), (lb, 0)],
                                  fill=(255, 248, 220, 150))
    masque = coin_arrondi(lb, hb, hb // 2, (255, 255, 255, 255))
    bande = Image.new("RGBA", (lb, hb))
    bande.paste(bande_or, (0, 0), masque)
    sauver("barre_bande", bande)


# --------------------------------------------------------------------------- #
# Lot 12 — plaques, pastilles, titres, case à cocher, filet, défilement
# --------------------------------------------------------------------------- #
def fabriquer_plaques():
    """Les plaques d'infobulle sous les textes posés sur le bois (règle
    n° 1 de la passe UX) : l'audit du 26/07 a mesuré 1,4 à 3,2:1 pour toute
    encre posée directement sur la texture, 6,7 à 10 sur panneau."""
    sauver("plaque_verdict", plaque_infobulle(M["CW"], M["PLAQUE_VERDICT_H"]))
    sauver("plaque_outils", plaque_infobulle(M["CW"], M["PLAQUE_OUTILS_H"]))
    sauver("plaque_note", plaque_infobulle(M["CW"], M["PLAQUE_NOTE_H"]))


def fabriquer_pastilles():
    """Les billes d'état du jeu (COMMON/Indicator-*) : la pastille double le
    verdict — et comme les quatre ont la même forme, le TEXTE porte toujours
    le sens (« la forme avant la couleur » : ici, la forme est la phrase)."""
    for nom, fichier in (("pastille_verte", "Indicator-Green.PNG"),
                         ("pastille_jaune", "Indicator-Yellow.PNG"),
                         ("pastille_rouge", "Indicator-Red.PNG"),
                         ("pastille_grise", "Indicator-Gray.PNG")):
        im = texture("COMMON", fichier)
        im = im.crop(im.getbbox())
        sauver(nom, im.resize((22, 22), Image.LANCZOS))


TITRES_VUES = (
    ("accueil", "Accueil"),
    ("traduction", "Traduction"),
    ("voix", "Voix françaises"),
    ("addons", "Addons"),
    ("contribuer", "Contribuer"),
)


def fabriquer_titres():
    """Titres de vue : or vif + contour NOIR, le traitement du jeu lui-même
    (arbitrage de Dan du 28/07 — pas de plaque sous les titres, elle
    recouvrait le fronton gravé). En encre sur le bois ils mesuraient
    3,2:1 ; l'or vif contouré passe au-dessus de 12:1."""
    fonte = police("MORPHEUS.TTF", 30)
    ep = 2
    for vue, libelle in TITRES_VUES:
        x0, y0, x1, y1 = fonte.getbbox(libelle, stroke_width=ep)
        toile = Image.new("RGBA", (x1 - x0 + 6, y1 - y0 + 6))
        d = ImageDraw.Draw(toile)
        # Une ombre portée douce pour décoller du bois, puis l'or contouré.
        d.text((3 - x0 + 1, 3 - y0 + 2), libelle, font=fonte,
               fill=(0, 0, 0, 130), stroke_width=ep,
               stroke_fill=(0, 0, 0, 130))
        d.text((3 - x0, 3 - y0), libelle, font=fonte, fill=OR_VIF,
               stroke_width=ep, stroke_fill=(0, 0, 0, 255))
        sauver("titre_" + vue, toile)


SOUSTITRES = (
    ("soustitre_voix",
     "Les cinématiques et les personnages parlent français — les 14 442 "
     "répliques d'époque, retrouvées et remises en place."),
    ("soustitre_addons",
     "Traduits à 100 %, entretenus et distribués par AscensionFR — toute "
     "la chaîne est de chez nous."),
)


def fabriquer_soustitres():
    """Les sous-titres de vue posés sur le BOIS : en encre ils mesuraient
    ~3:1. Ils sont statiques, donc cuits — beige vif + contour sombre, le
    traitement que le jeu donne à ses textes sur texture."""
    fonte = police("FRIZQT__.TTF", 15)
    interligne = 21
    for nom, texte in SOUSTITRES:
        mots, lignes, courante = texte.split(), [], ""
        for mot in mots:
            essai = (courante + " " + mot).strip()
            if fonte.getlength(essai) <= M["CW"] - 6:
                courante = essai
            else:
                lignes.append(courante)
                courante = mot
        lignes.append(courante)
        h = 6 + interligne * len(lignes)
        toile = Image.new("RGBA", (M["CW"], h))
        d = ImageDraw.Draw(toile)
        for i, ligne in enumerate(lignes):
            d.text((3, 3 + i * interligne), ligne, font=fonte,
                   fill=BEIGE_VIF, stroke_width=2,
                   stroke_fill=(30, 18, 6, 255))
        sauver(nom, toile)


def fabriquer_cases():
    """La vraie case à cocher du jeu (Buttons/UI-CheckBox-Up + -Check) pour
    « envoi automatique » : une décision qui commande un envoi de données ne
    doit pas ressembler à une note de bas de page."""
    cote = 26
    vide = texture("Buttons", "UI-CheckBox-Up.PNG")
    sauver("case_vide", vide.resize((cote, cote), Image.LANCZOS))
    cochee = vide.copy()
    cochee.alpha_composite(texture("Buttons", "UI-CheckBox-Check.PNG"))
    sauver("case_cochee", cochee.resize((cote, cote), Image.LANCZOS))


def fabriquer_filet():
    """Le filet séparateur des infobulles (COMMON/UI-TooltipDivider), sous
    le titre des Dernières nouvelles."""
    im = texture("COMMON", "UI-TooltipDivider.PNG")
    sauver("filet_nouvelles", im.resize((M["CW"] - 48, 8), Image.LANCZOS))


def fabriquer_defilement():
    """Flèches et pouce du défilement du catalogue (Buttons/UI-ScrollBar-*) :
    le plafond de `catalogue[:6]` saute — un 7ᵉ addon se défile au lieu de
    disparaître sans un mot."""
    for nom, fichier in (
            ("fleche_haut", "UI-ScrollBar-ScrollUpButton-Up.PNG"),
            ("fleche_haut_off", "UI-ScrollBar-ScrollUpButton-Disabled.PNG"),
            ("fleche_bas", "UI-ScrollBar-ScrollDownButton-Up.PNG"),
            ("fleche_bas_off", "UI-ScrollBar-ScrollDownButton-Disabled.PNG")):
        im = texture("Buttons", fichier)
        im = im.crop(im.getbbox())
        sauver(nom, im.resize((22, 22), Image.LANCZOS))
    knob = texture("Buttons", "UI-ScrollBar-Knob.PNG")
    knob = knob.crop(knob.getbbox())
    sauver("pouce_defilement", knob.resize((18, 24), Image.LANCZOS))


# Barre d'état : fond crème OPAQUE (retouche de Dan du 23/07 — le voile
# translucide se noyait dans le parchemin). La tonalité vit dans le liseré,
# la pastille et la couleur du texte, jamais dans le fond.
TONS = {
    "neutre": ((245, 236, 212, 255), (138, 106, 42, 255),
               (122, 94, 48, 255)),
    "alerte": ((248, 233, 198, 255), (170, 120, 25, 255),
               (184, 120, 31, 255)),
    "erreur": ((247, 226, 214, 255), (150, 45, 22, 255),
               (178, 59, 31, 255)),
    "succes": ((233, 240, 214, 255), (70, 120, 50, 255),
               (47, 127, 42, 255)),
}


def fabriquer_etats():
    l, h = M["ETAT_W"], M["H_ETAT"]
    for ton, (fond, bord, point) in TONS.items():
        toile = Image.new("RGBA", (l, h))
        d = ImageDraw.Draw(toile)
        d.rounded_rectangle((0, 1, l - 1, h - 1), 7, fill=(60, 40, 12, 90))
        d.rounded_rectangle((0, 0, l - 1, h - 2), 7, fill=fond,
                            outline=bord)
        d.line([(8, h - 3), (l - 8, h - 3)], fill=(120, 90, 40, 40))
        d.line([(8, 1), (l - 8, 1)], fill=(255, 250, 235, 180))
        d.ellipse((12, h // 2 - 5, 22, h // 2 + 5), fill=point,
                  outline=(60, 35, 10, 120))
        sauver("etat_" + ton, toile)


# --------------------------------------------------------------------------- #
# Icônes des cartes d'addons
# --------------------------------------------------------------------------- #
# ------------------------------------------------------------------------- #
# Boutons Discord / café : les MÊMES habillages que le Compagnon v2
# (demande de Dan, 23/07), remis à l'échelle de la barre latérale.
# ------------------------------------------------------------------------- #
V2UI = os.path.join(ICI, "assets", "v2ui")


def fabriquer_boutons_lien():
    for nom in ("btn_discord", "btn_discord_survol",
                "btn_cafe", "btn_cafe_survol"):
        im = Image.open(os.path.join(V2UI, nom + ".png")).convert("RGBA")
        # 44px (demande de Dan 24/07 : ils étaient trop peu lisibles à 32).
        # Toujours côte à côte : discord 77 + café 120 + 2 = 199 <= 210 (SB_W).
        h = 44
        l = round(im.width * h / im.height)
        sauver(nom, im.resize((l, h), Image.LANCZOS))


CARTE_ICONES = {
    "ascensionfr_confort": "INV_Misc_PocketWatch_01.PNG",
    "ascensionfr_equipement": "INV_Chest_Plate06.PNG",
    "dragonui": "INV_Misc_Head_Dragon_01.PNG",
    "dbm": "INV_Misc_Bone_HumanSkull_01.PNG",
    "adibags": "INV_Misc_Bag_10.PNG",
    "lootcollector": "INV_Box_02.PNG",
}


def fabriquer_icones_cartes():
    for ident, icone in CARTE_ICONES.items():
        sauver("carte_ic_" + ident, icone_encadree(icone, 56))


# --------------------------------------------------------------------------- #
def main():
    os.makedirs(SORTIE, exist_ok=True)
    os.makedirs(os.path.join(SORTIE, "fonts"), exist_ok=True)
    for nom in ("MORPHEUS.TTF", "FRIZQT__.TTF"):
        cible = os.path.join(SORTIE, "fonts", nom)
        try:
            shutil.copy2(os.path.join(POLICES, nom), cible)
        except PermissionError:
            # Un Hub ouvert tient la police (chargée FR_PRIVATE). Elle ne
            # change jamais : si elle est déjà là, on continue.
            if not os.path.isfile(cible):
                raise
    fabriquer_fond()
    fabriquer_navigation()
    fabriquer_boutons()
    fabriquer_panneaux()
    fabriquer_badges()
    fabriquer_barres()
    fabriquer_etats()
    fabriquer_plaques()
    fabriquer_pastilles()
    fabriquer_titres()
    fabriquer_soustitres()
    fabriquer_cases()
    fabriquer_filet()
    fabriquer_defilement()
    fabriquer_icones_cartes()
    fabriquer_boutons_lien()
    # FUSION PRÉSERVANTE (28/07/2026). L'ancien manifeste peut porter des
    # décors faits À PART (carte_ic_ascensionfr_peche, carte_ic_gbg n'ont
    # aucune recette ici) : réécrire le manifeste de zéro les faisait
    # disparaître — et une icône hors manifeste n'est plus posée du tout.
    # On garde donc toute entrée ancienne dont le PNG existe encore.
    chemin_manifeste = os.path.join(SORTIE, "decor_hub.json")
    if os.path.exists(chemin_manifeste):
        with open(chemin_manifeste, encoding="utf-8") as f:
            ancien = json.load(f)
        for nom, fiche in ancien.items():
            if nom not in MANIFESTE and os.path.isfile(
                    os.path.join(SORTIE, nom + ".png")):
                MANIFESTE[nom] = fiche
                print("  %-26s conservé de l'ancien manifeste" % nom)
    with open(chemin_manifeste, "w", encoding="utf-8") as f:
        json.dump(MANIFESTE, f, ensure_ascii=False, indent=1)
    print("Décors du Hub écrits dans", SORTIE)


if __name__ == "__main__":
    main()
