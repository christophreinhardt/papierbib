"""ISBN normalization and validation without external dependencies."""
import re


def normalize(value):
    return re.sub(r'[\s-]', '', value or '').upper()


def valid(value):
    value = normalize(value)
    if re.fullmatch(r'\d{9}[\dX]', value):
        return sum((10 - i) * (10 if c == 'X' else int(c)) for i, c in enumerate(value)) % 11 == 0
    if re.fullmatch(r'97[89]\d{10}', value):
        return sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(value)) % 10 == 0
    return False


def to_isbn13(value):
    value = normalize(value)
    if not valid(value):
        raise ValueError('Ungültige ISBN: Länge oder Prüfziffer stimmt nicht.')
    if len(value) == 13:
        return value
    prefix = '978' + value[:9]
    return prefix + str((-sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(prefix))) % 10)
