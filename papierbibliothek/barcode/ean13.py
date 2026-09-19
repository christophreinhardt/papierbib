"""Small dependency-free EAN-13 decoder specialized for ISBN camera frames."""
from ..isbn import valid


LEFT_ODD = {
    '0001101': '0', '0011001': '1', '0010011': '2', '0111101': '3',
    '0100011': '4', '0110001': '5', '0101111': '6', '0111011': '7',
    '0110111': '8', '0001011': '9',
}
LEFT_EVEN = {
    '0100111': '0', '0110011': '1', '0011011': '2', '0100001': '3',
    '0011101': '4', '0111001': '5', '0000101': '6', '0010001': '7',
    '0001001': '8', '0010111': '9',
}
RIGHT = {
    '1110010': '0', '1100110': '1', '1101100': '2', '1000010': '3',
    '1011100': '4', '1001110': '5', '1010000': '6', '1000100': '7',
    '1001000': '8', '1110100': '9',
}
PARITY = {
    'LLLLLL': '0', 'LLGLGG': '1', 'LLGGLG': '2', 'LLGGGL': '3',
    'LGLLGG': '4', 'LGGLLG': '5', 'LGGGLL': '6', 'LGLGLG': '7',
    'LGLGGL': '8', 'LGGLGL': '9',
}


def _pattern_widths(bits):
    """Return the four alternating run widths of a seven-module digit."""
    widths = []
    start = 0
    for index in range(1, len(bits) + 1):
        if index == len(bits) or bits[index] != bits[start]:
            widths.append(index - start)
            start = index
    return tuple(widths)


LEFT_ODD_WIDTHS = {digit: _pattern_widths(bits)
                   for bits, digit in LEFT_ODD.items()}
LEFT_EVEN_WIDTHS = {digit: _pattern_widths(bits)
                    for bits, digit in LEFT_EVEN.items()}
RIGHT_WIDTHS = {digit: _pattern_widths(bits)
                for bits, digit in RIGHT.items()}


def _valid_ean13(value):
    return (len(value) == 13 and value.isdigit() and
            sum(int(c) * (1 if i % 2 == 0 else 3)
                for i, c in enumerate(value)) % 10 == 0)


def encode_ean13(value):
    """Return ideal modules for tests and synthetic verification."""
    if not _valid_ean13(value):
        raise ValueError('Ungültige EAN-13.')
    parity = next(key for key, digit in PARITY.items() if digit == value[0])
    odd = {digit: bits for bits, digit in LEFT_ODD.items()}
    even = {digit: bits for bits, digit in LEFT_EVEN.items()}
    right = {digit: bits for bits, digit in RIGHT.items()}
    left = ''.join((odd if kind == 'L' else even)[digit]
                   for kind, digit in zip(parity, value[1:7]))
    return '101' + left + '01010' + ''.join(right[x] for x in value[7:]) + '101'


def _nearest(bits, table, max_errors=1):
    ranked = sorted((sum(a != b for a, b in zip(bits, pattern)), digit)
                    for pattern, digit in table.items())
    if not ranked or ranked[0][0] > max_errors:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0]


def decode_modules(bits):
    """Decode 95 sampled EAN modules, allowing minor resampling damage."""
    if len(bits) != 95:
        return None
    if sum(a != b for a, b in zip(bits[:3], '101')) > 1:
        return None
    if sum(a != b for a, b in zip(bits[45:50], '01010')) > 1:
        return None
    if sum(a != b for a, b in zip(bits[92:], '101')) > 1:
        return None
    digits, parity, errors = [], [], 0
    for index in range(6):
        chunk = bits[3 + index * 7:10 + index * 7]
        left_l, left_g = _nearest(chunk, LEFT_ODD), _nearest(chunk, LEFT_EVEN)
        choices = [(item[0], kind, item[1]) for kind, item in
                   (('L', left_l), ('G', left_g)) if item is not None]
        if not choices:
            return None
        choices.sort()
        if len(choices) > 1 and choices[0][0] == choices[1][0]:
            return None
        error, kind, digit = choices[0]
        errors += error
        parity.append(kind)
        digits.append(digit)
    first = PARITY.get(''.join(parity))
    if first is None:
        return None
    right_digits = []
    for index in range(6):
        chunk = bits[50 + index * 7:57 + index * 7]
        item = _nearest(chunk, RIGHT)
        if item is None:
            return None
        errors += item[0]
        right_digits.append(item[1])
    value = first + ''.join(digits + right_digits)
    if errors > 4 or not value.startswith(('978', '979')) or not valid(value):
        return None
    return value


def _runs(row):
    answer = []
    start = 0
    for index in range(1, len(row) + 1):
        if index == len(row) or row[index] != row[start]:
            answer.append((row[start], start, index))
            start = index
    return answer


def _nearest_run_digit(observed, tables, max_error=1.85):
    """Match four measured bars/spaces after local scale normalization."""
    total = float(sum(observed))
    if total <= 0:
        return None
    normalized = tuple(width * 7.0 / total for width in observed)
    ranked = []
    for kind, table in tables:
        for digit, expected in table.items():
            error = sum(abs(value - target)
                        for value, target in zip(normalized, expected))
            ranked.append((error, kind, digit))
    ranked.sort()
    if not ranked or ranked[0][0] > max_error:
        return None
    # An ambiguous digit is more dangerous than a missed frame: the camera will
    # simply try again, whereas a plausible wrong ISBN could trigger a lookup.
    if len(ranked) > 1 and ranked[1][0] - ranked[0][0] < .12:
        return None
    return ranked[0]


def _decode_run_window(window):
    """Decode the canonical 59 alternating runs of an EAN-13 symbol.

    Unlike fixed-width module sampling this normalizes every digit separately,
    so it tolerates perspective and a module width that changes across the image.
    """
    if len(window) != 59 or window[0][0] != 1:
        return None
    widths = [end - start for _, start, end in window]
    if min(widths) < 1:
        return None

    left_unit = sum(widths[3:27]) / 42.0
    right_unit = sum(widths[32:56]) / 42.0
    if left_unit <= 0 or right_unit <= 0:
        return None
    guard_checks = (
        (widths[0:3], left_unit),
        (widths[27:32], (left_unit + right_unit) / 2.0),
        (widths[56:59], right_unit),
    )
    for guard, unit in guard_checks:
        if any(not .35 <= width / unit <= 2.15 for width in guard):
            return None

    digits, parity, total_error = [], [], 0.0
    for index in range(6):
        group = widths[3 + index * 4:7 + index * 4]
        item = _nearest_run_digit(
            group, (('L', LEFT_ODD_WIDTHS), ('G', LEFT_EVEN_WIDTHS)))
        if item is None:
            return None
        error, kind, digit = item
        total_error += error
        parity.append(kind)
        digits.append(digit)
    first = PARITY.get(''.join(parity))
    if first is None:
        return None

    right_digits = []
    for index in range(6):
        group = widths[32 + index * 4:36 + index * 4]
        item = _nearest_run_digit(group, (('R', RIGHT_WIDTHS),))
        if item is None:
            return None
        error, _kind, digit = item
        total_error += error
        right_digits.append(digit)
    value = first + ''.join(digits + right_digits)
    if (total_error > 12.0 or not value.startswith(('978', '979')) or
            not valid(value)):
        return None
    return value


def _decode_binary_row(row):
    runs = _runs(row)
    # A complete EAN-13 consists of exactly 59 alternating runs. Search every
    # possible black start, since text and cover art may surround the barcode.
    # Rank cheap guard-pattern checks first and fully decode only a bounded
    # number. This prevents fine cover art from causing quadratic UI stalls.
    candidates = []
    for index in range(max(0, len(runs) - 58)):
        if runs[index][0] != 1:
            continue
        window = runs[index:index + 59]
        span = window[-1][2] - window[0][1]
        module = span / 95.0
        if module < 1.25:
            continue
        guard_indices = (0, 1, 2, 27, 28, 29, 30, 31, 56, 57, 58)
        ratios = [(window[pos][2] - window[pos][1]) / module
                  for pos in guard_indices]
        if any(not .30 <= ratio <= 2.40 for ratio in ratios):
            continue
        candidates.append((sum(abs(ratio - 1.0) for ratio in ratios), index))
    for _score, index in sorted(candidates)[:64]:
        value = _decode_run_window(runs[index:index + 59])
        if value:
            return value

    # Keep the fixed-module path as a useful fallback for slightly broken run
    # boundaries in otherwise straight, high-contrast images.
    guard_candidates = []
    for index in range(len(runs) - 2):
        first, middle, third = runs[index:index + 3]
        if (first[0], middle[0], third[0]) != (1, 0, 1):
            continue
        widths = [end - start for _, start, end in (first, middle, third)]
        if min(widths) < 1 or max(widths) > min(widths) * 2.2:
            continue
        base = sum(widths) / 3.0
        if base < 1.25:
            continue
        guard_candidates.append((max(widths) / min(widths), index, base))
    for _score, index, base in sorted(guard_candidates)[:64]:
        first = runs[index]
        for factor in (1.0, .97, 1.03, .94, 1.06):
            module = base * factor
            start = first[1]
            if start + module * 95 > len(row) + module:
                continue
            sampled = ''.join(
                '1' if row[min(len(row) - 1, int(start + (x + .5) * module))]
                else '0' for x in range(95))
            value = decode_modules(sampled)
            if value:
                return value
    return None


def decode_rows(rows):
    """Decode an ISBN EAN-13 from iterable 8-bit grayscale scanlines."""
    for grayscale in rows:
        if len(grayscale) < 95:
            continue
        ordered = sorted(grayscale)
        dark = ordered[len(ordered) // 10]
        light = ordered[len(ordered) * 9 // 10]
        if light - dark < 45:
            continue
        middle = (dark + light) // 2
        for threshold in (middle, middle - 15, middle + 15):
            row = [1 if value < threshold else 0 for value in grayscale]
            found = _decode_binary_row(row) or _decode_binary_row(row[::-1])
            if found:
                return found
    return None


def decode_qimage(image):
    """Decode from a QImage without retaining or transmitting the frame."""
    from qt.core import QImage, Qt

    if image is None or image.isNull():
        return None
    if image.width() > 1280 or image.height() > 900:
        image = image.scaled(1280, 900, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
    gray = image.convertToFormat(QImage.Format.Format_Grayscale8)
    data = gray.constBits().asstring(gray.sizeInBytes())
    stride, width, height = gray.bytesPerLine(), gray.width(), gray.height()
    positions = sorted(set(int(height * value) for value in
                           (.20, .28, .36, .44, .5, .56, .64, .72, .80)))
    rows = []
    # Diagonal scanlines make handheld rotation and perspective much less
    # sensitive. A three-pixel vertical average also suppresses sensor noise.
    for center in positions:
        for slope in (-.22, -.11, 0.0, .11, .22):
            row = bytearray(width)
            usable = True
            for x in range(width):
                y = int(center + slope * (x - width / 2.0))
                if not 1 <= y < height - 1:
                    usable = False
                    break
                row[x] = (data[(y - 1) * stride + x] +
                          data[y * stride + x] +
                          data[(y + 1) * stride + x]) // 3
            if usable:
                rows.append(row)
    return decode_rows(rows)
