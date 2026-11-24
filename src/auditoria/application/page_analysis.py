"""Orientación, anclas de catálogo y números destacados con evidencia OCR revisable."""
from dataclasses import dataclass, asdict
from statistics import median
import re
import unicodedata

from ..infrastructure.layout_ocr import read_rotations, read_refinements
from ..infrastructure.product_cards import CardRegion, detect_cards, salient_regions
from ..domain.compare import valid_gtin


def clean(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.lower()) if not unicodedata.combining(c))


def ean_text(text):
    text=text.strip('.,:;() ')
    return text if re.fullmatch(r'(?:\d{8}|\d{12,14})',text) else ''


def orientation_score(words):
    vocabulary={'de','del','al','con','sin','por','para','precio','descuento','hasta','valido',
                'noviembre','promocion','crema','tabletas','ml','gramos','compra','gratis','producto'}
    return sum(40 if ean_text(w.text) and valid_gtin(ean_text(w.text)) else
               15 if ean_text(w.text) else 5 if clean(w.text) in vocabulary else
               3 if re.search(r'\d.*[%$]|\$.*\d',w.text) else
               1 if re.fullmatch(r'[A-Za-zÁÉÍÓÚáéíóúñÑ]{3,}',w.text) else 0 for w in words)


def union(boxes):
    return min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)


@dataclass(frozen=True)
class NumericFinding:
    text: str
    kind: str
    value: str
    box: tuple[int,int,int,int]
    context: str
    prominence: float


def numeric_findings(words,size):
    width,height=size
    findings=[]
    consumed=set()
    for index,word in enumerate(words):
        if index in consumed or ean_text(word.text):continue
        text=word.text.strip()
        box=word.box
        # Agrupar símbolos separados por OCR solo cuando están pegados al número.
        related=[]
        if text in ('$', 'COP'):
            related=[(j,w) for j,w in enumerate(words) if j!=index and w.line==word.line
                     and 0 <= w.box[0]-box[2] < max(25,box[3]-box[1])*2 and re.match(r'\d',w.text)]
            if related:
                j,w=min(related,key=lambda pair:pair[1].box[0]);text+=w.text;box=union([box,w.box]);consumed.add(j)
        if re.fullmatch(r'\d{1,3}(?:[.,]\d+)?',text):
            related=[(j,w) for j,w in enumerate(words) if j!=index and '%' in w.text
                     and abs(w.box[0]-box[2]) < max(35,box[3]-box[1])*1.2
                     and abs(w.box[1]-box[1]) < max(35,box[3]-box[1])]
            if related:
                j,w=min(related,key=lambda pair:abs(pair[1].box[0]-box[2]));text+=w.text;box=union([box,w.box]);consumed.add(j)
        if not re.search(r'\d',text) and '$' not in text:continue
        nearby=[w for w in words if abs((w.box[0]+w.box[2])/2-(box[0]+box[2])/2)<width*.18
                and abs((w.box[1]+w.box[3])/2-(box[1]+box[3])/2)<height*.09]
        context=' '.join(w.text for w in nearby)
        kind='numero_destacado';value=''
        percent=re.search(r'(\d{1,3}(?:[.,]\d+)?)\s*%',text)
        price=re.search(r'\$\s*(\d+(?:[.,]\d+)*)',text)
        if re.search(r'[#*]\s*\d{3,}',text):
            kind='contacto'
        elif percent and float(percent[1].replace(',','.'))<=100:
            value=percent[1].replace(',','.')
            kind='descuento_hasta' if 'hasta' in clean(context) else 'descuento'
        elif '$' in text:
            # No completar dígitos ilegibles ni sustituir O por 0 silenciosamente.
            if re.fullmatch(r'\$\s*\d+(?:[.,]\d+)*',text):
                kind='precio';value=price[1] if price else ''
            else:kind='precio_ilegible'
        elif re.search(r'\d\s*(?:mg|ml|kg|g|anos|meses|und|caps|tab)',clean(text)):
            kind='cantidad'
        elif re.fullmatch(r'\d{1,4}',text):
            same_line=' '.join(w.text for w in words if w.line==word.line)
            if re.search(r'\b(?:anos|meses|mg|ml|kg|gramos|tabletas|caps|minutos|horas)\b',clean(same_line)):
                kind='cantidad'
            elif any(m in clean(context) for m in ('valido','vigencia','noviembre','diciembre')) and box[3]-box[1]<height*.03:
                kind='fecha'
        if re.fullmatch(r'\d{8,}',text):continue
        prominence=round((box[3]-box[1])/height,5)
        if kind=='numero_destacado' and (prominence<.018 or not re.fullmatch(r'[S$]?\d+(?:[.,]\d+)*[+º°]?',text)):continue
        findings.append(NumericFinding(text,kind,value,box,context,prominence))
    # Conservar valores contradictorios para revisión, eliminar repeticiones espaciales.
    from ..infrastructure.product_cards import _overlap
    unique=[]
    for finding in sorted(findings,key=lambda f:(not bool(f.value),-f.prominence)):
        if any(_overlap(finding.box,n.box)>.6 and (finding.value==n.value and finding.kind==n.kind or finding.kind=='precio_ilegible' and n.kind=='precio') for n in unique):continue
        unique.append(finding)
    return sorted(unique,key=lambda f:f.prominence,reverse=True)


def _groups(values,threshold):
    groups=[]
    for value in sorted(values):
        if not groups or value-median(groups[-1])>threshold:groups.append([value])
        else:groups[-1].append(value)
    return groups


def catalog_regions(image,words,numbers,padding=.012):
    """Inferir columnas/filas desde EAN; recuperar tarjetas desde precios sin inventar EAN."""
    w,h=image.size
    eans=[word for word in words if ean_text(word.text)]
    # El mismo EAN leído dos veces en el mismo sitio no define dos tarjetas.
    anchors=[]
    for word in eans:
        if not any(abs(a.box[0]-word.box[0])<w*.05 and abs(a.box[1]-word.box[1])<h*.04 for a in anchors):anchors.append(word)
    prices=[n for n in numbers if n.kind in ('precio','precio_ilegible')]
    from ..infrastructure.layout_ocr import Word
    for price in prices:
        if not any(abs(a.box[0]-price.box[0])<w*.15 and -h*.02 <= price.box[1]-a.box[1]<h*.13 for a in anchors):
            anchors.append(Word('',(price.box[0],max(0,price.box[1]-round(h*.045)),price.box[2],price.box[3]),-1))
    if not anchors:return []
    # Un precio publicitario centrado no debe desplazar las columnas de EAN.
    col_groups=_groups([a.box[0] for a in anchors if a.text] or [a.box[0] for a in anchors],w*.20)
    if len(col_groups)<2:col_groups=_groups([a.box[0] for a in anchors],w*.20)
    columns=[median(g) for g in col_groups]
    gaps=[b-a for a,b in zip(sorted({a.box[1] for a in anchors}),sorted({a.box[1] for a in anchors})[1:]) if b-a>h*.10]
    row_step=median(gaps) if gaps else h*.25
    row_step=max(h*.14,min(h*.32,row_step))
    boxes=[]
    for anchor in anchors:
        column=min(range(len(columns)),key=lambda j:abs(columns[j]-anchor.box[0]))
        left=max(0,round(columns[column]-w*.045))
        right=round(columns[column+1]-w*.055) if column+1<len(columns) else round(w*.97)
        if right-left>w*.65:right=min(w,round(left+w*.48))
        if not anchor.text and not any(a.text and abs(a.box[1]-anchor.box[1])<row_step*.30 for a in anchors):
            left=max(0,round(anchor.box[0]-w*.12))
            right=min(w,round(anchor.box[0]+w*.35))
        top=max(0,round(anchor.box[1]-row_step*.55-h*padding))
        bottom=min(h,round(anchor.box[1]+row_step*.60+h*padding))
        # Precios y descuentos próximos a este EAN deben quedar dentro del recorte.
        for number in numbers:
            if number.kind not in ('precio','precio_ilegible','descuento','descuento_hasta'):continue
            x,y=(number.box[0]+number.box[2])/2,(number.box[1]+number.box[3])/2
            if left<=x<=right and abs(y-anchor.box[1])<row_step*.58:
                peers=[a for a in anchors if abs(a.box[0]-columns[column])<w*.2]
                nearest=min(peers,key=lambda a:abs(y-a.box[1]))
                if nearest is anchor:
                    top=min(top,number.box[1]-round(h*padding));bottom=max(bottom,number.box[3]+round(h*padding))
        # Cortar en la calle entre filas, nunca en otra ancla.
        peers=sorted(a.box[1] for a in anchors if abs(a.box[0]-columns[column])<w*.2)
        above=[y for y in peers if y<anchor.box[1]-h*.05]
        below=[y for y in peers if y>anchor.box[1]+h*.05]
        if above:top=max(top,round((above[-1]+anchor.box[1])/2))
        if below:bottom=min(bottom,round((below[0]+anchor.box[1])/2))
        boxes.append((max(0,left),max(0,top),min(w,right),min(h,bottom),ean_text(anchor.text)))
    boxes.sort(key=lambda b:(round(b[1]/(h*.08)),b[0]))
    return [CardRegion(i+1,box[:4],'anclas_ocr','tarjeta_con_ean' if box[4] else 'tarjeta_sin_ean',box[4]) for i,box in enumerate(boxes)]


def analyze_page(image,auto_rotate=True,mode='auto',reader=None,refiner=None,padding=.012):
    if mode not in ('auto','catalogo','promocion_pagina_completa'):raise ValueError('Tipo de página inválido.')
    if not 0<=padding<=.1:raise ValueError('Margen fuera de rango.')
    reader=reader or read_rotations
    refiner=refiner or read_refinements
    variants=reader(image,(0,90,180,270) if auto_rotate else (0,))
    scores={r:orientation_score(words) for r,words in variants.items()}
    rotation=max(scores,key=scores.get)
    image=image.rotate(rotation,expand=True)
    words=variants[rotation]
    # Las lecturas complementarias mantienen coordenadas de la página orientada.
    warnings=[]
    try:words=words+refiner(image)
    except (RuntimeError,TimeoutError,OSError) as error:
        warnings.append(f'No se completaron las pasadas de contraste: {error}')
    numbers=numeric_findings(words,image.size)
    cards=catalog_regions(image,words,numbers,padding=padding)
    kind='catalogo' if len(cards)>=2 else 'promocion_pagina_completa'
    if mode!='auto':kind=mode
    if kind=='promocion_pagina_completa':
        cards=[CardRegion(1,(0,0,image.width,image.height),'pagina_completa','promocion_sin_asignar_ean')]
    elif not cards:
        cards=detect_cards(image)
    ranking=sorted(scores.values(),reverse=True)
    metadata={'page_kind':kind,'rotation_applied':rotation,'orientation_scores':scores,
              'salient_regions':salient_regions(image,words,numbers) if kind=='promocion_pagina_completa' else [],
              'orientation_needs_review':len(ranking)>1 and ranking[0]-ranking[1]<max(10,ranking[0]*.15),
              'numeric_findings':[asdict(n) for n in numbers], 'warnings':warnings,
              'scope':'Lecturas OCR candidatas. No asignar promociones generales a EAN ni comparar automáticamente.',
              'words':[asdict(word) for word in words]}
    return image,cards,metadata
