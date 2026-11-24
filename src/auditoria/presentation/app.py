"""Interfaz web local. Ejecute desde raíz: streamlit run app.py"""
import sys
from pathlib import Path
from collections import Counter
import hashlib
import json
import streamlit as st

ROOT=Path(__file__).resolve().parents[3]
if str(ROOT/'src') not in sys.path:sys.path.insert(0,str(ROOT/'src'))
from auditoria.application.service import compare_catalogs,demo_extract,ocr_extract
from auditoria.infrastructure.excel_repo import get_sheets
from auditoria.infrastructure.report import report_xlsx
from auditoria.domain.models import Product
from auditoria.domain.validity import evaluate_validity,today_bogota
from auditoria.domain.rules import AuditRules,FIELDS
from auditoria.domain.numbers import parse_number
from auditoria.presentation.compatible_ui import edit_products,show_table
from auditoria.application.results import discrepancy_rows,pending_review_count

st.set_page_config(page_title='Auditoría comercial',layout='wide',page_icon='📊')
st.title('Auditoría de revista contra catálogo maestro')
st.caption('Sistema local de tres capas · procesamiento sin envío a servidores externos · los datos de origen no se modifican')

mode=st.sidebar.radio('2. Método de extracción', ['DEMO: transcripción revisable','OCR: leer PDF real','TARJETAS: detectar y visualizar','PRUEBA USUARIO FINAL'],horizontal=False)
if mode=='PRUEBA USUARIO FINAL':
    from auditoria.presentation.final_user_ui import final_user_workspace
    final_user_workspace()
    st.stop()
if mode.startswith('TARJETAS'):
    from auditoria.presentation.cards_ui import cards_workspace
    with st.sidebar:
        demo_cards=st.toggle('Utilizar revista de prueba incluida',value=True)
        if demo_cards:
            card_pdf=(ROOT/'data/Revista_Essentials.pdf').read_bytes()
        else:
            uploaded_pdf=st.file_uploader('Revista PDF para detectar tarjetas',type=['pdf'])
            card_pdf=uploaded_pdf.getvalue() if uploaded_pdf else None
    cards_workspace(card_pdf)
    st.stop()

with st.sidebar:
    st.header('1. Archivos de entrada')
    demo=st.toggle('Utilizar archivos de prueba incluidos',value=True)
    if demo:
        excel_path=ROOT/'data/Base_Datos_Demo.xlsx';pdf_path=ROOT/'data/Revista_Essentials.pdf'
        excel_bytes=excel_path.read_bytes();pdf_bytes=pdf_path.read_bytes();filename=excel_path.name
    else:
        x=st.file_uploader('Catálogo Excel u ODS',type=['xlsx','ods'])
        p=st.file_uploader('Revista PDF',type=['pdf'])
        if not x:st.info('Carga un catálogo Excel para continuar');st.stop()
        excel_bytes=x.getvalue();pdf_bytes=p.getvalue() if p else None;filename=x.name
    try:sheets=get_sheets(excel_bytes,filename)
    except Exception as e:st.error(f'No se pudo leer Excel: {e}');st.stop()
    catalog_sheet=st.selectbox('Hoja que simula la base de datos',sheets,
                                index=sheets.index('BASE_DATOS_PRUEBA') if 'BASE_DATOS_PRUEBA' in sheets else 0)
    tolerance=st.number_input('Tolerancia para precios (COP)',min_value=0,max_value=100000,step=100,value=0)
    with st.expander('Reglas de comparación',expanded=True):
        fields=st.multiselect('Campos a validar',FIELDS,default=list(FIELDS))
        discount_tolerance=st.number_input('Tolerancia de descuento (puntos porcentuales)',min_value=0.0,max_value=100.0,value=0.0,step=0.1)
        similarity=st.slider('Similitud mínima del nombre',min_value=0.0,max_value=1.0,value=0.82,step=0.01)
        normalize_brand=st.checkbox('Ignorar mayúsculas y tildes en marca',value=True)
        equivalent_units=st.checkbox('Aceptar unidades equivalentes',value=True)
        flag_missing=st.checkbox('Alertar campos vacíos',value=True)
        require_valid_gtin=st.checkbox('Exigir dígito verificador EAN válido para comparar',value=True)
        st.caption('EAN siempre exacto. Descuentos: escriba 12.5 para 12.5%. Una tolerancia de 0.5 acepta 25% frente a 25.5%. Las cantidades distintas del nombre siempre generan diferencia.')
        if not fields:st.warning('Seleccione al menos un campo.');st.stop()
    rules=AuditRules(fields=tuple(fields),price_tolerance=tolerance,
                     discount_tolerance=discount_tolerance,name_min_similarity=similarity,
                     normalize_brand=normalize_brand,equivalent_units=equivalent_units,
                     flag_missing=flag_missing,require_valid_gtin=require_valid_gtin)
    edition_year_text=st.text_input('Año de inicio de la edición (si la vigencia omite el año)',value='')
    edition_year=None
    if edition_year_text.strip():
        try:
            edition_year=int(edition_year_text)
            if not 1 <= edition_year <= 9999:raise ValueError()
        except ValueError:
            st.error('Indique un año válido de cuatro dígitos.');st.stop()
    st.caption(f'Fecha de evaluación en Colombia: {today_bogota().isoformat()}')

# Un cambio de archivo o método requiere una extracción nueva.
input_context=(hashlib.sha256(excel_bytes).hexdigest(),hashlib.sha256(pdf_bytes or b'').hexdigest(),mode)
if st.session_state.get('input_context') != input_context:
    st.session_state['input_context']=input_context
    st.session_state.pop('products',None)
    st.session_state.pop('audit',None)
    st.session_state['editor_version']=st.session_state.get('editor_version',0)+1

if mode.startswith('OCR'):
    from auditoria.infrastructure.pdf_ocr import page_preview
    if not pdf_bytes:st.error('Es necesario cargar un PDF para ejecutar OCR');st.stop()
    import fitz
    with fitz.open(stream=pdf_bytes,filetype='pdf') as doc:npages=len(doc)
    left,right=st.columns([1,2])
    with left:
        pages=st.multiselect('Páginas a procesar',list(range(1,npages+1)),default=[14] if npages>=14 else [1])
        rotation=st.selectbox('Rotación necesaria para leer las páginas',[0,90,180,270],index=1)
    with right:
        if pages:
            st.image(page_preview(pdf_bytes,pages[0]-1,rotation),caption=f'Previsualización de página {pages[0]}',width=400)
    if st.button('Ejecutar OCR local',type='primary',disabled=not pages):
        with st.spinner('Analizando las páginas seleccionadas...'):
            try:
                st.session_state['products']=ocr_extract(pdf_bytes,pages,{p:rotation for p in pages})
                st.session_state['mode']=mode
                st.session_state['editor_version']=st.session_state.get('editor_version',0)+1
                st.session_state.pop('audit',None)
            except Exception as e:st.error(f'OCR no disponible: {e}. Instala tesseract-ocr-spa y las dependencias.')
else:
    if st.button('Cargar transcripción para DEMO',type='primary'):
        try:
            st.session_state['products']=demo_extract(excel_bytes,filename)
            st.session_state['mode']=mode
            st.session_state['editor_version']=st.session_state.get('editor_version',0)+1
            st.session_state.pop('audit',None)
        except Exception as e:st.error(f'La hoja REVISTA_EXTRAIDA no está disponible: {e}')

if 'products' not in st.session_state:st.info('Clic en Cargar transcripción o Ejecutar OCR para comenzar.');st.stop()

st.subheader('3. Revisar valores extraídos')
st.info('Los valores de OCR son candidatos. Revise y complete los campos vacíos antes de comparar; no se inventan precios.')
st.caption('Vigencia: transcriba el rango impreso o complete inicio y fin (AAAA-MM-DD). Las fechas completas prevalecen sobre el texto. El OCR actual no asocia vigencias automáticamente.')
general_validity=st.text_input('Vigencia general confirmada de la revista (solo para filas sin vigencia)',
                              placeholder='Del 10 al 30 de noviembre de 2026')
rows=[{'EAN':p.ean,'Producto':p.name,'Marca':p.brand,'Presentación':p.presentation,
       'Precio COP':p.price,'Descuento %':p.discount,'Página PDF':p.page,
       'Vigencia texto':p.validity_text,'Vigencia inicio':p.valid_from,'Vigencia fin':p.valid_until,
       'Confianza':p.confidence,'Observaciones':p.notes} for p in st.session_state['products']]
updated=edit_products(rows,st.session_state.get('editor_version',0))

def numeric(v, *, money=False):
    try:return parse_number(v,money=money)
    except ValueError:return str(v)

comparison_context=json.dumps([input_context,catalog_sheet,updated,general_validity,edition_year,rules.as_dict()],sort_keys=True,default=str)
if st.session_state.get('comparison_context') != comparison_context:
    st.session_state.pop('audit',None)

if st.button('Comparar contra base de datos',type='primary'):
    try:
        products=[Product(ean=str(row.get('EAN') or ''),name=str(row.get('Producto') or ''),
                 brand=str(row.get('Marca') or ''),presentation=str(row.get('Presentación') or ''),
                 price=numeric(row.get('Precio COP'),money=True),discount=numeric(row.get('Descuento %')),
                 page=numeric(row.get('Página PDF')),confidence=str(row.get('Confianza') or ''),
                 validity_text=str(row.get('Vigencia texto') or ''),
                 valid_from=str(row.get('Vigencia inicio') or ''),valid_until=str(row.get('Vigencia fin') or ''),
                 notes=str(row.get('Observaciones') or '')) for row in updated]
        for product in products:
            if not (product.validity_text or product.valid_from or product.valid_until):
                product.validity_text=general_validity.strip()
        checked_on=today_bogota()
        base,findings=compare_catalogs(products,excel_bytes,filename,catalog_sheet,tolerance,
                                       as_of=checked_on,edition_year=edition_year,rules=rules)
        st.session_state['audit']=(products,base,findings,checked_on,edition_year,rules)
        st.session_state['comparison_context']=comparison_context
    except Exception as e:st.error(f'Error de comparación: {e}')

if 'audit' in st.session_state:
    products,base,findings,checked_on,audit_year,audit_rules=st.session_state['audit']
    if checked_on != today_bogota():
        st.warning('La fecha cambió. Vuelva a comparar para actualizar la vigencia.');st.stop()
    c=Counter(i.status for i in findings)
    result_rows=discrepancy_rows(findings)
    a,b,d,e=st.columns(4)
    a.metric('Productos revista',len(products));b.metric('Filas base',len(base));d.metric('Incoherencias',len(result_rows));e.metric('No existe en base',c['NO_EN_BASE'])
    st.subheader('4. Reporte de diferencias')
    st.caption('Campos evaluados: '+', '.join(audit_rules.fields)+'. Los campos desactivados no se validan.')
    st.caption(f'Resultados de la última comparación: {checked_on.isoformat()}. Si cambia datos o archivos, vuelva a comparar.')
    validity_rows=[]
    for product in products:
        validity=evaluate_validity(product,checked_on,audit_year)
        validity_rows.append({'EAN':product.ean,'Producto':product.name,
                              'Vigencia no vencida':validity.not_expired,'Estado':validity.status,
                              'Inicio':validity.start,'Fin':validity.end,'Revisión':validity.detail})
    show_table(validity_rows)
    st.caption('True: aún no venció, incluso si empieza en el futuro. False: ya venció. Vacío: requiere revisión. El último día está incluido.')
    if demo:st.warning('El catálogo de demostración contiene modificaciones intencionales. No refleja errores comprobados de una base empresarial.')
    st.subheader('Incoherencias encontradas')
    if result_rows:
        show_table(result_rows)
    elif pending_review_count(findings):
        st.info('No se encontraron incoherencias comparables; quedan datos pendientes de revisión.')
    else:
        st.success('No se encontraron incoherencias en los campos evaluados.')
    pending=pending_review_count(findings)
    if pending:
        st.warning(f'Hay {pending} alertas por datos faltantes, inválidos o identificaciones ambiguas. No aparecen como incoherencias confirmadas; revise los datos de entrada antes de dar la auditoría por terminada.')
    if c['SOLO_EN_BASE']:
        st.caption(f'{c["SOLO_EN_BASE"]} registros de Excel no aparecen en las páginas procesadas. Se excluyen de esta tabla porque eso no demuestra un error en la revista.')
    st.download_button('Descargar informe XLSX',report_xlsx(findings,products,base,checked_on,audit_year,audit_rules),
                       'Reporte_Auditoria.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    st.caption('Identificación por EAN exacto. EAN no válidos generan alertas de revisión. El OCR no valida automáticamente precios.')
