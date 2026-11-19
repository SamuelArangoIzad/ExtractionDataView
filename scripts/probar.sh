#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
