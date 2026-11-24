"""Flujo simple: dos archivos, generar y resultados separados por revisión."""
import hashlib
import streamlit as st
from auditoria.application.hybrid import generate_hybrid
from auditoria.presentation.compatible_ui import show_table
from auditoria.domain.compare import normalize_text


def final_user_workspace():
    st.header('Prueba usuario final')
    excel=st.file_uploader('Agregar tabla de Excel con datos de la revista',type=['xlsx'],key='final_excel')
    pdf=st.file_uploader('Agregar PDF de la revista por analizar',type=['pdf'],key='final_pdf')
    context=(hashlib.sha256(excel.getvalue()).hexdigest(),hashlib.sha256(pdf.getvalue()).hexdigest()) if excel and pdf else None
    if st.session_state.get('final_context')!=context:
        st.session_state.pop('final_result',None)
        st.session_state['final_context']=context
    if st.button('Generar',type='primary',disabled=context is None):
        st.session_state.pop('final_result',None)
        bar=st.progress(0,text='Analizando la revista…')
        try:
            result=generate_hybrid(excel.getvalue(),excel.name,pdf.getvalue(),progress=lambda done,total:bar.progress(done/total,text=f'Analizando la revista: {done} de {total} páginas'))
            st.session_state['final_result']=result
        except Exception as error:st.error(f'No se pudo generar el análisis: {error}')
        finally:bar.empty()
    result=st.session_state.get('final_result')
    if result:
        visible=[row for row in result.rows if normalize_text(row.get('Producto') or '')
                 not in ('','producto por identificar','producto sin nombre')]
        pending=[]
        discrepancies=[]
        for row in visible:
            target=pending if row.get('Descripción de la incoherencia','').strip().startswith('Revisión pendiente:') else discrepancies
            target.append(row)
        st.caption(f'{result.pages} páginas procesadas · {result.agreed_fields} campos con acuerdo entre ambas lecturas. Se omiten los productos sin identificar. Marca y vigencia pueden quedar sin evaluar si no se leen; el acuerdo entre dos lecturas no garantiza exactitud.')
        st.subheader('Incoherencias encontradas del consenso')
        if discrepancies:show_table(discrepancies)
        else:st.info('No hay incoherencias para mostrar entre los productos identificados con consenso.')
        st.subheader('Revisiones pendientes de la revista')
        st.caption('Estas revisiones no son diferencias confirmadas con Excel.')
        if pending:show_table(pending)
        else:st.info('No hay revisiones pendientes para mostrar entre los productos identificados.')
