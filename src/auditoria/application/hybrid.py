"""Dos lecturas del PDF, consenso conservador y consulta posterior por EAN exacto."""
from dataclasses import dataclass
from collections import defaultdict
import re
import pymupdf

from .page_analysis import orientation_score, catalog_regions, numeric_findings, ean_text
from .results import discrepancy_rows, RESULT_COLUMNS
from ..infrastructure.layout_ocr import read_rotations, read_refinements
from ..infrastructure.product_cards import render_page, CardRegion
from ..infrastructure.excel_repo import get_sheets, load_products
from ..domain.models import Product
from ..domain.compare import audit, normalize_text, valid_gtin, ExactEanIndex
from ..domain.numbers import parse_number
from ..domain.rules import AuditRules


FIELDS={'name':('DESCRIPCION','Nombre'), 'brand':('MARCA','Marca'),
        'presentation':('PRESENTACION','Presentación'), 'price':('PRECIO_COP','Precio'),
        'discount':('DESCUENTO_PCT','Descuento')}


def catalog_from_excel(data,filename):
    sheets=get_sheets(data,filename)
    if 'BASE_DATOS_PRUEBA' in sheets:
        return load_products(data,filename,'BASE_DATOS_PRUEBA','base')
    candidates=[]
    for sheet in sheets:
        if sheet.upper()=='REVISTA_EXTRAIDA':continue
        try:candidates.append(load_products(data,filename,sheet,'base'))
        except ValueError:continue
    if len(candidates)!=1:
        raise ValueError('El Excel debe contener una sola hoja de catálogo con columna EAN. No se pudo identificar una hoja única.')
    return candidates[0]


def inside(word,box):
    return box[0]<=word.box[0] and box[1]<=word.box[1] and word.box[2]<=box[2] and word.box[3]<=box[3]


def parse_reading(words,size,page):
    """Extrae solo lo observado; múltiples precios o códigos quedan ambiguos."""
    codes={ean_text(w.text) for w in words if ean_text(w.text)}
    product=Product(page=page,source='PDF híbrido',ean=next(iter(codes)) if len(codes)==1 else '')
    numbers=numeric_findings(words,size)
    for attr,kind in [('price','precio'),('discount','descuento')]:
        values={parse_number(n.value,money=attr=='price') for n in numbers if n.kind==kind}
        if len(values)==1:setattr(product,attr,values.pop())
    # El bloque descriptivo suele estar arriba del EAN, alineado con su margen izquierdo.
    anchors=[w for w in words if w.text==product.ean] if product.ean else []
    if anchors:
        anchor=anchors[0];x,y,_,_=anchor.box
        nearby=[w for w in words if x-size[0]*.035<=w.box[0]<x+size[0]*.33
                and y-size[1]*.30<=w.box[1]<y and '$' not in w.text and '%' not in w.text]
        lines=defaultdict(list)
        for w in nearby:lines[w.line].append(w)
        names=[]
        for line in sorted(lines.values(),key=lambda ws:min(w.box[1] for w in ws)):
            text=' '.join(w.text for w in sorted(line,key=lambda w:w.box[0]))
            if re.match(r'^x\s*\d',text,re.I):
                quantity=re.sub(r'^x\s*','',text,flags=re.I)
                quantity=re.sub(r'\b(?:tabl|tabs)\b','tabletas',quantity,flags=re.I)
                quantity=re.sub(r'\b(?:cap|caps)\b','cápsulas',quantity,flags=re.I)
                product.presentation=quantity
            elif re.match(r'^marca\s*:',text,re.I):product.brand=text.split(':',1)[1].strip()
            elif not re.search(r'antes|valido|vigencia|descuento',normalize_text(text)) and re.search(r'[a-zA-Z]',text):names.append(text)
        product.name=' '.join(names)
    return product


def row(product,field,description):
    return dict(zip(RESULT_COLUMNS,(product.name or 'Producto por identificar',product.ean or 'Sin confirmar',product.page,field,description)))


def consensus(first,second,database):
    """El Excel no vota ni completa lecturas; se consulta después del consenso."""
    rows=[]
    merged=Product(page=first.page,source='Consenso OCR página + OCR tarjeta')
    if not first.ean or first.ean!=second.ean or not valid_gtin(first.ean):
        rows.append(row(first,'EAN / identificación',f'Revisión pendiente: lectura de página «{first.ean or "sin código"}»; lectura de tarjeta «{second.ean or "sin código"}». Confirme el EAN en la revista antes de corregir Excel.'))
        return merged,rows,0
    merged.ean=first.ean
    agreed=[]
    for attr,(field,label) in FIELDS.items():
        a,b=getattr(first,attr),getattr(second,attr)
        present=a is not None and a!='' and b is not None and b!=''
        equal=(normalize_text(a)==normalize_text(b)) if attr not in ('price','discount') else a==b
        if present and equal:
            setattr(merged,attr,a);agreed.append(field)
        elif a not in (None,'') or b not in (None,'') or attr in ('price','discount'):
            rows.append(row(first,label,f'Revisión pendiente: página «{a if a is not None and a!="" else "sin lectura única"}»; tarjeta «{b if b is not None and b!="" else "sin lectura única"}». No hay consenso; compruebe la revista antes de modificar Excel.'))
    matches=ExactEanIndex(database).find(merged.ean)
    if len(matches)==1 and 'DESCRIPCION' in agreed:
        observed,expected=normalize_text(merged.name),normalize_text(matches[0].name)
        if observed!=expected and observed in expected:
            agreed.remove('DESCRIPCION')
            rows.append(row(merged,'Nombre','Revisión pendiente: el nombre leído parece incompleto frente al de Excel. Compruebe el nombre completo en la revista antes de corregirlo.'))
    if len(matches)==1 and not merged.name:merged.name=matches[0].name+' (nombre en Excel)'
    # El nombre de Excel es solo etiqueta, nunca evidencia de comparación.
    if agreed:
        issues=audit([merged],database,rules=AuditRules(fields=tuple(agreed),flag_missing=False))
        differences=discrepancy_rows(issues)
        for difference in differences:
            difference['Descripción de la incoherencia']='Posible incoherencia: '+difference['Descripción de la incoherencia']
        rows=differences+rows
        for issue in issues:
            if issue.status in ('EAN_DUPLICADO_BASE','REVISAR_VALOR_INVALIDO'):
                rows.append(row(merged,issue.field,'Revisión pendiente: Excel contiene un EAN duplicado o un valor inválido. Revise la fila del catálogo.'))
    elif len(matches)!=1:
        rows.append(row(merged,'EAN','Revisión pendiente: el EAN no tiene una fila única en Excel. Revise el catálogo.'))
    return merged,rows,len(agreed)


@dataclass
class HybridResult:
    rows:list
    pages:int
    regions:int
    agreed_fields:int
    incomplete_pages:int


def generate_hybrid(excel_bytes,filename,pdf_bytes,*,reader=None,refiner=None,pages=None,progress=None):
    reader=reader or read_rotations
    refiner=refiner or read_refinements
    database=catalog_from_excel(excel_bytes,filename)
    with pymupdf.open(stream=pdf_bytes,filetype='pdf') as pdf:
        if pdf.needs_pass:raise ValueError('El PDF está protegido con contraseña.')
        selected=list(pages) if pages is not None else list(range(1,len(pdf)+1))
    if not selected:raise ValueError('El PDF no contiene páginas.')
    rows=[];regions=agreed=incomplete=0
    for index,page in enumerate(selected):
        if progress:progress(index,len(selected))
        try:
            image=render_page(pdf_bytes,page,dpi=180)
            variants=reader(image,(0,90,180,270))
            rotation=max(variants,key=lambda angle:orientation_score(variants[angle]))
            image=image.rotate(rotation,expand=True)
            page_words=variants[rotation]
            # Detectar geometría no comparte lecturas con el OCR de cada recorte.
            geometry_words=page_words+refiner(image)
            cards=catalog_regions(image,geometry_words,numeric_findings(geometry_words,image.size))
            if not cards:cards=[CardRegion(1,(0,0,image.width,image.height),'pagina_completa')]
            page_agreed=0
            for card in cards:
                region=image.crop(card.box)
                # Rama A: palabras de la página completa, pasadas al sistema local del recorte.
                from ..infrastructure.layout_ocr import Word
                local=[Word(w.text,(w.box[0]-card.box[0],w.box[1]-card.box[1],w.box[2]-card.box[0],w.box[3]-card.box[1]),w.line)
                       for w in page_words if inside(w,card.box)]
                # Rama B: OCR nuevo sobre píxeles recortados; no reutiliza la transcripción A.
                crop_words=reader(region,(0,))[0]
                first=parse_reading(local,region.size,page)
                second=parse_reading(crop_words,region.size,page)
                _,found,count=consensus(first,second,database)
                rows.extend(found);agreed+=count;page_agreed+=count;regions+=1
            if not page_agreed:incomplete+=1
        except (RuntimeError,OSError,ValueError,TimeoutError) as error:
            incomplete+=1
            rows.append(row(Product(page=page),'Lectura de página',f'Revisión pendiente: no se completó la lectura de esta página ({error}). No se puede concluir que esté correcta.'))
    if progress:progress(len(selected),len(selected))
    # Una fila por campo diferente; repeticiones exactas de evidencia se eliminan.
    unique={tuple(str(r[c]) for c in RESULT_COLUMNS):r for r in rows}
    return HybridResult(list(unique.values()),len(selected),regions,agreed,incomplete)
