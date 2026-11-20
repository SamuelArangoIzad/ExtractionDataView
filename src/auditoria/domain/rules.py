"""Configuración explícita de las reglas de auditoría, independiente de la UI."""
from dataclasses import asdict, dataclass
import math


FIELDS = ('DESCRIPCION', 'MARCA', 'PRESENTACION', 'PRECIO_COP', 'DESCUENTO_PCT', 'VIGENCIA')


@dataclass(frozen=True)
class AuditRules:
    fields: tuple[str, ...] = FIELDS
    price_tolerance: float = 0
    discount_tolerance: float = 0
    name_min_similarity: float = 0.82
    normalize_brand: bool = True
    equivalent_units: bool = True
    flag_missing: bool = True
    require_valid_gtin: bool = True

    def __post_init__(self):
        object.__setattr__(self, 'fields', tuple(self.fields))
        if not self.fields or set(self.fields) - set(FIELDS) or len(set(self.fields)) != len(self.fields):
            raise ValueError('Seleccione campos válidos, sin duplicados.')
        for name, upper in [('price_tolerance', None), ('discount_tolerance', 100),
                            ('name_min_similarity', 1)]:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f'{name} debe ser un número finito.')
            if value < 0 or (upper is not None and value > upper):
                raise ValueError(f'{name} está fuera de rango.')
        for name in ('normalize_brand', 'equivalent_units', 'flag_missing', 'require_valid_gtin'):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f'{name} debe ser booleano.')

    def as_dict(self):
        return asdict(self)
