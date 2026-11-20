"""Edición y tablas sin pandas/Arrow ni sus extensiones nativas."""
from html import escape
import streamlit as st


def table_html(rows):
    if not rows:
        return '<p>Sin registros.</p>'
    headers = list(rows[0])
    header = ''.join(f'<th>{escape(str(h))}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(
        f'<td>{escape(str(row[h])) if row.get(h) is not None else ""}</td>'
        for h in headers) + '</tr>' for row in rows)
    return (
        '<div style="overflow:auto;max-height:480px"><table style="width:100%;'
        'border-collapse:collapse;text-align:left">'
        f'<thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'
    )


def show_table(rows):
    # Todos los valores de entrada se escapan; no se interpreta HTML del catálogo.
    st.markdown(table_html(rows), unsafe_allow_html=True)


def _save_field(state_key, row_id, field, widget_key):
    st.session_state[state_key]['records'][row_id][field] = st.session_state[widget_key]


def edit_products(rows, version):
    state_key = 'compatible_editor'
    if state_key not in st.session_state or st.session_state[state_key]['version'] != version:
        st.session_state[state_key] = {
            'version': version,
            'records': {i: dict(row) for i, row in enumerate(rows)},
            'next_id': len(rows),
        }
    draft = st.session_state[state_key]
    records = draft['records']
    fields = list(rows[0]) if rows else [
        'EAN', 'Producto', 'Marca', 'Presentación', 'Precio COP', 'Descuento %',
        'Página PDF', 'Vigencia texto', 'Vigencia inicio', 'Vigencia fin', 'Confianza', 'Observaciones']
    selector_key = f'product_selector_{version}'
    st.caption('Seleccione un producto para editarlo. Confirme cada cambio con Enter o saliendo del campo; luego pulse Comparar. Los cambios se conservan al cambiar de producto.')
    if st.button('Añadir producto', key=f'add_product_{version}'):
        row_id = draft['next_id']
        draft['next_id'] += 1
        records[row_id] = {field: '' for field in fields}
        st.session_state[selector_key] = row_id
    if not records:
        st.info('No hay productos. Puede añadir uno o volver a cargar la transcripción.')
        return []
    if st.session_state.get(selector_key) not in records:
        st.session_state[selector_key] = next(iter(records))
    row_id = st.selectbox('Producto a revisar', list(records), key=selector_key,
                          format_func=lambda i: f'{i + 1}. {records[i].get("EAN", "")} · {records[i].get("Producto", "")}')
    if st.button('Quitar producto seleccionado', key=f'remove_product_{version}'):
        del records[row_id]
        st.rerun()
    columns = st.columns(2)
    for i, field in enumerate(fields):
        value = records[row_id].get(field)
        widget_key = f'product_{version}_{row_id}_{field}'
        with columns[i % 2]:
            st.text_input(field, value='' if value is None else str(value), key=widget_key,
                          on_change=_save_field, args=(state_key, row_id, field, widget_key))
    st.caption(f'{len(records)} productos en la revisión. Los archivos originales no se modifican.')
    return [dict(row) for row in records.values()]
