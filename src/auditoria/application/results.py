"""Vista breve de incoherencias para pantalla y reporte, sin alterar la auditoría."""
from decimal import Decimal, InvalidOperation


RESULT_COLUMNS = ('Producto', 'EAN', 'Página', 'Campo', 'Descripción de la incoherencia')
VISIBLE_STATUSES = frozenset(('DIFERENCIA', 'NO_EN_BASE', 'VIGENCIA_VENCIDA'))
FIELD_NAMES = {
    'DESCRIPCION': 'Nombre', 'MARCA': 'Marca', 'PRESENTACION': 'Presentación / unidad',
    'PRECIO_COP': 'Precio', 'DESCUENTO_PCT': 'Descuento',
    'VIGENCIA_INICIO': 'Inicio de vigencia', 'VIGENCIA_FIN': 'Fin de vigencia',
    'VIGENCIA': 'Vigencia', 'EAN': 'Identificación del producto',
}


def display_value(value, field):
    text = str(value).strip() if value is not None else ''
    if text in ('', 'None'):
        return 'sin dato'
    if field in ('PRECIO_COP', 'DESCUENTO_PCT'):
        try:
            number = Decimal(text)
            if number.is_finite():
                formatted = format(number, ',f')
                if '.' in formatted:
                    formatted = formatted.rstrip('0').rstrip('.')
                formatted = formatted.translate(str.maketrans({',': '.', '.': ','}))
                return f'${formatted} COP' if field == 'PRECIO_COP' else f'{formatted}%'
        except InvalidOperation:
            pass
    return f'«{text}»'


def discrepancy_rows(findings):
    rows = []
    for issue in findings:
        if issue.status not in VISIBLE_STATUSES:
            continue
        field = FIELD_NAMES.get(issue.field, issue.field)
        if issue.status == 'NO_EN_BASE':
            description = f'El EAN {issue.ean} de la revista no se encuentra en Excel. Verifique el código y la hoja del catálogo seleccionada.'
        elif issue.status == 'VIGENCIA_VENCIDA':
            description = f'La vigencia publicada terminó el {issue.magazine_value}. {issue.database_value}. Revise las fechas de la promoción antes de publicar.'
        else:
            magazine = display_value(issue.magazine_value, issue.field)
            database = display_value(issue.database_value, issue.field)
            description = f'{field}: en la revista figura {magazine}; en Excel figura {database}. Revise este campo antes de publicar.'
        rows.append(dict(zip(RESULT_COLUMNS, (
            issue.product or 'Producto sin nombre', issue.ean, issue.page, field, description))))
    return rows


def pending_review_count(findings):
    # La ausencia de datos o un EAN dudoso no demuestra una discrepancia comercial.
    return sum(i.status not in VISIBLE_STATUSES and i.status != 'SOLO_EN_BASE' for i in findings)
