"""OCR de palabras con coordenadas, sin pandas; Windows integrado o Tesseract CLI."""
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import csv
import io
import os
import shutil
import subprocess
import asyncio


@dataclass(frozen=True)
class Word:
    text: str
    box: tuple[int,int,int,int]
    line: int = 0
    source: str = 'original'


def contrast_images(image):
    """Pasadas complementarias para cifras claras, rojas y amarillas sobre fondos de color."""
    small=image.convert('RGB').resize((max(1,image.width//2),max(1,image.height//2)))
    yield 'reducida',small
    yield 'texto_claro',small.convert('L').point(lambda v:0 if v>205 else 255).convert('RGB')
    for name in ('rojo','amarillo'):
        mask=small.convert('L')
        pixels=small.get_flattened_data() if hasattr(small,'get_flattened_data') else small.getdata()
        mask.putdata([0 if (r>g*1.35 and r>b*1.35 if name=='rojo' else r>130 and g>110 and b<min(r,g)*.7) else 255
                      for r,g,b in pixels])
        yield name,mask.convert('RGB')


def read_refinements(image,reader=None):
    reader=reader or read_rotations
    words=[]
    for pass_id,(name,variant) in enumerate(contrast_images(image),1):
        sx,sy=image.width/variant.width,image.height/variant.height
        for word in reader(variant,(0,))[0]:
            x0,y0,x1,y1=word.box
            words.append(Word(word.text,(round(x0*sx),round(y0*sy),round(x1*sx),round(y1*sy)),
                              pass_id*100000+word.line,name))
    return words


async def _windows_read(inputs):
    from winrt.windows.storage import StorageFile, FileAccessMode
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.media.ocr import OcrEngine
    engine=OcrEngine.try_create_from_user_profile_languages()
    if engine is None:raise RuntimeError('No hay idiomas OCR de Windows instalados.')
    result={}
    for item in inputs:
        file=await StorageFile.get_file_from_path_async(item['path'])
        stream=await file.open_async(FileAccessMode.READ)
        try:
            decoder=await BitmapDecoder.create_async(stream)
            bitmap=await decoder.get_software_bitmap_async()
            try:
                recognized=await engine.recognize_async(bitmap)
                words=[]
                for line_id,line in enumerate(recognized.lines):
                    for word in line.words:
                        r=word.bounding_rect
                        words.append(Word(word.text,(round(r.x),round(r.y),round(r.x+r.width),round(r.y+r.height)),line_id))
                result[item['rotation']]=words
            finally:bitmap.close()
        finally:stream.close()
    return result


def read_rotations(image, rotations=(0,)):
    """Devuelve palabras en coordenadas de cada imagen rotada, nunca del original."""
    with TemporaryDirectory(prefix='revista_ocr_') as directory:
        root=Path(directory)
        inputs=[]
        for angle in rotations:
            path=root/f'page_{angle}.png'
            image.rotate(angle,expand=True).save(path)
            inputs.append({'rotation':angle,'path':str(path)})
        if os.name=='nt':
            try:
                return asyncio.run(asyncio.wait_for(_windows_read(inputs),timeout=90))
            except ImportError as error:
                raise RuntimeError('Faltan bibliotecas WinRT. Instale requirements.txt en Windows.') from error
        executable=shutil.which('tesseract')
        if not executable:
            raise RuntimeError('Instale Tesseract con el idioma español para la detección guiada por texto.')
        results={}
        for item in inputs:
            result=subprocess.run([executable,item['path'],'stdout','-l','spa+eng','--psm','11','tsv'],
                                  capture_output=True,text=True,encoding='utf-8',timeout=60)
            if result.returncode:raise RuntimeError('Tesseract no pudo leer la página: '+result.stderr[-600:])
            words=[];lines={}
            for row in csv.DictReader(io.StringIO(result.stdout),delimiter='\t'):
                if not row['text'].strip():continue
                x,y,w,h=(int(row[k]) for k in ('left','top','width','height'))
                key=tuple(row[k] for k in ('block_num','par_num','line_num'))
                line=lines.setdefault(key,len(lines))
                words.append(Word(row['text'],(x,y,x+w,y+h),line))
            results[item['rotation']]=words
        return results
