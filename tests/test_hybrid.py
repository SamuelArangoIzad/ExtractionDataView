from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from io import BytesIO
import pymupdf
import xlsxwriter
from streamlit.testing.v1 import AppTest
from auditoria.application.hybrid import consensus,parse_reading,catalog_from_excel,generate_hybrid,HybridResult
from auditoria.infrastructure.layout_ocr import Word
from auditoria.domain.models import Product

ROOT=Path(__file__).resolve().parents[1]
EAN='7701021114174'


class HybridTests(TestCase):
    def test_two_differences_same_product_and_exact_identity(self):
        p=Product(ean=EAN,name='Pañal',price=10000,discount=10,page=2)
        merged,rows,count=consensus(p,p,[Product(ean=EAN,name='Pañal',price=11000,discount=15)])
        self.assertEqual({r['Campo'] for r in rows},{'Precio','Descuento'})
        self.assertEqual(count,3)
        self.assertTrue(all(r['Página']==2 for r in rows))

    def test_conflict_is_not_resolved_using_excel(self):
        a=Product(ean=EAN,price=10000,discount=10,page=1)
        b=Product(ean=EAN,price=12000,discount=10,page=1)
        merged,rows,_=consensus(a,b,[Product(ean=EAN,price=10000,discount=10)])
        self.assertIsNone(merged.price)
        self.assertTrue(any('No hay consenso' in r['Descripción de la incoherencia'] for r in rows))

    def test_missing_or_different_ean_never_matches_by_name(self):
        for code in ('','7701021116635'):
            merged,rows,count=consensus(Product(ean=EAN,name='Pañal'),Product(ean=code,name='Pañal'),[Product(ean=EAN)])
            self.assertEqual(count,0)
            self.assertFalse(merged.ean)
            self.assertEqual(rows[0]['Campo'],'EAN / identificación')

    def test_partial_name_is_review_not_confirmed_difference(self):
        p=Product(ean=EAN,name='Acetaminofén 500 mg',price=1000,discount=10)
        _,rows,_=consensus(p,p,[Product(ean=EAN,name='Dolex Acetaminofén 500 mg',price=1000,discount=10)])
        self.assertEqual(len(rows),1)
        self.assertIn('parece incompleto',rows[0]['Descripción de la incoherencia'])

    def test_package_prefix_is_not_an_extra_unit(self):
        p=parse_reading([Word('x',(10,50,20,65),0),Word('6',(25,50,35,65),0),Word('Und',(40,50,70,65),0),Word(EAN,(10,100,180,120),1)],(500,300),1)
        self.assertEqual(p.presentation,'6 Und')

    def test_multiple_prices_and_until_discount_not_assumed_fixed(self):
        p=parse_reading([Word('$10.000',(0,0,100,30)),Word('$12.000',(0,50,100,80),1),
                         Word('hasta',(0,100,80,120),2),Word('20%',(0,125,80,155),2)],(400,600),1)
        self.assertIsNone(p.price)
        self.assertIsNone(p.discount)

    def test_demo_catalog_does_not_read_transcribed_magazine(self):
        data=(ROOT/'data/Base_Datos_Demo.xlsx').read_bytes()
        products=catalog_from_excel(data,'demo.xlsx')
        self.assertTrue(products)
        self.assertTrue(all(p.source.endswith('/BASE_DATOS_PRUEBA') for p in products))

    def test_ambiguous_workbook_is_rejected(self):
        buffer=BytesIO()
        with xlsxwriter.Workbook(buffer,{'in_memory':True}) as book:
            for name in ('Uno','Dos'):
                sheet=book.add_worksheet(name);sheet.write_row(0,0,['EAN','PRODUCTO']);sheet.write_row(1,0,[EAN,'Pañal'])
        with self.assertRaises(ValueError):catalog_from_excel(buffer.getvalue(),'base.xlsx')

    def test_pipeline_invokes_separate_page_and_crop_reads(self):
        doc=pymupdf.open();doc.new_page(width=200,height=300);pdf=doc.tobytes();doc.close()
        calls=[]
        def reader(image,rotations):
            calls.append(rotations)
            return {angle:[Word(EAN,(60,150,180,170)),Word('$10.000',(60,180,170,210))] if angle==0 else [] for angle in rotations}
        with patch('auditoria.application.hybrid.catalog_from_excel',return_value=[Product(ean=EAN,price=11000)]):
            result=generate_hybrid(b'excel','base.xlsx',pdf,reader=reader,refiner=lambda im:[])
        self.assertEqual(calls,[(0,90,180,270),(0,)])
        self.assertEqual(result.pages,1)
        self.assertEqual(result.regions,1)

    def test_engine_failure_does_not_claim_no_differences(self):
        doc=pymupdf.open();doc.new_page();pdf=doc.tobytes();doc.close()
        with patch('auditoria.application.hybrid.catalog_from_excel',return_value=[]):
            result=generate_hybrid(b'excel','base.xlsx',pdf,reader=lambda *a:(_ for _ in ()).throw(RuntimeError('OCR no disponible')))
        self.assertEqual(result.incomplete_pages,1)
        self.assertIn('no se completó',result.rows[0]['Descripción de la incoherencia'])


class FinalUserUITests(TestCase):
    def test_only_two_uploaders_and_generate(self):
        app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
        app.radio[0].set_value('PRUEBA USUARIO FINAL').run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.get('file_uploader')),2)
        self.assertEqual([b.label for b in app.button],['Generar'])
        self.assertTrue(app.button[0].disabled)
        self.assertEqual(len(app.selectbox),0)
        self.assertEqual(len(app.number_input),0)

    def test_generate_renders_result_and_new_files_clear_it(self):
        class Upload(BytesIO):name='base.xlsx'
        excel=Upload(b'excel');pdf=Upload(b'pdf')
        source='from auditoria.presentation.final_user_ui import final_user_workspace\nfinal_user_workspace()'
        app=AppTest.from_string(source,default_timeout=30)
        rows=[{'Producto':'Pañal','EAN':EAN,'Página':2,'Campo':'Precio','Descripción de la incoherencia':'Precio diferente en Excel'}]
        rows.extend([
            dict(rows[0],Campo='Descuento',**{'Descripción de la incoherencia':'Revisión pendiente: descuento sin consenso'}),
            dict(rows[0],Producto='Producto por identificar'),
            dict(rows[0],Producto='Producto sin nombre',**{'Descripción de la incoherencia':'Revisión pendiente: sin nombre'}),
        ])
        with patch('streamlit.file_uploader',side_effect=[excel,pdf]):app.run()
        with patch('streamlit.file_uploader',side_effect=[excel,pdf]),patch('auditoria.presentation.final_user_ui.generate_hybrid',return_value=HybridResult(rows,1,1,2,0)) as generate:
            app.button[0].click().run()
            self.assertEqual(generate.call_count,1)
        self.assertFalse(app.exception)
        tables=[m.value for m in app.markdown if '<table' in m.value]
        self.assertEqual(len(tables),2)
        self.assertIn('Precio diferente',tables[0])
        self.assertNotIn('descuento sin consenso',tables[0])
        self.assertIn('descuento sin consenso',tables[1])
        self.assertNotIn('Precio diferente',tables[1])
        self.assertTrue(all('Producto por identificar' not in t and 'Producto sin nombre' not in t for t in tables))
        self.assertEqual([s.value for s in app.subheader],['Incoherencias encontradas del consenso','Revisiones pendientes de la revista'])
        with patch('streamlit.file_uploader',side_effect=[excel,Upload(b'otro pdf')]):app.run()
        self.assertNotIn('final_result',app.session_state)
