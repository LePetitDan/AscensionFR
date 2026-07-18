# -*- coding: utf-8 -*-
"""
Parseur des caches WDB de World of Warcraft 3.3.5a (client Project Ascension).

Les fichiers .wdb sont des réponses serveur mises en cache par le client :
  - questcache.wdb      : SMSG_QUEST_QUERY_RESPONSE      (quêtes)
  - itemcache.wdb       : SMSG_ITEM_QUERY_SINGLE_RESPONSE (objets)
  - creaturecache.wdb   : SMSG_CREATURE_QUERY_RESPONSE   (créatures/PNJ)
  - npccache.wdb        : SMSG_NPC_TEXT_UPDATE           (textes de dialogue)
  - pagetextcache.wdb   : SMSG_PAGE_TEXT_QUERY_RESPONSE  (pages de livres)
  - gameobjectcache.wdb : SMSG_GAMEOBJECT_QUERY_RESPONSE (objets du monde)

Format fichier (constaté empiriquement sur le client Ascension, build 12340) :
  En-tête 24 octets : magic(4) build(4) locale(4) inconnu(4) version(4) horodatage(4)
  Puis enregistrements : id(uint32) longueur(uint32) données[longueur]
  Terminé par id=0, longueur=0.

Usage :
  python parser_wdb.py "<dossier WDB>" "<dossier de sortie>"
"""
import json
import os
import struct
import sys

HEADER_SIZE = 24

MAGICS = {
    b"TSQW": "quest",
    b"BOMW": "creature",
    b"BDIW": "item",
    b"CPNW": "npctext",
    b"XTPW": "pagetext",
    b"BOGW": "gameobject",
}


class Cursor:
    """Lecteur séquentiel sur un buffer binaire."""

    def __init__(self, data):
        self.data = data
        self.pos = 0

    def u32(self):
        v = struct.unpack_from("<I", self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self):
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def cstring(self):
        end = self.data.find(b"\x00", self.pos)
        if end == -1:
            raise ValueError("chaîne non terminée")
        raw = self.data[self.pos:end]
        self.pos = end + 1
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")

    def remaining(self):
        return len(self.data) - self.pos


def iter_records(path):
    """Itère (id, payload) sur un fichier .wdb."""
    with open(path, "rb") as f:
        header = f.read(HEADER_SIZE)
        if len(header) < HEADER_SIZE:
            return
        magic = header[0:4]
        build = struct.unpack_from("<I", header, 4)[0]
        kind = MAGICS.get(magic)
        if kind is None:
            raise ValueError(f"magic inconnu {magic!r} dans {path}")
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            rec_id, length = struct.unpack("<II", head)
            if rec_id == 0 and length == 0:
                break
            payload = f.read(length)
            if len(payload) < length:
                break
            yield rec_id, payload


# ---------------------------------------------------------------------------
# Parseurs par type d'enregistrement
# ---------------------------------------------------------------------------

def parse_quest(rec_id, payload):
    """Structure 3.3.5 : l'ID est répété en tête, puis 64 uint32, puis
    5 chaînes (titre, objectifs, description, texte de fin, texte accompli),
    puis 4 groupes d'objectifs, 6 objets requis, et 4 textes d'objectifs."""
    c = Cursor(payload)
    first = c.u32()
    if first != rec_id:
        # Pas de répétition de l'ID : on revient au début.
        c.pos = 0
    c.pos += 64 * 4  # champs numériques fixes
    title = c.cstring()
    objectives = c.cstring()
    details = c.cstring()
    end_text = c.cstring()
    completed = c.cstring()
    # 4 groupes (creatureOrGo, count, itemDrop, itemDropCount) + 6 (item, count)
    objective_texts = []
    try:
        c.pos += 4 * 16 + 6 * 8
        for _ in range(4):
            objective_texts.append(c.cstring())
    except (ValueError, struct.error):
        objective_texts = []
    out = {"Title": title}
    if objectives:
        out["Objectives"] = objectives
    if details:
        out["Details"] = details
    if end_text:
        out["EndText"] = end_text
    if completed:
        out["CompletedText"] = completed
    texts = [t for t in objective_texts if t]
    if texts:
        out["ObjectiveTexts"] = objective_texts
    return out


def parse_item(rec_id, payload):
    """Structure 3.3.5 : class, subclass, soundOverride, 4 noms, puis champs
    fixes ; la description est plus loin (position variable selon StatsCount)."""
    c = Cursor(payload)
    c.u32()  # Class
    c.u32()  # SubClass
    c.i32()  # SoundOverrideSubclass
    names = [c.cstring() for _ in range(4)]
    out = {"Name": names[0]}
    # Tentative de parcours exact jusqu'à la description.
    try:
        c.u32()  # DisplayInfoID
        c.u32()  # Quality
        c.u32()  # Flags
        c.u32()  # Flags2
        c.u32()  # BuyPrice
        c.u32()  # SellPrice
        c.u32()  # InventoryType
        c.u32()  # AllowableClass
        c.u32()  # AllowableRace
        c.u32()  # ItemLevel
        c.u32()  # RequiredLevel
        c.u32()  # RequiredSkill
        c.u32()  # RequiredSkillRank
        c.u32()  # RequiredSpell
        c.u32()  # RequiredHonorRank
        c.u32()  # RequiredCityRank
        c.u32()  # RequiredReputationFaction
        c.u32()  # RequiredReputationRank
        c.u32()  # MaxCount
        c.i32()  # Stackable
        c.u32()  # ContainerSlots
        stats_count = c.u32()
        if stats_count > 64:
            raise ValueError("StatsCount aberrant")
        for _ in range(stats_count):
            c.u32()
            c.i32()
        c.u32()  # ScalingStatDistribution
        c.u32()  # ScalingStatValue
        for _ in range(2):  # 2 types de dégâts en 3.3.5
            c.f32()
            c.f32()
            c.u32()
        for _ in range(7):  # Armure + 6 résistances
            c.u32()
        c.u32()  # Delay
        c.u32()  # AmmoType
        c.f32()  # RangedModRange
        sorts = []
        for _ in range(5):  # 5 emplacements de sorts
            spell_id = c.i32()
            declencheur = c.u32()
            c.i32()  # charges
            c.i32()  # cooldown
            c.i32()  # catégorie
            c.i32()  # cooldown de catégorie
            if spell_id > 0:
                sorts.append([spell_id, declencheur])
        c.u32()  # Bonding
        description = c.cstring()
        if description:
            out["Description"] = description
        # Les sorts attachés produisent les lignes « Use: ... » de
        # l'info-bulle : leur description, résolue par le client, ne peut
        # être traduite que si on sait QUEL sort chercher. On ne les retient
        # qu'après un parcours complet réussi : une désynchronisation du
        # curseur donnerait des identifiants fantaisistes.
        if sorts:
            out["Spells"] = sorts
    except (ValueError, struct.error, IndexError):
        out["_desc_parse_failed"] = True
    return out


def parse_creature(rec_id, payload):
    c = Cursor(payload)
    names = [c.cstring() for _ in range(4)]
    subname = c.cstring()
    icon = c.cstring()
    out = {"Name": names[0]}
    if subname:
        out["SubName"] = subname
    return out


def parse_npctext(rec_id, payload):
    """8 groupes : float proba, texte0, texte1, uint32 langue, 3x(délai, emote)."""
    c = Cursor(payload)
    texts = []
    for _ in range(8):
        if c.remaining() < 4:
            break
        c.f32()  # probabilité
        t0 = c.cstring()
        t1 = c.cstring()
        c.u32()  # langue
        for _ in range(3):
            c.u32()
            c.u32()
        if t0:
            texts.append(t0)
        if t1 and t1 != t0:
            texts.append(t1)
    return {"Texts": texts} if texts else None


def parse_pagetext(rec_id, payload):
    c = Cursor(payload)
    text = c.cstring()
    next_page = c.u32() if c.remaining() >= 4 else 0
    out = {"Text": text}
    if next_page:
        out["NextPage"] = next_page
    return out


def parse_gameobject(rec_id, payload):
    c = Cursor(payload)
    c.u32()  # type
    c.u32()  # displayId
    names = [c.cstring() for _ in range(4)]
    c.cstring()  # iconName (nom de curseur, pas à traduire)
    cast_bar = c.cstring()
    out = {"Name": names[0]}
    if cast_bar:
        out["CastBarCaption"] = cast_bar
    return out


PARSERS = {
    "quêtes": ("questcache.wdb", parse_quest, "quetes.json"),
    "objets": ("itemcache.wdb", parse_item, "objets.json"),
    "créatures": ("creaturecache.wdb", parse_creature, "creatures.json"),
    "dialogues": ("npccache.wdb", parse_npctext, "textes_pnj.json"),
    "pages": ("pagetextcache.wdb", parse_pagetext, "pages.json"),
    "objets du monde": ("gameobjectcache.wdb", parse_gameobject,
                        "objets_monde.json"),
}


def parse_dir(wdb_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    report = {}
    for kind, (filename, parser, out_name) in PARSERS.items():
        path = os.path.join(wdb_dir, filename)
        if not os.path.exists(path):
            report[kind] = "absent"
            continue
        entries, errors = {}, 0
        for rec_id, payload in iter_records(path):
            try:
                parsed = parser(rec_id, payload)
                if parsed:
                    entries[str(rec_id)] = parsed
            except Exception:
                errors += 1
        with open(os.path.join(out_dir, out_name), "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=1, sort_keys=True)
        # Ce compte est ce qu'on a LU dans les caches du jeu, c'est-à-dire tout
        # ce que le serveur a envoyé au joueur depuis le début — pas ce qui
        # vient d'être traduit. La distinction prête à confusion : la formuler
        # explicitement.
        report[kind] = f"{len(entries)}"
        if errors:
            report[kind] += f" ({errors} illisibles)"
    return report


if __name__ == "__main__":
    wdb_dir = sys.argv[1]
    out_dir = sys.argv[2]
    for kind, status in parse_dir(wdb_dir, out_dir).items():
        print(f"{kind:12s} : {status}")
