from ..domain.compare import audit
from ..infrastructure.excel_repo import load_products
from ..infrastructure.pdf_ocr import extract_candidates

def compare_catalogs(magazine,excel_bytes,filename,sheet,tolerance=0,as_of=None,edition_year=None):
    database=load_products(excel_bytes,filename,sheet,'base')
    return database,audit(magazine,database,price_tolerance=tolerance,as_of=as_of,edition_year=edition_year)

def demo_extract(excel_bytes,filename):
    return load_products(excel_bytes,filename,'REVISTA_EXTRAIDA','revista')

def ocr_extract(pdf_bytes,pages,rotations):
    return extract_candidates(pdf_bytes,pages,rotations)
