import unittest
from auditoria.domain.models import Product
from auditoria.domain.compare import audit,valid_gtin

class Tests(unittest.TestCase):
    def test_ean(self):
        self.assertTrue(valid_gtin('4006381333931'))
        self.assertFalse(valid_gtin('4006381333932'))
    def test_price_and_discount(self):
        m=[Product('4006381333931','Crema marca','Marca','75 ml',14500,25,14)]
        b=[Product('4006381333931','Crema marca','Marca','75 ml',15900,30,sku='SKU1')]
        got=audit(m,b)
        self.assertEqual({g.field for g in got},{'PRECIO_COP','DESCUENTO_PCT'})
    def test_missing(self):
        m=[Product('4006381333931','Producto',price=100)]
        got=audit(m,[])
        self.assertEqual(got[0].status,'NO_EN_BASE')
    def test_not_silently_match_names(self):
        m=[Product('4006381333931','X')]
        b=[Product('5901234123457','X')]
        got=audit(m,b)
        self.assertTrue(any(i.status=='NO_EN_BASE' for i in got))
    def test_duplicate_base(self):
        p=Product('4006381333931','Producto')
        got=audit([p],[p,p])
        self.assertTrue(any(i.status=='EAN_DUPLICADO_BASE' for i in got))
if __name__=='__main__':unittest.main()
