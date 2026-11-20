"""Regresión del flujo DEMO sin cargar pandas/Arrow (requiere sockets locales)."""
from pathlib import Path
import sys
import unittest

from streamlit.testing.v1 import AppTest
from auditoria.presentation.compatible_ui import table_html


class ForbidTableLibraries:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('pandas', 'pyarrow'):
            raise ImportError(f'La interfaz compatible no debe importar {fullname}')
        return None


class CompatibleUITests(unittest.TestCase):
    def setUp(self):
        self.guard = ForbidTableLibraries()
        sys.meta_path.insert(0,self.guard)
        self.addCleanup(lambda: sys.meta_path.remove(self.guard))
        self.app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py'),default_timeout=20).run()
        self.assertFalse(self.app.exception)
        self.button('Cargar transcripción para DEMO').click().run()
        self.assertFalse(self.app.exception)

    def button(self,label):
        return next(b for b in self.app.button if b.label==label)

    def field(self,label):
        return next(t for t in self.app.text_input if t.label==label)

    def selector(self):
        return next(s for s in self.app.selectbox if s.label=='Producto a revisar')

    def test_demo_edit_compare_and_download_without_pandas(self):
        self.app.multiselect[0].set_value(['DESCUENTO_PCT']).run()
        self.field('Descuento %').set_value('25.5').run()
        self.button('Comparar contra base de datos').click().run()
        self.assertFalse(self.app.exception)
        products,base,issues,*_=self.app.session_state['audit']
        self.assertEqual(len(products),36)
        self.assertEqual(products[0].discount,25.5)
        self.assertTrue(any(i.ean==products[0].ean and i.field=='DESCUENTO_PCT' for i in issues))
        self.assertEqual(len(self.app.get('download_button')),1)
        result_tables=[m.value for m in self.app.markdown if 'Descripción de la incoherencia' in m.value]
        self.assertEqual(len(result_tables),1)
        self.assertIn('25,5%',result_tables[0])
        self.assertNotIn('<th>Severidad</th>',result_tables[0])
        self.assertNotIn('SOLO_EN_BASE',result_tables[0])
        next(n for n in self.app.number_input if n.label.startswith('Tolerancia de descuento')).set_value(0.5).run()
        self.assertNotIn('audit',self.app.session_state)
        self.button('Comparar contra base de datos').click().run()
        self.assertFalse(self.app.exception)
        self.assertFalse(any(i.ean==products[0].ean and i.field=='DESCUENTO_PCT'
                             for i in self.app.session_state['audit'][2]))

    def test_navigation_preserves_edits_and_reload_resets_them(self):
        self.field('EAN').set_value('012345678905').run()
        self.field('Marca').set_value('Marca editada').run()
        self.selector().set_value(1).run()
        self.selector().set_value(0).run()
        self.assertEqual(self.field('EAN').value,'012345678905')
        self.assertEqual(self.field('Marca').value,'Marca editada')
        self.button('Cargar transcripción para DEMO').click().run()
        self.assertEqual(self.field('EAN').value,'7707397791469')
        self.assertEqual(self.field('Marca').value,'Dolex')
        self.assertFalse(self.app.exception)

    def test_add_and_remove_product(self):
        self.button('Añadir producto').click().run()
        self.assertEqual(len(self.app.session_state['compatible_editor']['records']),37)
        self.field('EAN').set_value('5901234123457').run()
        self.field('Producto').set_value('Nuevo producto').run()
        self.button('Quitar producto seleccionado').click().run()
        self.assertEqual(len(self.app.session_state['compatible_editor']['records']),36)
        self.assertFalse(self.app.exception)


class TableHTMLTests(unittest.TestCase):
    def test_escape_source_values(self):
        result=table_html([{'<campo>':'<script>alert(1)</script>','Vacío':None,'Vigente':False}])
        self.assertNotIn('<script>',result)
        self.assertIn('&lt;script&gt;',result)
        self.assertIn('&lt;campo&gt;',result)
        self.assertIn('False',result)
        self.assertNotIn('None',result)


if __name__=='__main__':unittest.main()
