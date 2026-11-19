#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
echo 'Instalando dependencias del sistema (requiere sudo)...'
sudo apt update
sudo apt install -y python3 python3-venv python3-pip tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -e .
echo 'Instalación completada. Ejecuta: ./scripts/iniciar.sh'
