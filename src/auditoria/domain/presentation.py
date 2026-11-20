"""Equivalencias conservadoras de una cantidad y su unidad; no infiere multipacks."""
from decimal import Decimal
import re
import unicodedata


UNITS = {
    'ml': ('volumen', 1), 'mililitro': ('volumen', 1), 'mililitros': ('volumen', 1),
    'l': ('volumen', 1000), 'litro': ('volumen', 1000), 'litros': ('volumen', 1000),
    'mg': ('masa', 1), 'miligramo': ('masa', 1), 'miligramos': ('masa', 1),
    'g': ('masa', 1000), 'gramo': ('masa', 1000), 'gramos': ('masa', 1000),
    'kg': ('masa', 1000000), 'kilogramo': ('masa', 1000000), 'kilogramos': ('masa', 1000000),
    'unidad': ('unidad', 1), 'unidades': ('unidad', 1), 'und': ('unidad', 1), 'uds': ('unidad', 1),
    'tableta': ('tableta', 1), 'tabletas': ('tableta', 1),
    'capsula': ('capsula', 1), 'capsulas': ('capsula', 1),
}


def presentation_key(value):
    text = ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower())
                   if not unicodedata.combining(c)).strip()
    match = re.fullmatch(r'(\d+(?:[.,]\d+)?)\s*([a-z]+)\.?', text)
    if match and match[2] in UNITS:
        unit, factor = UNITS[match[2]]
        return unit, Decimal(match[1].replace(',', '.')) * factor
    # Mantener signos y decimales: 1.5 no equivale a 15 ni 2 x 50 a 100.
    return 'texto', ' '.join(text.split())
