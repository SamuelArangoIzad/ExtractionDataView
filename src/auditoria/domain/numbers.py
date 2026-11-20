"""Números sin truncamiento. COP usa agrupación colombiana; descuentos en puntos %."""
from decimal import Decimal, InvalidOperation
import math
import re


def parse_number(value, *, money=False):
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError('Un booleano no es un importe ni un descuento.')
    text = str(value).strip()
    if money:
        text = re.sub(r'(?i)COP|\$', '', text).replace(' ', '')
        # 15.000 / 15.000,50 (COP). Los números nativos ya son independientes del formato.
        if isinstance(value, str) and re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+(?:,\d+)?', text):
            text = text.replace('.', '')
    else:
        text = text.removesuffix('%').strip()
    text = text.replace(',', '.')
    try:
        result = Decimal(text)
    except InvalidOperation:
        raise ValueError(f'Valor numérico no reconocido: {value}') from None
    if not result.is_finite():
        raise ValueError(f'Valor numérico no finito: {value}')
    number = float(result)
    if not math.isfinite(number):
        raise ValueError(f'Valor numérico fuera de rango: {value}')
    return number
