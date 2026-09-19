"""Google Gemini Developer API adapter; no SDK dependency or OpenAI compatibility proxy."""
import base64
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .provider import VisionProvider, NoRedirect, PROMPT
from .schema import EXTRACTION_SCHEMA, VisionError, VisionCancelled, strict_json, validate_extraction

DEFAULT_GEMINI_MODEL = 'gemini-3.5-flash-lite'
GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/models/'


def request_schema(value):
    """Keep the strict structure; enforce numeric/array limits in the local validator.

    Some Gemini deployments reject bounded nested array schemas even though the
    same constraints are documented. Never relax the validation of returned data.
    """
    if isinstance(value, dict):
        return {key: request_schema(item) for key, item in value.items()
                if key not in ('minimum', 'maximum', 'minItems', 'maxItems')}
    if isinstance(value, list):
        return [request_schema(item) for item in value]
    return value


def parse_response(data, validator=validate_extraction):
    if not isinstance(data, dict) or data.get('error'):
        raise VisionError('Gemini hat die Auswertung nicht vollständig beendet oder abgelehnt. Bitte Bild und Modell prüfen.')
    try:
        if data.get('promptFeedback', {}).get('blockReason'):
            raise ValueError()
        candidates = data['candidates']
        if not isinstance(candidates, list) or len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
            raise ValueError()
        parts = candidates[0]['content']['parts']
        if not isinstance(parts, list) or not parts:
            raise ValueError()
        parts = [p for p in parts if p.get('thought') is not True]
        if not parts or any(not isinstance(p.get('text'), str) or any(k in p for k in ('functionCall','functionResponse','inlineData','fileData','executableCode','codeExecutionResult')) for p in parts):
            raise ValueError()
        text = ''.join(p['text'] for p in parts)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise VisionError('Gemini lieferte kein eindeutiges Textergebnis. Die Antwort wurde nicht übernommen.') from None
    return validator(strict_json(text))


class GeminiVisionProvider(VisionProvider):
    def __init__(self, api_key, model=DEFAULT_GEMINI_MODEL, timeout=45, transport=None):
        self._key = api_key.strip() if isinstance(api_key, str) else ''
        if not self._key:
            raise VisionError('GEMINI_API_KEY fehlt. Schlüssel in der Umgebung setzen oder in den KI-Einstellungen für diese Sitzung eingeben.')
        if any(ord(c) < 33 or ord(c) > 126 for c in self._key):
            raise VisionError('Der Gemini-API-Schlüssel enthält ungültige Zeichen.')
        if not isinstance(model, str) or not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', model):
            raise VisionError('Ungültiger Gemini-Modellname. Bitte eine Modell-ID beginnend mit gemini- eingeben.')
        self.model, self.timeout = model, timeout
        self.transport = transport or build_opener(NoRedirect()).open

    def analyze(self, jpeg, *, consent, cancel):
        return self._request(jpeg, consent=consent, cancel=cancel, prompt=PROMPT,
                             schema=EXTRACTION_SCHEMA, validator=validate_extraction, limit=3000)

    def detect_shelf(self, jpeg, *, consent, cancel):
        from .shelf import SHELF_SCHEMA, SHELF_PROMPT, validate_shelf
        return self._request(jpeg, consent=consent, cancel=cancel, prompt=SHELF_PROMPT,
                             schema=SHELF_SCHEMA, validator=validate_shelf, limit=12000)

    def scan_identifier(self, jpeg, *, consent, cancel):
        from .identifier import IDENTIFIER_SCHEMA, IDENTIFIER_PROMPT, validate_identifier
        return self._request(jpeg, consent=consent, cancel=cancel, prompt=IDENTIFIER_PROMPT,
                             schema=IDENTIFIER_SCHEMA, validator=validate_identifier, limit=2500)

    def _request(self, jpeg, *, consent, cancel, prompt, schema, validator, limit):
        if consent is not True:
            raise VisionError('Der Bildübertragung an Google Gemini wurde nicht zugestimmt.')
        if cancel.is_set():
            raise VisionCancelled('Gemini-Auswertung abgebrochen.')
        if not isinstance(jpeg, bytes) or not jpeg.startswith(b'\xff\xd8') or len(jpeg) > 10*1024*1024:
            raise VisionError('Der Ausschnitt muss ein JPEG unter 10 MB sein.')
        payload = {'contents': [{'role': 'user', 'parts': [{'text': prompt},
                   {'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(jpeg).decode('ascii')}}]}],
                   'generationConfig': {'responseMimeType': 'application/json', 'responseJsonSchema': request_schema(schema),
                                        'maxOutputTokens': limit, 'candidateCount': 1}}
        request = Request(GEMINI_ENDPOINT + self.model + ':generateContent', data=json.dumps(payload).encode('utf-8'), method='POST',
                          headers={'x-goog-api-key': self._key, 'Content-Type': 'application/json'})
        if cancel.is_set():
            raise VisionCancelled('Gemini-Auswertung abgebrochen.')
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read(2*1024*1024+1)
            if len(raw) > 2*1024*1024:
                raise VisionError('Die Gemini-Antwort ist unerwartet groß.')
            data = strict_json(raw)
        except HTTPError as exc:
            code = exc.code
            exc.close()
            messages = {400: 'Gemini-Anfrage abgelehnt. Bitte API-Schlüssel sowie Bild-/Schema-Unterstützung des Modells prüfen.',
                        401: 'Der Gemini-API-Schlüssel wird nicht akzeptiert.',
                        403: 'Kein Zugriff auf Gemini. Bitte Schlüssel, API-Freigabe und Region prüfen.',
                        404: 'Gemini-Modell oder API nicht verfügbar. Bitte Modell in den Einstellungen prüfen.',
                        429: 'Gemini-Kontingent oder Anfragelimit erreicht. Bitte Abrechnung/Limits prüfen und später erneut versuchen.'}
            raise VisionError(messages.get(code, 'Gemini ist momentan nicht erreichbar. Bitte später erneut versuchen.')) from None
        except (URLError, OSError, UnicodeError):
            raise VisionError('Netzwerk-, TLS- oder Zeitüberschreitungsfehler bei der Gemini-Verbindung.') from None
        except VisionError:
            raise
        except Exception:
            raise VisionError('Die Gemini-Verbindung lieferte einen unerwarteten Fehler.') from None
        if cancel.is_set():
            raise VisionCancelled('Gemini-Auswertung abgebrochen; eine gesendete Anfrage kann Kosten verursacht haben.')
        extraction = parse_response(data, validator)
        usage = data.get('usageMetadata') or {}
        mapping = {'input_tokens': 'promptTokenCount', 'output_tokens': 'candidatesTokenCount', 'total_tokens': 'totalTokenCount'}
        tokens = {key: usage[source] for key, source in mapping.items()
                  if isinstance(usage, dict) and type(usage.get(source)) is int and usage[source] >= 0}
        return {'provider': 'gemini', 'model': self.model, 'extraction': extraction, 'usage': tokens}
