"""OCR preliminar: detecta EAN candidatos, nunca inventa precio/producto."""
from io import BytesIO
import re
from PIL import Image, ImageOps, ImageEnhance
import fitz
from ..domain.models import Product
from ..domain.compare import valid_gtin

GTIN_RE = re.compile(r'\d{8,14}')

def page_preview(pdf_bytes, page_index, rotation=0, zoom=0.8):
    with fitz.open(stream=pdf_bytes,filetype='pdf') as pdf:
        pix=pdf[page_index].get_pixmap(matrix=fitz.Matrix(zoom,zoom),alpha=False)
        img=Image.open(BytesIO(pix.tobytes('png'))).convert('RGB')
        return img.rotate(rotation,expand=True) if rotation else img

def extract_candidates(pdf_bytes,pages,rotation_by_page=None,lang='spa+eng',dpi=160):
    import pytesseract
    from pytesseract import Output
    result=[];rotation_by_page=rotation_by_page or {}
    with fitz.open(stream=pdf_bytes,filetype='pdf') as pdf:
        for page_no in pages:
            if not 1 <= page_no <= len(pdf):continue
            pix=pdf[page_no-1].get_pixmap(matrix=fitz.Matrix(dpi/72,dpi/72),alpha=False)
            image=Image.open(BytesIO(pix.tobytes('png'))).convert('RGB')
            image=image.rotate(rotation_by_page.get(page_no,0),expand=True)
            image=ImageEnhance.Contrast(ImageOps.grayscale(image)).enhance(1.25)
            data=pytesseract.image_to_data(image,lang=lang,config='--psm 11',output_type=Output.DICT)
            words=[(str(t).strip(),int(data['left'][i]),int(data['top'][i]),int(data['height'][i]))
                   for i,t in enumerate(data['text']) if str(t).strip()]
            found=set()
            for i,(txt,x,y,h) in enumerate(words):
                combined=txt
                for count in range(3):
                    if count:
                        nxt=i+count
                        if nxt>=len(words) or abs(words[nxt][2]-y)>max(18,h):break
                        combined+=words[nxt][0]
                    code=re.sub(r'[\s\-]','',combined)
                    if not GTIN_RE.fullmatch(code) or code in found:continue
                    found.add(code)
                    near=[t for t,xx,yy,hh in words if abs(yy-y)<140 and abs(xx-x)<420 and t!=code]
                    result.append(Product(ean=code,page=page_no,confidence='REVISAR',source='OCR',notes=(
                        ('GTIN válido' if valid_gtin(code) else 'GTIN inválido')+
                        ' · OCR cercano (no verificado): '+' '.join(near[:18])[:180])))
    return result
