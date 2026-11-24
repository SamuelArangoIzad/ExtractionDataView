"""Revisión de regiones visuales independiente del catálogo y del OCR."""
import hashlib
from dataclasses import replace

import pymupdf
import streamlit as st

from auditoria.infrastructure.product_cards import (
    CardRegion, annotated_page, detect_cards, export_cards, png_bytes, render_page, validate_box,
)
from auditoria.application.page_analysis import analyze_page
from auditoria.presentation.compatible_ui import show_table


@st.cache_data(show_spinner=False, max_entries=4)
def _page_bytes(pdf_bytes, page, rotation, dpi=120):
    return png_bytes(render_page(pdf_bytes,page,rotation,dpi=dpi))


def cards_workspace(pdf_bytes):
    from io import BytesIO
    from PIL import Image

    st.header('Tarjetas de producto: detectar y revisar')
    st.info('Revise los recortes y las lecturas candidatas de precios y descuentos. Las promociones generales no se asignan a un EAN ni se comparan automáticamente con Excel.')
    if not pdf_bytes:
        st.info('Cargue una revista PDF para comenzar.');return
    try:
        with pymupdf.open(stream=pdf_bytes,filetype='pdf') as pdf:
            if pdf.needs_pass:raise ValueError('El PDF está protegido con contraseña.')
            total=len(pdf)
        if not total:raise ValueError('El PDF no contiene páginas.')
    except Exception as error:
        st.error(f'No se pudo abrir el PDF: {error}');return
    digest=hashlib.sha256(pdf_bytes).hexdigest()
    if st.session_state.get('cards_document') != digest:
        st.session_state['cards_document']=digest
        st.session_state['card_pages']={}
    page=st.selectbox('Página de la revista',list(range(1,total+1)),index=13 if total>=14 else 0,key=f'card_page_{digest}')
    rotation=st.selectbox('Girar página (grados antihorarios)',[0,90,180,270],key=f'card_rotation_{digest}_{page}')
    engine=st.selectbox('Detección', ['Guiada por texto (OCR local)', 'Solo regiones visuales'])
    guided=engine=='Guiada por texto (OCR local)'
    automatic=st.checkbox('Corregir orientación automáticamente',value=True,disabled=not guided)
    layout=st.selectbox('Tipo de página',['Automático','Catálogo de varios productos','Promoción de página completa'])
    mode={'Automático':'auto','Catálogo de varios productos':'catalogo','Promoción de página completa':'promocion_pagina_completa'}[layout]
    with st.expander('Ajustes de detección'):
        minimum=st.slider('Área mínima de tarjeta (% de página)',1,15,2,key='card_minimum')
        margin=st.slider('Margen del recorte (% del lado de página)',0.0,5.0,1.2,0.2,key='card_margin')
        st.caption('El área mínima se aplica al detector visual. El margen amplía los recortes. Si el diseño no se reconoce, cambie el tipo de página o ajuste los límites manualmente.')
    try:
        image=Image.open(BytesIO(_page_bytes(pdf_bytes,page,rotation,180 if guided else 120))).convert('RGB')
    except Exception as error:
        st.error(f'No se pudo renderizar la página: {error}');return
    parameters={'min_area':minimum/100,'max_area':.30,'padding':margin/100}
    context=(rotation,minimum,margin,engine,automatic,mode)
    pages=st.session_state['card_pages']
    if page not in pages or pages[page]['context'] != context:
        pages[page]={'context':context,'cards':[],'detected':False,'revision':0,'next_id':1,'analysis':{}}
    state=pages[page]
    selection_key=f'card_selection_{digest}_{page}_{rotation}'
    st.caption('Al cambiar rotación o ajustes se reinician las regiones de esta página. Al cambiar de página se conservan sus regiones en la sesión. Detectar nuevamente reemplaza los recortes actuales.')
    if st.button('Detectar tarjetas de esta página',type='primary'):
        with st.spinner('Revisando orientación, tarjetas y números destacados...' if guided else 'Buscando regiones visuales...'):
            try:
                if guided:
                    _,state['cards'],state['analysis']=analyze_page(image,auto_rotate=automatic,mode=mode,padding=margin/100)
                elif mode=='promocion_pagina_completa':
                    state['cards']=[CardRegion(1,(0,0,image.width,image.height),'pagina_completa','promocion_sin_asignar_ean')]
                else:
                    state['cards']=detect_cards(image,**parameters)
                state['detected']=True
                state['revision']+=1
                state['next_id']=max((c.id for c in state['cards']),default=0)+1
            except Exception as error:
                st.error(f'No se pudieron detectar regiones: {error}')
                st.info('Puede usar «Solo regiones visuales» y corregir los límites manualmente.');return
    analysis=state['analysis']
    applied=analysis.get('rotation_applied',0)
    image=image.rotate(applied,expand=True)
    if analysis:
        for warning in analysis.get('warnings',[]):st.warning(warning)
        st.caption(f'Orientación mostrada: {(rotation+applied)%360}° antihorarios. Tipo: {analysis["page_kind"].replace("_"," ")}.')
        if analysis.get('orientation_needs_review'):
            st.warning('La orientación no es concluyente. Revise la imagen; puede desactivar la corrección automática y girarla manualmente.')
        if not analysis.get('words'):
            st.warning('No se pudo leer texto. Una región completa no confirma que exista una promoción.')
        findings=analysis.get('numeric_findings',[])
        commercial=[n for n in findings if n['kind'] in ('precio','precio_ilegible','descuento','descuento_hasta','numero_destacado')]
        if commercial:
            st.subheader('Números encontrados en la página · por confirmar')
            labels={'precio':'Precio','precio_ilegible':'Precio ilegible: revisar','descuento':'Descuento %','descuento_hasta':'Hasta … % (no descuento fijo)','numero_destacado':'Número destacado (sin clasificar)'}
            show_table([{'Lectura':n['text'],'Interpretación':labels[n['kind']],'Valor candidato':n['value'] or 'Revisar imagen'} for n in commercial])
            st.caption('El orden refleja el tamaño del texto. Cantidades, fechas y teléfonos se conservan solo como contexto en el JSON. Un precio anterior también puede aparecer: confirme cuál aplica.')
        else:
            st.warning('No se reconocieron precios o descuentos legibles. Revise la página; esto no significa que no existan.')
        if analysis.get('salient_regions'):
            with st.expander('Zonas destacadas del anuncio para revisar'):
                st.caption('Recortes por tamaño y contraste, incluso cuando el OCR no logra leerlos. Pueden contener letras o imágenes: no son valores numéricos confirmados.')
                for i,box in enumerate(analysis['salient_regions'],1):
                    st.image(png_bytes(image.crop(box)),caption=f'Zona destacada {i}',width=350)
    # La adición manual permite trabajar también con páginas sin detecciones.
    if st.button('Añadir región manual'):
        w,h=image.size
        state['cards'].append(CardRegion(state['next_id'],(w//4,h//4,3*w//4,3*h//4),'manual'))
        st.session_state[selection_key]=state['next_id']
        state['next_id']+=1
        state['revision']+=1
    cards=state['cards']
    st.metric('Regiones candidatas en esta página',len(cards))
    st.image(png_bytes(annotated_page(image,cards)),caption=f'Página {page}: recuadros numerados; no son productos confirmados.',width=650)
    if not cards:
        if state['detected']:st.warning('No se encontraron regiones con estos ajustes. Añada una región manual o cambie los parámetros; esto no significa que la página no tenga productos.')
        return
    key=f'card_edit_{digest}_{page}_{rotation}_{state["revision"]}'
    if st.session_state.get(selection_key) not in [c.id for c in cards]:
        st.session_state[selection_key]=cards[0].id
    selected=st.selectbox('Tarjeta a revisar',[c.id for c in cards],format_func=lambda i:f'Tarjeta {i}',key=selection_key)
    card=next(c for c in cards if c.id==selected)
    st.image(png_bytes(image.crop(card.box)),caption=f'Tarjeta {card.id} · página {page} · {card.origin}',width=500)
    if card.ean:st.caption(f'EAN leído (pendiente de confirmar): {card.ean}')
    inside=[n for n in analysis.get('numeric_findings',[]) if card.box[0]<=n['box'][0] and card.box[1]<=n['box'][1] and n['box'][2]<=card.box[2] and n['box'][3]<=card.box[3] and n['kind'] in ('precio','precio_ilegible','descuento','descuento_hasta','numero_destacado')]
    if inside:show_table([{'Lectura en este recorte':n['text'],'Tipo':n['kind'].replace('_',' ')} for n in inside])
    st.caption('Compruebe nombre, foto, precio, descuento, EAN y vigencia. Amplíe la región si corta información; elimínela si es un anuncio o contiene varios productos y cree recortes separados.')
    with st.form(f'{key}_{selected}_bounds'):
        st.write('Ajustar límites del recorte (píxeles sobre la página mostrada)')
        cols=st.columns(2)
        with cols[0]:
            x0=st.number_input('Izquierda',0,image.width,value=card.box[0],step=1)
            y0=st.number_input('Arriba',0,image.height,value=card.box[1],step=1)
        with cols[1]:
            x1=st.number_input('Derecha',0,image.width,value=card.box[2],step=1)
            y1=st.number_input('Abajo',0,image.height,value=card.box[3],step=1)
        save=st.form_submit_button('Guardar límites')
    if save:
        try:
            box=validate_box((x0,y0,x1,y1),image.size)
            state['cards']=[replace(c,box=box,origin='ajustada') if c.id==selected else c for c in cards]
            state['revision']+=1
            st.rerun()
        except ValueError as error:st.error(str(error))
    if st.button('Eliminar esta región'):
        state['cards']=[c for c in cards if c.id!=selected]
        state['revision']+=1
        st.rerun()
    st.download_button('Descargar recortes de esta página (ZIP)',
                       export_cards(pdf_bytes,page,(rotation+applied)%360,image,cards,parameters,analysis=analysis),
                       file_name=f'tarjetas_pagina_{page}.zip',mime='application/zip')
    st.caption('El ZIP incluye los recortes PNG, la página marcada y regiones.json con coordenadas, rotación y huella del PDF. Son candidatos revisables; no se incorporan automáticamente a la auditoría.')
