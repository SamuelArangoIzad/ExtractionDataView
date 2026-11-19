from io import BytesIO
from xlsxwriter import Workbook

def report_xlsx(issues,magazine,database):
    output=BytesIO();wb=Workbook(output,{'in_memory':True})
    fmt=wb.add_format({'bold':True,'font_color':'#FFFFFF','bg_color':'#17354B','text_wrap':True})
    sheets=[('DIFERENCIAS',['ESTADO','EAN','SKU','CAMPO','VALOR_REVISTA','VALOR_BASE','PAGINA','PRODUCTO','EVIDENCIA','SEVERIDAD'],
             [[d.status,d.ean,d.sku,d.field,d.magazine_value,d.database_value,d.page,d.product,d.evidence,d.severity] for d in issues]),
            ('REVISTA',['EAN','PRODUCTO','MARCA','PRESENTACION','PRECIO_COP','DESCUENTO','PAGINA','CONFIANZA','NOTAS'],
             [[p.ean,p.name,p.brand,p.presentation,p.price,p.discount,p.page,p.confidence,p.notes] for p in magazine]),
            ('BASE',['SKU','EAN','PRODUCTO','MARCA','PRESENTACION','PRECIO_COP','DESCUENTO'],
             [[p.sku,p.ean,p.name,p.brand,p.presentation,p.price,p.discount] for p in database])]
    for name,heads,rows in sheets:
        sh=wb.add_worksheet(name);sh.freeze_panes(1,0);sh.set_column(0,len(heads)-1,22);sh.set_column(3,5,32)
        sh.set_row(0,32)
        for j,h in enumerate(heads):sh.write_string(0,j,h,fmt)
        for i,row in enumerate(rows,1):
            for j,v in enumerate(row):
                if v is None:continue
                if isinstance(v,(int,float)):sh.write_number(i,j,v)
                else:sh.write_string(i,j,str(v))
        if rows:sh.autofilter(0,0,len(rows),len(heads)-1)
    sh=wb.add_worksheet('ADVERTENCIAS');sh.set_column('A:A',24);sh.set_column('B:B',95)
    notes=[('ALCANCE','Prototipo local; no modifica Excel de entrada'),('OCR','Extracción preliminar; validar identificación, precio, descuento y página'),
           ('EMPAREJAMIENTO','Únicamente por EAN exacto'),('DEMO','Las discrepancias del catálogo incluido son simuladas'),
           ('COBERTURA','SOLO_EN_BASE puede significar que el artículo no está en las páginas procesadas')]
    for i,(a,b) in enumerate(notes):sh.write_string(i,0,a,fmt);sh.write_string(i,1,b)
    wb.close();return output.getvalue()
