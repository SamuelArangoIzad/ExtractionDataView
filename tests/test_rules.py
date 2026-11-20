"""Casos de negocio y recorrido Excel -> servicio -> auditoría -> reporte."""
from dataclasses import replace
from datetime import date
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from python_calamine import CalamineWorkbook
from auditoria.application.service import compare_catalogs, demo_extract
from auditoria.domain.compare import audit, ExactEanIndex
from auditoria.domain.models import Product
from auditoria.domain.numbers import parse_number
from auditoria.domain.rules import AuditRules
from auditoria.infrastructure.excel_repo import load_products
from auditoria.infrastructure.report import report_xlsx


class RulesTests(unittest.TestCase):
    def setUp(self):
        self.base=Product(ean='4006381333931',name='Crema 100 ml',brand='Ácme',
                          presentation='100 ml',price=15000,discount=25,
                          valid_from='2026-11-01',valid_until='2026-11-30')

    def findings(self, product=None, rules=None, base=None):
        return audit([product or self.base],[base or self.base],
                     as_of=date(2026,11,20),rules=rules or AuditRules())

    def test_identical_complete_records(self):
        self.assertEqual(self.findings(),[])

    def test_price_tolerance_boundary(self):
        p=replace(self.base,price=15100)
        self.assertTrue(any(i.field=='PRECIO_COP' for i in self.findings(p)))
        self.assertEqual(self.findings(p,AuditRules(price_tolerance=100)),[])
        self.assertTrue(self.findings(replace(p,price=15100.01),AuditRules(price_tolerance=100)))

    def test_discount_decimal_and_tolerance(self):
        p=replace(self.base,discount=25.5)
        self.assertEqual([i.field for i in self.findings(p)],['DESCUENTO_PCT'])
        self.assertEqual(self.findings(p,AuditRules(discount_tolerance=0.5)),[])
        self.assertTrue(self.findings(replace(p,discount=25.51),AuditRules(discount_tolerance=0.5)))

    def test_decimal_boundary_is_not_float_rounding(self):
        p=replace(self.base,discount=0.3)
        b=replace(self.base,discount=0.1)
        self.assertEqual(self.findings(p,AuditRules(discount_tolerance=0.2),b),[])

    def test_brand_normalization_can_be_disabled(self):
        p=replace(self.base,brand='ACME')
        self.assertEqual(self.findings(p),[])
        self.assertEqual([i.field for i in self.findings(p,AuditRules(normalize_brand=False))],['MARCA'])

    def test_units_alias_and_conversion(self):
        for value in ['100 mililitros','0.1 litros','0,1 l']:
            with self.subTest(value=value):
                self.assertEqual(self.findings(replace(self.base,presentation=value)),[])
        self.assertTrue(self.findings(replace(self.base,presentation='100 mililitros'),
                                     AuditRules(equivalent_units=False)))

    def test_units_do_not_mix_dimensions_or_packaging(self):
        for value in ['100 mg','2 x 50 ml','100 ml + obsequio','200 ml']:
            self.assertEqual([i.field for i in self.findings(replace(self.base,presentation=value))],['PRESENTACION'])

    def test_name_threshold_is_configurable(self):
        p=replace(self.base,name='Crema suave 100 ml')
        self.assertEqual(self.findings(p,AuditRules(name_min_similarity=0.5)),[])
        self.assertTrue(self.findings(p,AuditRules(name_min_similarity=1)))

    def test_name_quantities_cannot_be_hidden_by_similarity(self):
        self.assertTrue(self.findings(replace(self.base,name='Crema 200 ml'),AuditRules(name_min_similarity=0)))

    def test_missing_fields_are_reviewed_even_when_both_empty(self):
        for attr,field in [('name','DESCRIPCION'),('brand','MARCA'),('presentation','PRESENTACION'),
                           ('price','PRECIO_COP'),('discount','DESCUENTO_PCT')]:
            p=replace(self.base,**{attr:None if attr in ('price','discount') else ''})
            with self.subTest(attr=attr):
                self.assertTrue(any(i.status=='REVISAR_CAMPO_FALTANTE' and i.field==field for i in self.findings(p,base=p)))
                self.assertEqual(self.findings(p,AuditRules(flag_missing=False),p),[])

    def test_invalid_numbers_remain_alerts_with_missing_disabled(self):
        for attr,value in [('price',-1),('price','ilegible'),('price',float('nan')),
                           ('discount',101),('discount',-0.1),('discount',float('inf'))]:
            with self.subTest(attr=attr,value=value):
                self.assertTrue(any(i.status=='REVISAR_VALOR_INVALIDO' for i in
                                    self.findings(replace(self.base,**{attr:value}),AuditRules(flag_missing=False))))

    def test_disabled_fields_are_not_evaluated(self):
        p=replace(self.base,brand='Otra marca',price=19000,valid_until='2026-11-15')
        self.assertEqual(self.findings(p,AuditRules(fields=('PRESENTACION',))),[])

    def test_exact_ean_not_name(self):
        p=replace(self.base,ean='5901234123457')
        got=self.findings(p)
        self.assertEqual({i.status for i in got},{'NO_EN_BASE','SOLO_EN_BASE'})

    def test_leading_zero_and_duplicates_preserved(self):
        p=replace(self.base,ean='012345678905')
        index=ExactEanIndex([p,p])
        self.assertEqual(len(index.find('012345678905')),2)
        self.assertEqual(index.find('12345678905'),())
        self.assertEqual(len(index.find(' 012345678905.0 ')),2)
        got=audit([p],[p,p],as_of=date(2026,11,20))
        self.assertEqual([i.status for i in got],['EAN_DUPLICADO_BASE'])

    def test_invalid_check_digit_blocks_comparison_by_default(self):
        b=replace(self.base,ean='4006381333932')
        p=replace(b,price=16000)
        self.assertEqual([i.status for i in self.findings(p,base=b)],['REVISAR_EAN'])
        got=self.findings(p,AuditRules(require_valid_gtin=False),b)
        self.assertEqual([i.status for i in got],['REVISAR_EAN','DIFERENCIA'])

    def test_malformed_ean_never_matches_even_with_relaxed_checksum(self):
        for code in ['', '12345', '400638133393X', '²'*13]:
            p=replace(self.base,ean=code)
            got=self.findings(p,AuditRules(require_valid_gtin=False),p)
            self.assertTrue(any(i.status=='REVISAR_IDENTIFICACION' for i in got))
            self.assertFalse(any(i.status=='DIFERENCIA' for i in got))

    def test_invalid_configuration_rejected(self):
        for kwargs in [{'price_tolerance':-1},{'price_tolerance':float('nan')},
                       {'discount_tolerance':101},{'name_min_similarity':1.1},
                       {'fields':()},{'fields':('EAN',)},{'fields':('MARCA','MARCA')},
                       {'flag_missing':'false'}]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):AuditRules(**kwargs)

    def test_colombian_money_and_percentage_points(self):
        for value,expected in [('15.000',15000),('$ 15.000,50',15000.5),('COP 15000',15000),
                               ('15000.50',15000.5),(15.5,15.5)]:
            self.assertEqual(parse_number(value,money=True),expected)
        self.assertEqual(parse_number('12,5%'),12.5)
        self.assertEqual(parse_number(0.125),0.125)
        self.assertIsNone(parse_number(''))
        with self.assertRaises(ValueError):parse_number('ilegible')
        with self.assertRaises(ValueError):parse_number('1e1000')

    def test_invalid_value_report_can_be_downloaded(self):
        p=replace(self.base,price=float('nan'))
        issues=self.findings(p)
        output=report_xlsx(issues,[p],[self.base])
        book=CalamineWorkbook.from_filelike(BytesIO(output))
        self.assertEqual(book.get_sheet_by_name('REVISTA').to_python()[1][4],'nan')

    def test_excel_loader_preserves_invalid_values_and_decimals(self):
        rows=[['EAN','PRECIO','DESCUENTO'],[self.base.ean,'$ 15.000,50','12,5%'],
              ['5901234123457','ilegible',101]]
        with patch('auditoria.infrastructure.excel_repo._load_sheet',return_value=rows):
            data=load_products(b'','test.xlsx','base','base')
        self.assertEqual((data[0].price,data[0].discount),(15000.5,12.5))
        got=audit([data[1]],[data[1]],rules=AuditRules(fields=('PRECIO_COP','DESCUENTO_PCT')))
        self.assertEqual([i.status for i in got],['REVISAR_VALOR_INVALIDO','REVISAR_VALOR_INVALIDO'])

    def test_real_excel_service_and_report_rules(self):
        path=Path(__file__).resolve().parents[1]/'data/Base_Datos_Demo.xlsx'
        original=path.read_bytes()
        products=demo_extract(original,path.name)
        dolex=products[0]
        self.assertEqual(dolex.ean,'7707397791469')
        strict=AuditRules(fields=('PRECIO_COP',))
        base,issues=compare_catalogs([dolex],original,path.name,'BASE_DATOS_PRUEBA',rules=strict)
        self.assertTrue(any(i.field=='PRECIO_COP' and i.status=='DIFERENCIA' for i in issues))
        relaxed=replace(strict,price_tolerance=2200)
        _,issues=compare_catalogs([dolex],original,path.name,'BASE_DATOS_PRUEBA',rules=relaxed)
        self.assertFalse(any(i.status=='DIFERENCIA' for i in issues))
        report=report_xlsx(issues,[dolex],base,rules=relaxed)
        book=CalamineWorkbook.from_filelike(BytesIO(report))
        values=dict(book.get_sheet_by_name('REGLAS').to_python()[1:])
        self.assertEqual(values['price_tolerance'],2200)
        self.assertEqual(values['fields'],'PRECIO_COP')
        self.assertEqual(path.read_bytes(),original)


if __name__=='__main__':unittest.main()
