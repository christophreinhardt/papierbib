"""Strict ISBN-only recognition. Never repair digits or invent check digits."""
import re
import unicodedata


def normalize(value):
    value = unicodedata.normalize('NFKC', str(value or '')).strip().upper()
    value = re.sub(r'^ISBN(?:-1[03])?\s*:?\s*', '', value)
    return re.sub(r'[\s\-‐‑‒–—]', '', value)


def valid(value):
    value = normalize(value)
    if re.fullmatch(r'[0-9]{9}[0-9X]', value):
        return sum((10-i)*(10 if c == 'X' else int(c)) for i,c in enumerate(value)) % 11 == 0
    if re.fullmatch(r'97[89][0-9]{10}', value):
        return sum(int(c)*(1 if i % 2 == 0 else 3) for i,c in enumerate(value)) % 10 == 0
    return False


def canonical(value):
    value = normalize(value)
    if not valid(value):
        raise ValueError('Ungültige ISBN: Länge, Präfix oder Prüfziffer stimmt nicht.')
    if len(value) == 13:
        return value
    prefix = '978' + value[:9]
    return prefix + str(-sum(int(c)*(1 if i % 2 == 0 else 3) for i,c in enumerate(prefix)) % 10)


def isbn10(value):
    value = canonical(value)
    if not value.startswith('978'):
        return None
    digits = value[3:12]
    check = -sum((10-i)*int(c) for i,c in enumerate(digits)) % 11
    return digits + ('X' if check == 10 else str(check))


def extract(text):
    """Only whole ISBN-shaped tokens, never substrings of longer numbers."""
    text = unicodedata.normalize('NFKC', text or '').upper()
    text = re.sub(r'ISBN(?:-1[03])?\s*:?\s*', ' ', text)
    found = []
    for line in text.splitlines():
        for match in re.finditer(r'(?<![0-9A-Z])[0-9][0-9X\s\-‐‑‒–—]*[0-9X](?![0-9A-Z])', line):
            value = normalize(match.group())
            if valid(value):
                value = canonical(value)
                if value not in found:
                    found.append(value)
    return found[:10]
