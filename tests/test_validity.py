import unittest
from datetime import date, datetime
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from auditoria.domain.models import Product
from auditoria.domain.validity import evaluate_validity, parse_range, parse_date
from auditoria.domain.compare import audit
from auditoria.infrastructure.report import report_xlsx
from auditoria.infrastructure.excel_repo import load_products


class ValidityTests(unittest.TestCase):
    def test_inclusive_end_and_future(self):
        p = Product(validity_text='Del 10 al 30 de noviembre de 2026')
        for today, expected, status in [(date(2026,11,9),True,'FUTURA'),
                                        (date(2026,11,10),True,'VIGENTE'),
                                        (date(2026,11,30),True,'VIGENTE'),
                                        (date(2026,12,1),False,'VENCIDA')]:
            with self.subTest(today=today):
                v = evaluate_validity(p, today)
                self.assertIs(v.not_expired, expected)
                self.assertEqual(v.status,status)

    def test_missing_year_requires_context(self):
        p = Product(validity_text='del 10 al 30 de noviembre')
        self.assertIsNone(evaluate_validity(p,date(2027,1,1)).not_expired)
        self.assertIs(evaluate_validity(p,date(2027,1,1),2026).not_expired,False)

    def test_cross_year(self):
        expected=(date(2026,12,20),date(2027,1,10))
        for text, year in [('del 20 de diciembre al 10 de enero',2026),
                           ('del 20 de diciembre de 2026 al 10 de enero',None),
                           ('del 20 de diciembre al 10 de enero de 2027',None)]:
            self.assertEqual(parse_range(text,year),expected)

    def test_invalid_and_missing_are_unknown(self):
        for p in [Product(), Product(validity_text='hasta agotar existencias'),
                  Product(validity_text='del 30 al 10 de noviembre de 2026'),
                  Product(validity_text='del 1 al 31 de noviembre de 2026'),
                  Product(valid_from='2026-11-10'),
                  Product(valid_from='ilegible',valid_until='2026-11-30'),
                  Product(valid_from='2026-12-01',valid_until='2026-11-30')]:
            with self.subTest(p=p):
                self.assertIsNone(evaluate_validity(p).not_expired)
                self.assertEqual(evaluate_validity(p).status,'REVISAR')

    def test_leap_year(self):
        self.assertEqual(parse_range('del 1 al 29 de febrero de 2024')[1],date(2024,2,29))
        with self.assertRaises(ValueError):parse_range('del 1 al 29 de febrero de 2026')

    def test_confirmed_dates_override_text(self):
        p=Product(validity_text='ilegible',valid_from='10/11/2026',valid_until='2026-11-30')
        self.assertIs(evaluate_validity(p,date(2026,12,1)).not_expired,False)
        self.assertEqual(parse_date(datetime(2026,11,10,13)),date(2026,11,10))

    def test_current_date_is_not_cached(self):
        p=Product(validity_text='del 10 al 30 de noviembre de 2026')
        with patch('auditoria.domain.validity.today_bogota',return_value=date(2026,11,30)):
            self.assertIs(evaluate_validity(p).not_expired,True)
        with patch('auditoria.domain.validity.today_bogota',return_value=date(2026,12,1)):
            self.assertIs(evaluate_validity(p).not_expired,False)

    def test_audit_independent_of_ean_and_excel(self):
        p=Product(validity_text='del 10 al 30 de noviembre de 2026')
        statuses={d.status for d in audit([p],[],as_of=date(2026,12,1))}
        self.assertIn('VIGENCIA_VENCIDA',statuses)
        self.assertIn('REVISAR_IDENTIFICACION',statuses)

    def test_compare_dates_and_brand(self):
        p=Product(ean='4006381333931',brand='A',valid_from='2026-11-10',valid_until='2026-11-30')
        b=Product(ean=p.ean,brand='B',valid_from='2026-11-11',valid_until='2026-11-29')
        fields={d.field for d in audit([p],[b],as_of=date(2026,11,19))}
        self.assertEqual(fields,{'MARCA','VIGENCIA_INICIO','VIGENCIA_FIN'})

    def test_excel_aliases_and_native_dates(self):
        rows=[['EAN','VIGENCIA','FECHA_INICIO','FECHA_FIN'],
              ['4006381333931','texto original',datetime(2026,11,10),date(2026,11,30)]]
        with patch('auditoria.infrastructure.excel_repo._load_sheet',return_value=rows):
            p=load_products(b'','test.xlsx','BASE','base')[0]
        self.assertEqual(p.valid_from,'2026-11-10')
        self.assertEqual(p.valid_until,'2026-11-30')
        self.assertEqual(p.validity_text,'texto original')

    def test_demo_explicit_notes(self):
        from pathlib import Path
        data=(Path(__file__).resolve().parents[1]/'data/Base_Datos_Demo.xlsx').read_bytes()
        products=load_products(data,'demo.xlsx','REVISTA_EXTRAIDA','revista')
        known=[p for p in products if p.validity_text]
        self.assertEqual(len(known),5)
        values=[evaluate_validity(p,date(2026,11,19),2026).not_expired for p in known]
        self.assertEqual(values.count(False),2)
        self.assertEqual(values.count(True),3)

    def test_report_boolean_and_roundtrip(self):
        products=[Product(ean='4006381333931',valid_from='2026-11-10',valid_until=end)
                  for end in ['2026-11-30','2026-12-30']]+[Product(ean='5901234123457')]
        output=report_xlsx([],products,[],as_of=date(2026,12,1))
        with ZipFile(BytesIO(output)) as z:
            root=ET.fromstring(z.read('xl/worksheets/sheet2.xml'))
        ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        booleans=[c.find('s:v',ns).text for c in root.findall('.//s:c',ns) if c.get('t')=='b']
        self.assertEqual(booleans,['0','1'])
        loaded=load_products(output,'report.xlsx','REVISTA','revista')
        self.assertEqual([evaluate_validity(p,date(2026,12,1)).not_expired for p in loaded],
                         [False,True,None])


if __name__=='__main__':unittest.main()
