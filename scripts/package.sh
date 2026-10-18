#!/usr/bin/env bash
# Compila el frontend y crea out/konkr-toolbox-<versión>.zip, listo para
# Decky → Desarrollador → Instalar plugin desde ZIP.
set -euo pipefail
cd "$(dirname "$0")/.."
VER=$(python3 -c "import json; print(json.load(open('plugin.json'))['version'])")
pnpm install --frozen-lockfile
pnpm build
rm -rf out/konkr-toolbox && mkdir -p out/konkr-toolbox/dist
cp plugin.json package.json main.py LICENSE README.md out/konkr-toolbox/
cp -r py_modules out/konkr-toolbox/ && find out/konkr-toolbox -name __pycache__ -prune -exec rm -rf {} +
cp dist/index.js out/konkr-toolbox/dist/
(cd out && rm -f "konkr-toolbox-$VER.zip" && zip -qr "konkr-toolbox-$VER.zip" konkr-toolbox)
echo "out/konkr-toolbox-$VER.zip"
