"""Capa de dominio: estructuras independientes de UI/OCR/Excel."""
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class Product:
    ean: str = ""
    name: str = ""
    brand: str = ""
    presentation: str = ""
    price: Optional[int] = None
    discount: Optional[float] = None
    page: Optional[int] = None
    source: str = ""
    confidence: str = ""
    notes: str = ""
    sku: str = ""
    validity_text: str = ""
    valid_from: str = ""
    valid_until: str = ""

    def as_dict(self):
        return asdict(self)

@dataclass
class Difference:
    status: str
    ean: str
    sku: str
    field: str
    magazine_value: str
    database_value: str
    page: Optional[int]
    product: str
    evidence: str
    severity: str = "MEDIA"

    def as_dict(self):
        return asdict(self)
