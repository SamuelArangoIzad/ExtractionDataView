from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile

import pymupdf
from PIL import Image, ImageDraw
from streamlit.testing.v1 import AppTest

from auditoria.infrastructure.product_cards import (
    CardRegion, annotated_page, detect_cards, export_cards, render_page, validate_box,
)


ROOT=Path(__file__).resolve().parents[1]


class CardTests(unittest.TestCase):
    def test_detect_separated_panels(self):
        image=Image.new('RGB',(600,800),'white')
        draw=ImageDraw.Draw(image)
        expected=[]
        for y in (50,300,550):
            for x in (30,330):
                draw.rectangle((x,y,x+230,y+180),fill='#163e70')
                draw.text((x+15,y+15),'Producto 100 ml',fill='white')
                expected.append((x,y,x+231,y+181))
        cards=detect_cards(image,padding=0)
        self.assertEqual(len(cards),6)
        for box in expected:
            self.assertTrue(any(all(abs(a-b)<8 for a,b in zip(c.box,box)) for c in cards))

    def test_blank_page_does_not_invent_cards(self):
        self.assertEqual(detect_cards(Image.new('RGB',(500,700),'white')),[])

    def test_crop_coordinates_rotation_and_bounds(self):
        doc=pymupdf.open();page=doc.new_page(width=200,height=300)
        page.draw_rect(pymupdf.Rect(10,10,60,60),color=(1,0,0),fill=(1,0,0))
        pdf=doc.tobytes();doc.close()
        original=render_page(pdf,1,dpi=72)
        rotated=render_page(pdf,1,90,dpi=72)
        self.assertEqual(rotated.size,(300,200))
        self.assertEqual(rotated.tobytes(),original.rotate(90,expand=True).tobytes())
        for box in [(-1,0,10,10),(0,0,0,10),(0,0,301,20),(10,20,5,30)]:
            with self.assertRaises(ValueError):validate_box(box,rotated.size)
        with self.assertRaises(ValueError):render_page(pdf,2)
        with self.assertRaises(ValueError):render_page(pdf,1,45)

    def test_export_contains_exact_crops_and_provenance(self):
        image=Image.new('RGB',(200,300),'blue')
        cards=[CardRegion(4,(20,30,100,180),'manual')]
        output=export_cards(b'pdf',1,270,image,cards,{'min_area':.02})
        with ZipFile(BytesIO(output)) as archive:
            manifest=json.loads(archive.read('regiones.json'))
            self.assertEqual(manifest['rotation_ccw'],270)
            self.assertEqual(manifest['cards'][0]['box'],[20,30,100,180])
            self.assertEqual(manifest['cards'][0]['origin'],'manual')
            crop=Image.open(BytesIO(archive.read('pagina_1_tarjeta_4.png')))
            self.assertEqual(crop.size,(80,150))
            self.assertEqual(crop.tobytes(),image.crop(cards[0].box).tobytes())
        self.assertEqual(image.getpixel((20,30)),(0,0,255))
        self.assertNotEqual(annotated_page(image,cards).tobytes(),image.tobytes())

    def test_real_pdf_generates_reviewable_regions(self):
        data=(ROOT/'data/Revista_Essentials.pdf').read_bytes()
        image=render_page(data,14)
        cards=detect_cards(image)
        # Cobertura técnica, no un porcentaje de precisión semántica.
        self.assertGreaterEqual(len(cards),1)
        for card in cards:
            self.assertEqual(validate_box(card.box,image.size),card.box)
            self.assertGreater(image.crop(card.box).width,0)
        self.assertEqual(len({c.box for c in cards}),len(cards))


class NoOCRLibraries:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('pandas','pyarrow','pytesseract'):
            raise ImportError(f'La detección visual no debe importar {fullname}')
        return None


class CardUITests(unittest.TestCase):
    def setUp(self):
        guard=NoOCRLibraries();sys.meta_path.insert(0,guard)
        self.addCleanup(lambda:sys.meta_path.remove(guard))
        self.app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        self.app.radio[0].set_value('TARJETAS: detectar y visualizar').run()
        self.select('Detección').set_value('Solo regiones visuales').run()
        self.assertFalse(self.app.exception)

    def button(self,label):return next(b for b in self.app.button if b.label==label)
    def select(self,label):return next(s for s in self.app.selectbox if s.label==label)

    def test_detect_display_and_download_without_excel_or_ocr(self):
        self.assertNotIn('products',self.app.session_state)
        self.button('Detectar tarjetas de esta página').click().run()
        self.assertFalse(self.app.exception)
        self.assertGreater(len(self.app.session_state['card_pages'][14]['cards']),0)
        self.assertGreaterEqual(len(self.app.get('image'))+len(self.app.get('imgs')),2)
        self.assertEqual(len(self.app.get('download_button')),1)

    def test_manual_edit_delete_and_rotation_invalidates_coordinates(self):
        self.button('Añadir región manual').click().run()
        next(n for n in self.app.number_input if n.label=='Izquierda').set_value(0)
        self.button('Guardar límites').click().run()
        self.assertFalse(self.app.exception)
        modified=self.app.session_state['card_pages'][14]['cards'][0]
        self.assertEqual(modified.box[0],0)
        self.assertEqual(modified.origin,'ajustada')
        self.select('Página de la revista').set_value(6).run()
        self.select('Página de la revista').set_value(14).run()
        self.assertEqual(self.app.session_state['card_pages'][14]['cards'][0],modified)
        self.button('Eliminar esta región').click().run()
        self.assertEqual(self.app.session_state['card_pages'][14]['cards'],[])
        self.button('Añadir región manual').click().run()
        self.select('Girar página (grados antihorarios)').set_value(90).run()
        self.assertFalse(self.app.exception)
        self.assertEqual(self.app.session_state['card_pages'][14]['cards'],[])

    def test_invalid_manual_bounds_keep_previous_region(self):
        self.button('Añadir región manual').click().run()
        initial=self.app.session_state['card_pages'][14]['cards'][0]
        next(n for n in self.app.number_input if n.label=='Derecha').set_value(0)
        self.button('Guardar límites').click().run()
        self.assertTrue(self.app.error)
        self.assertEqual(self.app.session_state['card_pages'][14]['cards'][0],initial)


if __name__=='__main__':unittest.main()
