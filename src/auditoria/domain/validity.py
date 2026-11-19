"""Vigencia no vencida: fecha final inclusiva, independiente del catálogo."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import re
import unicodedata


def today_bogota():
    # Colombia usa UTC-5; evita depender de la zona horaria del servidor.
    return datetime.now(timezone(timedelta(hours=-5))).date()


MONTHS = {name: i for i, name in enumerate(
    'enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre'.split(), 1)}
MONTHS['setiembre'] = 9
MONTH_PATTERN = '|'.join(MONTHS)
RANGE_RE = re.compile(
    rf'(?:del?\s+)?(?P<d1>\d{{1,2}})(?:\s+de\s+(?P<m1>{MONTH_PATTERN}))?'
    rf'(?:\s+(?:de\s+)?(?P<y1>\d{{4}}))?\s+(?:al|a|hasta(?:\s+el)?)\s+'
    rf'(?P<d2>\d{{1,2}})\s+de\s+(?P<m2>{MONTH_PATTERN})'
    rf'(?:\s+(?:de\s+)?(?P<y2>\d{{4}}))?')


def parse_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError(f'Fecha no válida: {value}. Use AAAA-MM-DD o DD/MM/AAAA.')


def parse_range(text, edition_year=None):
    value = ''.join(c for c in unicodedata.normalize('NFKD', str(text).lower())
                    if not unicodedata.combining(c)).strip().rstrip('.')
    value = re.sub(r'^(?:vigencia|valido|valida|vigente)\s*:?\s*', '', value)
    match = RANGE_RE.fullmatch(value)
    if not match:
        raise ValueError('Rango no reconocido; confirme fechas de inicio y fin.')
    g = match.groupdict()
    m2 = MONTHS[g['m2']]
    m1 = MONTHS[g['m1']] if g['m1'] else m2
    rollover = m1 > m2
    y1, y2 = g['y1'], g['y2']
    if y1:
        y1 = int(y1)
        y2 = int(y2) if y2 else y1 + rollover
    elif y2:
        y2 = int(y2)
        y1 = y2 - rollover
    elif edition_year is not None:
        y1 = int(edition_year)
        y2 = y1 + rollover
    else:
        raise ValueError('Falta el año de la edición; no se supone el año actual.')
    start, end = date(y1, m1, int(g['d1'])), date(y2, m2, int(g['d2']))
    if end < start:
        raise ValueError('El fin de vigencia es anterior al inicio.')
    return start, end


@dataclass(frozen=True)
class Validity:
    start: date | None
    end: date | None
    not_expired: bool | None
    status: str
    checked_on: date
    detail: str = ''


def evaluate_validity(product, as_of=None, edition_year=None):
    checked_on = as_of if as_of is not None else today_bogota()
    try:
        start, end = parse_date(product.valid_from), parse_date(product.valid_until)
        if start is not None or end is not None:
            # Fechas confirmadas manualmente prevalecen sobre la transcripción OCR.
            if start is None or end is None:
                raise ValueError('Complete ambas fechas de vigencia.')
        elif product.validity_text:
            start, end = parse_range(product.validity_text, edition_year)
        else:
            raise ValueError('No hay vigencia informada.')
        if end < start:
            raise ValueError('El fin de vigencia es anterior al inicio.')
    except (ValueError, TypeError, OverflowError) as error:
        return Validity(None, None, None, 'REVISAR', checked_on, str(error))
    status = 'VENCIDA' if checked_on > end else ('FUTURA' if checked_on < start else 'VIGENTE')
    return Validity(start, end, checked_on <= end, status, checked_on)
