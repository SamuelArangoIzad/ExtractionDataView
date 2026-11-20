from io import BytesIO
import unittest
from python_calamine import CalamineWorkbook
from auditoria.application.results import discrepancy_rows, pending_review_count, RESULT_COLUMNS
from auditoria.domain.models import Difference
from auditoria.infrastructure.report import report_xlsx


def issue(status='DIFERENCIA',field='PRECIO_COP',magazine='24700.0',database='26900.0'):
    return Difference(status,'7707397791469','SKU1',field,magazine,database,6,'Dolex','PDF página 6')


class ResultTests(unittest.TestCase):
    def test_price_description_identifies_both_sources_and_field(self):
        row=discrepancy_rows([issue()])[0]
        self.assertEqual(tuple(row),RESULT_COLUMNS)
        self.assertEqual(row['Campo'],'Precio')
        self.assertIn('en la revista figura $24.700 COP; en Excel figura $26.900 COP',row[RESULT_COLUMNS[-1]])
        self.assertEqual(row['EAN'],'7707397791469')
        self.assertEqual(row['Página'],6)

    def test_only_incoherences_visible_and_reviews_counted(self):
        findings=[issue(),issue('SOLO_EN_BASE'),issue('REVISAR_CAMPO_FALTANTE'),
                  issue('REVISAR_EAN'),issue('NO_EN_BASE','EAN'),
                  issue('VIGENCIA_VENCIDA','VIGENCIA','2026-11-15','Fecha de evaluación: 2026-11-20')]
        rows=discrepancy_rows(findings)
        self.assertEqual(len(rows),3)
        self.assertEqual(pending_review_count(findings),2)
        self.assertIn('no se encuentra en Excel',rows[1][RESULT_COLUMNS[-1]])
        self.assertIn('terminó el 2026-11-15',rows[2][RESULT_COLUMNS[-1]])
        self.assertEqual(discrepancy_rows([]),[])
        self.assertEqual(discrepancy_rows([issue('SOLO_EN_BASE')]),[])

    def test_only_changed_fields_and_decimal_discounts(self):
        rows=discrepancy_rows([issue(field='DESCUENTO_PCT',magazine='25.5',database='25'),
                               issue(field='MARCA',magazine='A',database='B')])
        self.assertEqual([r['Campo'] for r in rows],['Descuento','Marca'])
        self.assertIn('25,5%',rows[0][RESULT_COLUMNS[-1]])
        self.assertIn('«A»',rows[1][RESULT_COLUMNS[-1]])
        self.assertIn('«B»',rows[1][RESULT_COLUMNS[-1]])

    def test_excel_uses_same_filtered_rows_and_preserves_other_sheets(self):
        findings=[issue(),issue('SOLO_EN_BASE'),issue('REVISAR_VIGENCIA')]
        book=CalamineWorkbook.from_filelike(BytesIO(report_xlsx(findings,[],[])))
        rows=book.get_sheet_by_name('DIFERENCIAS').to_python()
        self.assertEqual(rows[0],list(RESULT_COLUMNS))
        self.assertEqual(rows[1],list(discrepancy_rows(findings)[0].values()))
        self.assertEqual(len(rows),2)
        self.assertEqual(book.sheet_names,['DIFERENCIAS','REVISTA','BASE','ADVERTENCIAS','REGLAS'])
        self.assertIn('EAN',book.get_sheet_by_name('REVISTA').to_python()[0])


if __name__=='__main__':unittest.main()
