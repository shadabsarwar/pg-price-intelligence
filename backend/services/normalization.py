"""Conservative identity normalization. Original input is retained by the repository."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation


def clean(value: str | None) -> str:
    return ' '.join(re.sub(r'[^\w]+', ' ', unicodedata.normalize('NFKC', value or '').casefold()).split())


UNITS = {
    'ml': ('ml', Decimal('.001'), 'L'), 'milliliter': ('ml', Decimal('.001'), 'L'),
    'millilitres': ('ml', Decimal('.001'), 'L'), 'l': ('L', Decimal(1), 'L'),
    'liter': ('L', Decimal(1), 'L'), 'litre': ('L', Decimal(1), 'L'), 'litres': ('L', Decimal(1), 'L'),
    'liters': ('L', Decimal(1), 'L'), 'g': ('g', Decimal('.001'), 'kg'),
    'gram': ('g', Decimal('.001'), 'kg'), 'grams': ('g', Decimal('.001'), 'kg'), 'kg': ('kg', Decimal(1), 'kg'),
    'kilograms': ('kg', Decimal(1), 'kg'), 'diaper': ('diaper', Decimal(1), 'diaper'),
    'diapers': ('diaper', Decimal(1), 'diaper'), 'razor': ('razor', Decimal(1), 'razor'),
    'razors': ('razor', Decimal(1), 'razor'), 'refill': ('razor', Decimal(1), 'razor'),
    'refills': ('razor', Decimal(1), 'razor'),
}


def positive(value, label, maximum=100000):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label} must be a number') from None
    if not number.is_finite() or number <= 0 or number > maximum:
        raise ValueError(f'{label} must be positive and at most {maximum}')
    return number


def parse_quantity(size='', unit=None, pack_count=None):
    """Return per-item size and total in L/kg/count. Never infer diaper size as count."""
    if not str(size or '').strip():
        if unit or pack_count:
            raise ValueError('size is required when unit or pack_count is supplied')
        return None
    text = str(size).strip().casefold().replace('×', 'x')
    match = re.fullmatch(r'(?:(\d+)\s*x\s*)?(\d+(?:\.\d+)?)\s*([a-z]+)?', text)
    if not match:
        raise ValueError('Unparseable size; use e.g. 2 x 500 ml or size=500, unit=ml, pack_count=2')
    embedded_pack, amount, embedded_unit = match.groups()
    unit_key = (unit or embedded_unit or '').strip().casefold()
    if unit_key not in UNITS:
        raise ValueError('Unsupported or missing size unit')
    if unit and embedded_unit and UNITS.get(embedded_unit) != UNITS[unit_key]:
        raise ValueError('Conflicting size units')
    packs = positive(pack_count or embedded_pack or 1, 'pack_count', 10000)
    if packs != int(packs) or (embedded_pack and int(embedded_pack) != packs):
        raise ValueError('Conflicting or non-integer pack_count')
    amount = positive(amount, 'size')
    canonical, factor, dimension = UNITS[unit_key]
    total = amount * packs * factor
    if total > 100000:
        raise ValueError('Suspicious total quantity')
    return float(amount), canonical, int(packs), float(total), dimension


def normalized_name(name, brand):
    value, prefix = clean(name), clean(brand)
    return value[len(prefix) + 1:] if value.startswith(prefix + ' ') else value
