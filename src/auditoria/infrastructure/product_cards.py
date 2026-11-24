"""Regiones visuales candidatas, sin OCR ni identificación semántica de productos."""
from dataclasses import asdict, dataclass
from io import BytesIO
import hashlib
import json
from zipfile import ZipFile, ZIP_DEFLATED

import pymupdf
from PIL import Image, ImageDraw, ImageFilter


@dataclass(frozen=True)
class CardRegion:
    id: int
    box: tuple[int, int, int, int]  # píxeles de la imagen renderizada y rotada; fin exclusivo
    origin: str = 'automatica'
    kind: str = 'tarjeta_candidata'
    ean: str = ''


def render_page(pdf_bytes, page_no, rotation=0, dpi=120):
    if rotation not in (0, 90, 180, 270):
        raise ValueError('La rotación debe ser 0, 90, 180 o 270 grados.')
    if not 72 <= dpi <= 200:
        raise ValueError('Resolución permitida: 72 a 200 dpi.')
    with pymupdf.open(stream=pdf_bytes, filetype='pdf') as pdf:
        if not 1 <= page_no <= len(pdf):
            raise ValueError('Página fuera del PDF.')
        page = pdf[page_no-1]
        scale = min(dpi / 72, 2200 / max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
    return image.rotate(rotation, expand=True)


def validate_box(box, size):
    x0, y0, x1, y1 = box
    w, h = size
    if not all(isinstance(v, int) for v in box) or not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
        raise ValueError('El recorte debe tener ancho y alto positivos y estar dentro de la página.')
    return tuple(box)


def _components(mask):
    w, h = mask.size
    pixels = bytearray(mask.tobytes())
    for start, pixel in enumerate(pixels):
        if not pixel:
            continue
        pixels[start] = 0
        stack = [start]
        left = right = start % w
        top = bottom = start // w
        count = 0
        while stack:
            pos = stack.pop()
            x, y = pos % w, pos // w
            count += 1
            left, right = min(left, x), max(right, x)
            top, bottom = min(top, y), max(bottom, y)
            neighbors = []
            if x: neighbors.append(pos-1)
            if x+1 < w: neighbors.append(pos+1)
            if y: neighbors.append(pos-w)
            if y+1 < h: neighbors.append(pos+w)
            for nxt in neighbors:
                if pixels[nxt]:
                    pixels[nxt] = 0
                    stack.append(nxt)
        yield (left, top, right+1, bottom+1), count


def _overlap(a, b):
    intersection = max(0, min(a[2],b[2])-max(a[0],b[0])) * max(0,min(a[3],b[3])-max(a[1],b[1]))
    smaller = min((a[2]-a[0])*(a[3]-a[1]),(b[2]-b[0])*(b[3]-b[1]))
    return intersection / smaller if smaller else 0


def salient_regions(image,words=(),numbers=()):
    """Zonas de tipografía grande por contraste; no asegura que contengan cifras."""
    from PIL import ImageOps
    from .layout_ocr import contrast_images
    candidates=[]
    selected=[]
    iw,ih=image.size
    # Priorizar evidencia comercial antes que componentes grandes de fotografías.
    for number in numbers:
        if number.kind not in ('precio','descuento','descuento_hasta'):continue
        a,b,c,d=number.box
        selected.append((max(0,a-round(iw*.04)),max(0,b-round(ih*.03)),min(iw,c+round(iw*.04)),min(ih,d+round(ih*.03))))
    for word in words:
        text=word.text.lower()
        if not (text.startswith('promoci') or text in ('dto','descuento','hasta')):continue
        a,b,c,d=word.box
        box=(max(0,a-round(iw*.4)),max(0,b-round(ih*.10)),min(iw,c+round(iw*.06)),min(ih,d+round(ih*.16)))
        if not any(_overlap(box,other)>.6 for other in selected):selected.append(box)
    for name,mask in contrast_images(image):
        if name=='reducida':continue
        w,h=mask.size
        pieces=[box for box,count in _components(ImageOps.invert(mask.convert('L')))
                if h*.035<=box[3]-box[1]<=h*.23 and w*.012<=box[2]-box[0]<=w*.28
                and .10<count/((box[2]-box[0])*(box[3]-box[1]))<.90]
        groups=[]
        for box in sorted(pieces,key=lambda b:b[0]):
            matched=False
            for group in groups:
                a,b,c,d=group
                if -.01*w<=box[0]-c<max(d-b,box[3]-box[1])*.7 and min(d,box[3])-max(b,box[1])>min(d-b,box[3]-box[1])*.4:
                    group[:]=[min(a,box[0]),min(b,box[1]),max(c,box[2]),max(d,box[3])];matched=True;break
            if not matched:groups.append(list(box))
        for a,b,c,d in groups:
            if c-a>w*.65:continue
            sx,sy=image.width/w,image.height/h
            candidates.append((max(0,round((a-10)*sx)),max(0,round((b-10)*sy)),min(image.width,round((c+10)*sx)),min(image.height,round((d+10)*sy))))
    for box in sorted(candidates,key=lambda b:b[3]-b[1],reverse=True):
        if len(selected)>=6:break
        if not any(_overlap(box,b)>.6 for b in selected):selected.append(box)
    return selected[:6]


def detect_cards(image, min_area=0.025, max_area=0.30, padding=0.012):
    """Agrupa fondos de color y filtra regiones rectangulares. No es un modelo entrenado.

    Diseños sin bordes/fondos separados o promociones compartidas requieren revisión.
    Los parámetros son proporciones del área/lado de la página, no píxeles fijos.
    """
    if not (0 < min_area < max_area <= 1 and 0 <= padding <= 0.1):
        raise ValueError('Parámetros de detección fuera de rango.')
    small = image.convert('RGB').copy()
    small.thumbnail((600,600))
    w, h = small.size
    indexed = small.quantize(colors=12, dither=Image.Dither.NONE)
    palette = indexed.getpalette()
    candidates = []
    masks = []
    # Paneles con texto oscuro y foto sobre blanco: ambos deben pertenecer al mismo recorte.
    gray = small.convert('L')
    for low in (40,55,70):
        masks.append(gray.point(lambda v: 255 if v < low or v > 190 else 0))
    for color in range(12):
        rgb = palette[color*3:color*3+3]
        if not rgb or min(rgb) > 235:
            continue
        masks.append(indexed.point([255 if i == color else 0 for i in range(256)], mode='L'))
    for mask in masks:
        # Cerrar letras/agujeros pequeños sin unir calles amplias entre tarjetas.
        mask = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
        for box, count in _components(mask):
            x0,y0,x1,y1 = box
            bw,bh = x1-x0,y1-y0
            fraction = bw*bh/(w*h)
            if min_area <= fraction <= max_area and w*.12 <= bw <= w*.8 and bh >= h*.08 and .3 <= bw/bh <= 4 and count/(bw*bh) >= .45:
                candidates.append(box)
    white = gray.point(lambda v:255 if v > 170 else 0).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    photos = [box for box,count in _components(white)
              if w*.07 <= box[2]-box[0] <= w*.35 and h*.08 <= box[3]-box[1] <= h*.4]
    expanded = []
    for x0,y0,x1,y1 in candidates:
        for a,b,c,d in photos:
            overlap_y = max(0,min(y1,d)-max(y0,b))
            # Unir panel de texto y fondo claro contiguo de foto, no otra columna.
            if (x0+.4*(x1-x0) <= a <= x1+w*.035 and c > x1 and overlap_y/min(y1-y0,d-b) >= .7
                    and .5 <= (d-b)/(y1-y0) <= 1.6 and c-x0 <= w*.65):
                x1,y0,y1 = c,min(y0,b),max(y1,d)
        expanded.append((x0,y0,x1,y1))
    candidates = expanded
    # Una tarjeta puede tener varios colores: conservar la caja exterior, sin duplicados.
    kept = []
    for box in sorted(candidates,key=lambda b:(b[2]-b[0])*(b[3]-b[1]),reverse=True):
        if not any(_overlap(box,other) > .65 for other in kept):
            kept.append(box)
    sx,sy = image.width/w,image.height/h
    px,py = round(image.width*padding),round(image.height*padding)
    boxes = [(max(0,round(a*sx)-px),max(0,round(b*sy)-py),
              min(image.width,round(c*sx)+px),min(image.height,round(d*sy)+py)) for a,b,c,d in kept]
    boxes.sort(key=lambda b:(b[1]//max(1,round(image.height*.08)),b[0],b[1]))
    return [CardRegion(i+1,box) for i,box in enumerate(boxes)]


def png_bytes(image):
    out = BytesIO()
    image.save(out,format='PNG')
    return out.getvalue()


def annotated_page(image, cards):
    result = image.copy()
    draw = ImageDraw.Draw(result)
    for card in cards:
        x0,y0,x1,y1 = validate_box(card.box,image.size)
        draw.rectangle((x0,y0,x1-1,y1-1),outline='#ff5c00',width=max(2,image.width//300))
        label=f'{card.id}'
        draw.rectangle((x0,y0,x0+40,y0+24),fill='#ff5c00')
        draw.text((x0+5,y0+4),label,fill='white')
    return result


def export_cards(pdf_bytes, page_no, rotation, image, cards, parameters, analysis=None):
    manifest={'pdf_sha256':hashlib.sha256(pdf_bytes).hexdigest(),'page':page_no,
              'rotation_ccw':rotation,'image_size':list(image.size),
              'coordinate_system':'pixels_rotated_image_top_left_xyxy_end_exclusive',
              'parameters':parameters,'status':'candidatas_requieren_revision',
              'cards':[asdict(c) for c in cards]}
    if analysis is not None:
        manifest['analysis']=analysis
    output=BytesIO()
    with ZipFile(output,'w',ZIP_DEFLATED) as archive:
        archive.writestr('regiones.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        archive.writestr(f'pagina_{page_no}_marcada.png',png_bytes(annotated_page(image,cards)))
        for card in cards:
            archive.writestr(f'pagina_{page_no}_tarjeta_{card.id}.png',png_bytes(image.crop(validate_box(card.box,image.size))))
    return output.getvalue()
