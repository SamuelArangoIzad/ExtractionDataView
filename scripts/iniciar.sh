#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/streamlit ]]; then echo 'Primero ejecuta ./scripts/instalar_kali.sh'; exit 1; fi
exec .venv/bin/streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
