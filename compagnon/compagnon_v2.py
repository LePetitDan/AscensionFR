# -*- coding: utf-8 -*-
"""
Ascension FR — Compagnon, version 2
===================================
Point d'entrée de la nouvelle interface (maquette Claude Design v2).
La logique vient de `compagnon.py` (inchangé), l'habillage de
`interface_v2.py`, les décors d'`assets/v2ui/`.

Usage :
    python compagnon_v2.py                  # utilisation normale
    python compagnon_v2.py --demo maj,attente
        # mode capture d'écran : force un état (voir interface_v2.ETATS_TRAD
        # et ETATS_CONTRIB), sans réseau ni lecture de sauvegarde.
    python compagnon_v2.py --demo ajour,attente,jeuferme,diag
        # les drapeaux v2.1 (interface_v2.DRAPEAUX_DEMO) s'ajoutent après :
        # jeuferme (bandeau), diag (panneau), note (patch-note),
        # propose (dossier détecté), compteur (compteur de contribution).
"""
import sys

import interface_v2


def principal():
    demo = None
    args = sys.argv[1:]
    if "--demo" in args:
        i = args.index("--demo")
        valeur = args[i + 1] if i + 1 < len(args) else "ajour,rien"
        morceaux = valeur.split(",")
        trans = morceaux[0] if morceaux and morceaux[0] \
            in interface_v2.ETATS_TRAD else "ajour"
        contrib = morceaux[1] if len(morceaux) > 1 and morceaux[1] \
            in interface_v2.ETATS_CONTRIB else "rien"
        drapeaux = frozenset(m for m in morceaux[2:]
                             if m in interface_v2.DRAPEAUX_DEMO)
        demo = (trans, contrib, drapeaux)
    interface_v2.lancer(demo)


if __name__ == "__main__":
    principal()
