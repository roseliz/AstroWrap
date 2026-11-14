#!/usr/bin/env bash
# Point d'entrée du module (appelé par ./pipeline run astrobiology_habitability_caves [options]).
# Options : --help, ou voir README.md.
set -euo pipefail
MODULE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$MODULE/../.."          # racine du dépôt
exec python "$MODULE/scripts/pretraitement.py" "$@"
