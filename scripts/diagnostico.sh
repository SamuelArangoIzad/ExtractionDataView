#!/usr/bin/env bash
set -u
cd "$(dirname "$0")/.."
echo '=== PYTHON ==='
python3 --version
python3 -m venv --help >/dev/null && echo 'venv: disponible'
echo '=== TESSERACT ==='
command -v tesseract || true
tesseract --list-langs 2>&1 || true
echo '=== PAQUETES ==='
if [[ -x .venv/bin/python ]]; then
 .venv/bin/python -m pip show streamlit python-calamine PyMuPDF pytesseract Pillow XlsxWriter 2>/dev/null | grep -E '^(Name|Version):' || true
else echo 'Ambiente virtual no creado'; fi
echo '=== ARCHIVOS DEMO ==='
ls -lh data/Revista_Essentials.pdf data/Base_Datos_Demo.xlsx
