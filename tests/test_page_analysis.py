"""Regresiones de geometría, lectura y UI; el OCR nativo se verifica por separado."""
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from PIL import Image
from streamlit.testing.v1 import AppTest

from auditoria.application.page_analysis import analyze_page, numeric_findings
from auditoria.infrastructure.layout_ocr import Word, read_refinements
from auditoria.infrastructure.product_cards import CardRegion, validate_box

ROOT=Path(__file__).resolve().parents[1]


class PageAnalysisTests(TestCase):
    def test_price_percentage_contact_quantity_and_garbage(self):
        words=[Word('$92.600',(0,0,130,30),0),Word('20%',(0,100,80,140),1),
               Word('hasta',(0,80,80,99),1),Word('*678',(0,250,80,290),2),
               Word('1800g',(0,450,80,490),3),Word('Sua0idad',(0,600,120,640),4),
               Word('$2?.600',(0,700,120,740),5)]
        found={n.text:n for n in numeric_findings(words,(800,1000))}
        self.assertEqual(found['$92.600'].value,'92.600')
        self.assertEqual(found['20%'].kind,'descuento_hasta')
        self.assertEqual(found['*678'].kind,'contacto')
        self.assertEqual(found['1800g'].kind,'cantidad')
        self.assertNotIn('Sua0idad',found)
        self.assertEqual(found['$2?.600'].value,'')

    def test_separate_percent_and_currency_symbols(self):
        found=numeric_findings([Word('$',(10,10,25,40)),Word('92.600',(26,10,120,40)),
                               Word('20',(10,200,60,240),1),Word('%',(62,215,80,240),1)],(500,1000))
        self.assertEqual({n.value for n in found},{'92.600','20'})

    def test_conflicting_readings_are_not_silently_resolved(self):
        found=numeric_findings([Word('$10.900',(10,10,100,40)),Word('$10.900',(11,10,101,40),1),
                               Word('$10.800',(10,10,100,40),2)],(500,700))
        self.assertEqual(len(found),2)

    def test_blank_and_forced_full_page_do_not_assign_ean(self):
        image,cards,meta=analyze_page(Image.new('RGB',(500,700),'white'),reader=lambda *a:{0:[]},refiner=lambda i:[])
        self.assertEqual(len(cards),1)
        self.assertEqual(cards[0].box,(0,0,500,700))
        self.assertFalse(cards[0].ean)
        self.assertEqual(meta['numeric_findings'],[])
        self.assertEqual(meta['salient_regions'],[])

    def test_refinement_coordinates_return_to_original_scale(self):
        words=read_refinements(Image.new('RGB',(800,1000),'white'),reader=lambda *a:{0:[Word('$25',(10,20,50,40))]})
        self.assertEqual(len(words),4)
        self.assertTrue(all(w.box==(20,40,100,80) for w in words))
        self.assertEqual(len({w.line for w in words}),4)

    def test_refinement_failure_keeps_first_pass_and_reports_warning(self):
        def failed(image):raise RuntimeError('OCR temporalmente no disponible')
        _,cards,meta=analyze_page(Image.new('RGB',(500,700),'white'),reader=lambda *a:{0:[Word('20%',(10,10,90,50))]},refiner=failed)
        self.assertEqual(meta['numeric_findings'][0]['value'],'20')
        self.assertTrue(meta['warnings'])

    def test_eight_recorded_pages_orientation_and_card_recall(self):
        fixtures=json.loads((ROOT/'tests/fixtures/layout_ocr.json').read_text(encoding='utf8'))
        expected={4:3,5:1,8:5,9:1,10:1,11:6,12:4,15:5}
        for case in fixtures:
            with self.subTest(page=case['page']):
                variants={int(k):[Word(**w) for w in v] for k,v in case['variants'].items()}
                refined=[Word(**w) for w in case['refined']]
                im,cards,meta=analyze_page(Image.new('RGB',case['size'],'white'),reader=lambda *a:variants,refiner=lambda i:refined)
                self.assertEqual(meta['rotation_applied'],case['rotation'])
                self.assertEqual(len(cards),expected[case['page']])
                for c in cards:validate_box(c.box,im.size)
                if case['page']==10:self.assertIn('92.600',[n['value'] for n in meta['numeric_findings']])
                if case['page']==8:self.assertEqual(sum(n['kind']=='descuento' and n['value']=='15' for n in meta['numeric_findings']),5)
                if case['page'] in (5,9,10):self.assertFalse(cards[0].ean)
                if case['page'] in (5,9):
                    # Cifras estilizadas no leídas: el recorte contextual conserva la evidencia.
                    target={5:(1080,1530,1340,1640),9:(800,880,1250,1300)}[case['page']]
                    self.assertTrue(any(b[0]<=target[0] and b[1]<=target[1] and b[2]>=target[2] and b[3]>=target[3] for b in meta['salient_regions']))
                # Toda ancla EAN debe quedar dentro de una tarjeta.
                from auditoria.application.page_analysis import ean_text
                for word in variants[case['rotation']]:
                    if ean_text(word.text):
                        self.assertTrue(any(c.box[0]<=word.box[0] and c.box[1]<=word.box[1] and word.box[2]<=c.box[2] and word.box[3]<=c.box[3] for c in cards))


class GuidedUITests(TestCase):
    def test_guided_detection_rotation_and_retained_state(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('TARJETAS: detectar y visualizar').run()
        def analyze(image,**kwargs):
            result=image.rotate(90,expand=True)
            return result,[CardRegion(1,(0,0,result.width,result.height),'pagina_completa')],{
                'rotation_applied':90,'page_kind':'promocion_pagina_completa','words':[{'text':'20%'}],
                'numeric_findings':[{'text':'20%','kind':'descuento','value':'20','box':(10,10,100,50)}]}
        with patch('auditoria.presentation.cards_ui.analyze_page',side_effect=analyze):
            next(b for b in app.button if b.label=='Detectar tarjetas de esta página').click().run()
        self.assertFalse(app.exception)
        state=app.session_state['card_pages'][14]
        self.assertEqual(state['analysis']['rotation_applied'],90)
        self.assertTrue(any('20%' in md.value for md in app.markdown))
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('download_button')),1)
        next(s for s in app.selectbox if s.label=='Tipo de página').set_value('Catálogo de varios productos').run()
        self.assertEqual(app.session_state['card_pages'][14]['analysis'],{})

    def test_missing_engine_has_actionable_fallback(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('TARJETAS: detectar y visualizar').run()
        with patch('auditoria.presentation.cards_ui.analyze_page',side_effect=RuntimeError('Faltan bibliotecas WinRT')):
            next(b for b in app.button if b.label=='Detectar tarjetas de esta página').click().run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        self.assertTrue(any('Solo regiones visuales' in info.value for info in app.info))
