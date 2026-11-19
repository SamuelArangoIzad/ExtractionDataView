"""Capa de infraestructura: lectores XLSX/ODS, separada de negocio."""
from pathlib import Path
from io import BytesIO
from python_calamine import CalamineWorkbook
from ..domain.models import Product
from ..domain.compare import normalize_code


def get_sheets(file_bytes: bytes, filename: str):
    book = CalamineWorkbook.from_filelike(BytesIO(file_bytes))
    return book.sheet_names


def _load_sheet(file_bytes: bytes, filename: str, sheet_name: str):
    book = CalamineWorkbook.from_filelike(BytesIO(file_bytes))
    if sheet_name not in book.sheet_names:
        raise ValueError(f'Hoja {sheet_name} no existe. Hojas: {book.sheet_names}')
    return book.get_sheet_by_name(sheet_name).to_python()


def _pick(row, columns, *aliases):
    for name in aliases:
        ix = columns.get(name)
        if ix is not None and ix < len(row):
            value = row[ix]
            if value is not None and value != '':
                return value
    return None


def _number(v):
    if v is None or v == '':
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).replace('$', '').replace('COP', '').strip().replace(' ', '')
    s = s.replace('.', '').replace(',', '') if s.count('.') + s.count(',') == 1 and len(s.rsplit('.', 1)[-1]) == 3 else s.replace(',', '')
    try:
        return int(float(s))
    except ValueError:
        return None


def load_products(file_bytes: bytes, filename: str, sheet_name: str, mode: str) -> list[Product]:
    rows = _load_sheet(file_bytes, filename, sheet_name)
    if not rows or len(rows) < 2:
        raise ValueError('La hoja está vacía o no contiene productos.')
    columns = {str(v).strip().upper(): i for i, v in enumerate(rows[0])}
    if not any(n in columns for n in ('EAN_TEXTO', 'EAN', 'CODIGO_BARRAS', 'GTIN')):
        raise ValueError('Falta la columna EAN_TEXTO o EAN. Se requiere identificador por producto.')
    out = []
    for row in rows[1:]:
        ean = _pick(row, columns, 'EAN_TEXTO', 'EAN', 'CODIGO_BARRAS', 'GTIN')
        name = _pick(row, columns, 'PRODUCTO_REVISTA', 'PRODUCTO_BASE', 'PRODUCTO', 'DESCRIPCION', 'NOMBRE')
        if ean is None and name is None:
            continue
        page = _pick(row, columns, 'PAGINA_PDF', 'PAGINA')
        try: page = int(page) if page is not None else None
        except (ValueError, TypeError): page = None
        out.append(Product(
            ean=normalize_code(ean), name=str(name or ''),
            brand=str(_pick(row, columns, 'MARCA') or ''),
            presentation=str(_pick(row, columns, 'PRESENTACION', 'PRESENTACIÓN') or ''),
            price=_number(_pick(row, columns, 'PRECIO_REVISTA_COP', 'PRECIO_BASE_COP', 'PRECIO_COP', 'PRECIO')),
            discount=_number(_pick(row, columns, 'DESCUENTO_PCT', 'DESCUENTO_BASE_PCT', 'DESCUENTO')),
            page=page, source=f'{filename}/{sheet_name}',
            confidence=str(_pick(row, columns, 'CONFIANZA') or 'CATALOGO'),
            notes=str(_pick(row, columns, 'OBSERVACIONES') or ''),
            sku=str(_pick(row, columns, 'SKU') or '')
        ))
    return out
