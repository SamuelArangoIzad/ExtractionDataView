from io import BytesIO
import math
from xlsxwriter import Workbook
from ..domain.validity import evaluate_validity, today_bogota
from ..domain.rules import AuditRules
from ..application.results import discrepancy_rows,pending_review_count,RESULT_COLUMNS

def report_xlsx(issues,magazine,database,as_of=None,edition_year=None,rules=None):
    rules = rules or AuditRules()
    as_of = as_of if as_of is not None else today_bogota()
    validity_headers = ['VIGENCIA_TEXTO','VIGENCIA_INICIO','VIGENCIA_FIN','VIGENCIA_NO_VENCIDA',
                        'ESTADO_VIGENCIA','FECHA_EVALUACION','REVISION_VIGENCIA']
    def validity_values(product):
        v = evaluate_validity(product, as_of, edition_year)
        return [product.validity_text, v.start.isoformat() if v.start else product.valid_from,
                v.end.isoformat() if v.end else product.valid_until, v.not_expired,
                v.status, v.checked_on.isoformat(), v.detail]
    output=BytesIO();wb=Workbook(output,{'in_memory':True})
    fmt=wb.add_format({'bold':True,'font_color':'#FFFFFF','bg_color':'#17354B','text_wrap':True})
    sheets=[('DIFERENCIAS',list(RESULT_COLUMNS),
             [list(row.values()) for row in discrepancy_rows(issues)]),
            ('REVISTA',['EAN','PRODUCTO','MARCA','PRESENTACION','PRECIO_COP','DESCUENTO','PAGINA','CONFIANZA','NOTAS'] + validity_headers,
             [[p.ean,p.name,p.brand,p.presentation,p.price,p.discount,p.page,p.confidence,p.notes] + validity_values(p) for p in magazine]),
            ('BASE',['SKU','EAN','PRODUCTO','MARCA','PRESENTACION','PRECIO_COP','DESCUENTO'] + validity_headers,
             [[p.sku,p.ean,p.name,p.brand,p.presentation,p.price,p.discount] + validity_values(p) for p in database])]
    for name,heads,rows in sheets:
        sh=wb.add_worksheet(name);sh.freeze_panes(1,0);sh.set_column(0,len(heads)-1,22);sh.set_column(3,5,32)
        sh.set_row(0,32)
        if name == 'DIFERENCIAS':
            sh.set_column(0,0,42);sh.set_column(1,1,20);sh.set_column(2,2,10)
            sh.set_column(3,3,24);sh.set_column(4,4,90)
            wrapped=wb.add_format({'text_wrap':True,'valign':'top'})
        for j,h in enumerate(heads):sh.write_string(0,j,h,fmt)
        for i,row in enumerate(rows,1):
            if name == 'DIFERENCIAS':sh.set_row(i,60,wrapped)
            for j,v in enumerate(row):
                if v is None:continue
                if isinstance(v,bool):sh.write_boolean(i,j,v)
                elif isinstance(v,(int,float)) and math.isfinite(v):sh.write_number(i,j,v)
                else:sh.write_string(i,j,str(v))
        if rows:sh.autofilter(0,0,len(rows),len(heads)-1)
    sh=wb.add_worksheet('ADVERTENCIAS');sh.set_column('A:A',24);sh.set_column('B:B',95)
    notes=[('ALCANCE','Prototipo local; no modifica Excel de entrada'),('OCR','Extracción preliminar; validar identificación, precio, descuento y página'),
           ('EMPAREJAMIENTO','Únicamente por EAN exacto'),('DEMO','Las discrepancias del catálogo incluido son simuladas'),
           ('COBERTURA','SOLO_EN_BASE puede significar que el artículo no está en las páginas procesadas'),
           ('VIGENCIA','TRUE = no vencida (incluye futuras); FALSE = vencida; vacío = revisar. Fin inclusivo.'),
           ('FECHA_EVALUACION',as_of.isoformat() + ' · America/Bogota'),
           ('AÑO_EDICION',str(edition_year) if edition_year is not None else 'No indicado')]
    notes.append(('RESULTADOS','DIFERENCIAS solo incluye campos distintos, EAN no encontrados en Excel y vigencias vencidas.'))
    notes.append(('PENDIENTES',f'{pending_review_count(issues)} alertas de revisión por datos faltantes, inválidos o identificaciones ambiguas; no son incoherencias confirmadas.'))
    for i,(a,b) in enumerate(notes):sh.write_string(i,0,a,fmt);sh.write_string(i,1,b)
    sh=wb.add_worksheet('REGLAS');sh.set_column('A:A',32);sh.set_column('B:B',95)
    sh.write_row(0,0,['REGLA','VALOR APLICADO'],fmt)
    for i,(key,value) in enumerate(rules.as_dict().items(),1):
        sh.write_string(i,0,key)
        if isinstance(value,bool):sh.write_boolean(i,1,value)
        elif isinstance(value,(int,float)):sh.write_number(i,1,value)
        else:sh.write_string(i,1,', '.join(value) if isinstance(value,(list,tuple)) else str(value))
    sh.write_string(10,0,'Consulta EAN')
    sh.write_string(10,1,'Exacta tras quitar espacios y sufijo .0; sin similitud ni eliminación de ceros iniciales.')
    sh.write_string(11,0,'Unidad de descuento')
    sh.write_string(11,1,'Puntos porcentuales: 12.5 representa 12.5%, no 0.125. Diferencia igual a tolerancia aceptada.')
    wb.close();return output.getvalue()
