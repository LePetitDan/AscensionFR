#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Lance le Compagnon AscensionFR sous Linux, depuis les sources.
#
# Sous Windows, les joueurs utilisent l'exe de release. Sous Linux (le jeu
# tourne alors via un runner Wine/Proton — Faugus, Lutris, Steam Proton…), on
# lance directement le Python. Ce script crée au besoin un environnement local
# (.venv) et installe les dépendances : au 1er lancement il prépare tout, aux
# suivants il démarre instantanément.
#
# Usage :  ./lancer-linux.sh        (depuis n'importe où)
# ---------------------------------------------------------------------------
set -euo pipefail

ICI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ICI/.venv"

# 1. Seul prérequis SYSTÈME (non installable par pip) : Tk.
if ! python3 -c "import tkinter" >/dev/null 2>&1; then
  echo "⚠  Le module système « tkinter » manque. Installe-le puis relance :"
  echo "     Debian/Ubuntu/Pop!_OS : sudo apt install python3-tk"
  echo "     Fedora                : sudo dnf install python3-tkinter"
  echo "     Arch                  : sudo pacman -S tk"
  exit 1
fi

# 2. Environnement Python local + dépendances pip (idempotent).
#    Volontairement SANS --system-site-packages : pip fournit alors un Pillow
#    complet (avec ImageTk), là où le Pillow système en est parfois dépourvu.
if [ ! -x "$VENV/bin/python" ]; then
  echo "→ Premier lancement : préparation de l'environnement Python…"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r "$ICI/requirements.txt"
  echo "→ Prêt."
fi

# 3. Lancement du Compagnon.
exec "$VENV/bin/python" "$ICI/compagnon.py" "$@"
