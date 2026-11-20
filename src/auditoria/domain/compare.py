"""Reglas deterministas de conciliación; no generan ni suponen datos."""
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from decimal import Decimal
from .models import Difference, Product
from .validity import evaluate_validity, today_bogota
from .rules import AuditRules
from .numbers import parse_number
from .presentation import presentation_key


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
    if len(v) not in (8, 12, 13, 14) or not re.fullmatch(r'[0-9]+', v):
        return False
    digits = [int(x) for x in v]
    s = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits[:-1])))
    return (10 - s % 10) % 10 == digits[-1]


class ExactEanIndex:
    """Índice de solo lectura: conserva duplicados y nunca busca por semejanza."""
    def __init__(self, products):
        self._rows = defaultdict(list)
        for product in products:
            code = normalize_code(product.ean)
            if code:
                self._rows[code].append(product)

    def find(self, ean):
        return tuple(self._rows.get(normalize_code(ean), ()))


def audit(magazine: list[Product], database: list[Product], price_tolerance: int = 0,
          name_min_similarity: float = 0.82, as_of=None, edition_year=None,
          rules: AuditRules | None = None) -> list[Difference]:
    """Devuelve diferencias auditables; empareja SOLO por EAN exacto no vacío.

    No relaciona por semejanza automáticamente para evitar errores de producto.
    Los registros sin código o con duplicados se envían a revisión.
    """
    output = []
    rules = rules or AuditRules(price_tolerance=price_tolerance, name_min_similarity=name_min_similarity)
    as_of = as_of if as_of is not None else today_bogota()
    lookup = ExactEanIndex(database)
    magazine_codes = {normalize_code(p.ean) for p in magazine}
    for product in magazine:
        code = normalize_code(product.ean)
        ev = f'PDF página {product.page}' if product.page else (product.source or 'Revisión manual')
        def add(status, field, pm='', db='', severity='MEDIA'):
            output.append(Difference(status, code, '', field, str(pm), str(db), product.page,
                                     product.name, ev, severity))
        validity = evaluate_validity(product, as_of, edition_year)
        if 'VIGENCIA' in rules.fields:
            has_dates = bool(product.validity_text or product.valid_from or product.valid_until)
            if validity.not_expired is None and (rules.flag_missing or has_dates):
                add('REVISAR_VIGENCIA', 'VIGENCIA', product.validity_text, validity.detail)
            elif validity.not_expired is False:
                add('VIGENCIA_VENCIDA', 'VIGENCIA', validity.end.isoformat(),
                    f'Fecha de evaluación: {as_of.isoformat()}', 'ALTA')
        if not re.fullmatch(r'[0-9]+', code) or len(code) not in (8, 12, 13, 14):
            add('REVISAR_IDENTIFICACION', 'EAN', code, '', 'ALTA')
            continue
        valid_code = valid_gtin(code)
        if not valid_code:
            add('REVISAR_EAN', 'EAN', code, 'GTIN con dígito verificador inválido', 'ALTA')
        candidates = lookup.find(code)
        if len(candidates) > 1:
            add('EAN_DUPLICADO_BASE', 'EAN', code, f'{len(candidates)} registros', 'ALTA')
            continue
        if not candidates:
            add('NO_EN_BASE', 'EAN', code, 'No encontrado', 'ALTA')
            continue
        if rules.require_valid_gtin and not valid_code:
            continue
        dbp = candidates[0]
        def diff(field, a, b, severity='MEDIA'):
            output.append(Difference('DIFERENCIA', code, dbp.sku, field, str(a), str(b),
                                     product.page, product.name, ev, severity))
        if 'VIGENCIA' in rules.fields:
            base_validity = evaluate_validity(dbp, as_of, edition_year)
            if validity.not_expired is not None and base_validity.not_expired is not None:
                for field, a, b in [('VIGENCIA_INICIO', validity.start, base_validity.start),
                                    ('VIGENCIA_FIN', validity.end, base_validity.end)]:
                    if a != b:
                        diff(field, a, b)
            elif base_validity.not_expired is None and (rules.flag_missing or dbp.validity_text or dbp.valid_from or dbp.valid_until):
                add('REVISAR_VIGENCIA_BASE', 'VIGENCIA', '', base_validity.detail)

        def missing(field, a, b):
            absent = a is None or b is None or str(a).strip() == '' or str(b).strip() == ''
            if absent and rules.flag_missing:
                add('REVISAR_CAMPO_FALTANTE', field, a if a is not None else '', b if b is not None else '')
            return absent

        for field, a, b in [('DESCRIPCION', product.name, dbp.name),
                            ('MARCA', product.brand, dbp.brand),
                            ('PRESENTACION', product.presentation, dbp.presentation)]:
            if field not in rules.fields or missing(field, a, b):
                continue
            if field == 'DESCRIPCION':
                na, nb = normalize_text(a), normalize_text(b)
                # Una similitud alta no debe ocultar cambios de dosis o cantidad.
                numbers_a = re.findall(r'\d+(?:[.,]\d+)?', str(a))
                numbers_b = re.findall(r'\d+(?:[.,]\d+)?', str(b))
                mismatch = (SequenceMatcher(None, na, nb).ratio() < rules.name_min_similarity
                            or [Decimal(n.replace(',', '.')) for n in numbers_a] !=
                               [Decimal(n.replace(',', '.')) for n in numbers_b])
            elif field == 'MARCA':
                mismatch = normalize_text(a) != normalize_text(b) if rules.normalize_brand else a.strip() != b.strip()
            else:
                mismatch = presentation_key(a) != presentation_key(b) if rules.equivalent_units else a.strip().casefold() != b.strip().casefold()
            if mismatch:
                diff(field, a, b)

        for field, a, b, tolerance, maximum in [
                ('PRECIO_COP', product.price, dbp.price, rules.price_tolerance, None),
                ('DESCUENTO_PCT', product.discount, dbp.discount, rules.discount_tolerance, 100)]:
            if field not in rules.fields:
                continue
            absent = missing(field, a, b)
            parsed = []
            invalid = False
            for value in (a, b):
                try:
                    n = parse_number(value, money=field == 'PRECIO_COP')
                    if n is not None and (n < 0 or (maximum is not None and n > maximum)):
                        raise ValueError('Fuera de rango')
                    parsed.append(n)
                except (ValueError, TypeError):
                    invalid = True
            if invalid:
                add('REVISAR_VALOR_INVALIDO', field, a, b, 'ALTA')
            elif not absent and abs(Decimal(str(parsed[0])) - Decimal(str(parsed[1]))) > Decimal(str(tolerance)):
                diff(field, a, b, 'ALTA' if field == 'PRECIO_COP' else 'MEDIA')
    for product in database:
        code = normalize_code(product.ean)
        if code and code not in magazine_codes:
            output.append(Difference('SOLO_EN_BASE', code, product.sku, 'EAN', 'No publicado en páginas procesadas',
                                     code, None, product.name, 'Cobertura de PDF procesado', 'BAJA'))
    return output
