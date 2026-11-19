"""Reglas deterministas de conciliación; no generan ni suponen datos."""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from .models import Difference, Product
from .validity import evaluate_validity, today_bogota


def normalize_code(value):
    # Nunca convertir EAN a entero: perdería ceros iniciales.
    raw = str(value or '').strip().replace(' ', '')
    return raw[:-2] if raw.endswith('.0') and raw[:-2].isdigit() else raw


def normalize_text(value):
    v = unicodedata.normalize('NFKD', str(value or '').lower())
    v = ''.join(x for x in v if not unicodedata.combining(x))
    return ' '.join(re.findall(r'[a-z0-9]+', v))


def valid_gtin(value):
    v = normalize_code(value)
    if len(v) not in (8, 12, 13, 14) or not v.isdigit():
        return False
    digits = [int(x) for x in v]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - s % 10) % 10 == digits[-1]


def audit(magazine: list[Product], database: list[Product], price_tolerance: int = 0,
          name_min_similarity: float = 0.82, as_of=None, edition_year=None) -> list[Difference]:
    """Devuelve diferencias auditables; empareja SOLO por EAN exacto no vacío.

    No relaciona por semejanza automáticamente para evitar errores de producto.
    Los registros sin código o con duplicados se envían a revisión.
    """
    output = []
    as_of = as_of if as_of is not None else today_bogota()
    lookup = defaultdict(list)
    for product in database:
        code = normalize_code(product.ean)
        if code:
            lookup[code].append(product)
    seen = set()
    for product in magazine:
        code = normalize_code(product.ean)
        ev = f'PDF página {product.page}' if product.page else (product.source or 'Revisión manual')
        def add(status, field, pm='', db='', severity='MEDIA'):
            output.append(Difference(status, code, '', field, str(pm), str(db), product.page,
                                     product.name, ev, severity))
        validity = evaluate_validity(product, as_of, edition_year)
        if validity.not_expired is None:
            add('REVISAR_VIGENCIA', 'VIGENCIA', product.validity_text, validity.detail)
        elif not validity.not_expired:
            add('VIGENCIA_VENCIDA', 'VIGENCIA', validity.end.isoformat(),
                f'Fecha de evaluación: {as_of.isoformat()}', 'ALTA')
        if not code or not code.isdigit() or len(code) not in (8, 12, 13, 14):
            add('REVISAR_IDENTIFICACION', 'EAN', code, '', 'ALTA')
            continue
        if not valid_gtin(code):
            add('REVISAR_EAN', 'EAN', code, 'GTIN con dígito verificador inválido', 'ALTA')
        candidates = lookup.get(code, [])
        if len(candidates) > 1:
            add('EAN_DUPLICADO_BASE', 'EAN', code, f'{len(candidates)} registros', 'ALTA')
            continue
        if not candidates:
            add('NO_EN_BASE', 'EAN', code, 'No encontrado', 'ALTA')
            continue
        dbp = candidates[0]
        seen.add(code)
        def diff(field, a, b, severity='MEDIA'):
            output.append(Difference('DIFERENCIA', code, dbp.sku, field, str(a), str(b),
                                     product.page, product.name, ev, severity))
        base_validity = evaluate_validity(dbp, as_of, edition_year)
        if validity.not_expired is not None and base_validity.not_expired is not None:
            for field, a, b in [('VIGENCIA_INICIO', validity.start, base_validity.start),
                                ('VIGENCIA_FIN', validity.end, base_validity.end)]:
                if a != b:
                    diff(field, a, b)
        elif dbp.validity_text or dbp.valid_from or dbp.valid_until:
            if base_validity.not_expired is None:
                add('REVISAR_VIGENCIA_BASE', 'VIGENCIA', '', base_validity.detail)
        if normalize_text(product.brand) != normalize_text(dbp.brand):
            diff('MARCA', product.brand, dbp.brand)
        if product.price is not None and dbp.price is not None:
            if abs(int(product.price) - int(dbp.price)) > price_tolerance:
                diff('PRECIO_COP', product.price, dbp.price, 'ALTA')
        elif product.price is not None or dbp.price is not None:
            diff('PRECIO_COP_SIN_DATO', product.price, dbp.price)
        if product.discount is not None and dbp.discount is not None:
            if abs(float(product.discount) - float(dbp.discount)) > 0.001:
                diff('DESCUENTO_PCT', product.discount, dbp.discount)
        elif product.discount is not None or dbp.discount is not None:
            diff('DESCUENTO_SIN_DATO', product.discount, dbp.discount)
        if product.presentation and dbp.presentation and normalize_text(product.presentation) != normalize_text(dbp.presentation):
            diff('PRESENTACION', product.presentation, dbp.presentation)
        if product.name and dbp.name:
            ratio = SequenceMatcher(None, normalize_text(product.name), normalize_text(dbp.name)).ratio()
            if ratio < name_min_similarity:
                diff('DESCRIPCION', product.name, dbp.name)
    for product in database:
        code = normalize_code(product.ean)
        if code and code not in seen and not any(normalize_code(p.ean) == code for p in magazine):
            output.append(Difference('SOLO_EN_BASE', code, product.sku, 'EAN', 'No publicado en páginas procesadas',
                                     code, None, product.name, 'Cobertura de PDF procesado', 'BAJA'))
    return output
