# Testbericht Phase 3 - Version 0.4.0

Stand: 2026-09-19

## Automatisierte Tests

Ausgefuehrt im Repository:

```sh
python -m unittest discover -s mobile_backend/tests -v
node --test mobile_backend/tests/crop.test.mjs mobile_backend/tests/isbn.test.mjs
```

Ergebnis: 40 Python-Tests und 6 JavaScript-Tests bestanden.

Abgedeckt sind insbesondere:

- OpenAI- und Gemini-Anfrageformate mit gemocktem Netzwerk;
- keine API-Schluessel in Statusantworten oder im Request-Body;
- strikte JSON-Validierung, Konfidenzgrenzen und ISBN-10/13-Konsistenz;
- explizite Zustimmung, Aufnahmeart, Rate-Limit und keine Bildpersistenz durch
  die KI-Endpunktlogik;
- bestehende Kamera-, Crop-, Barcode-, ISBN-only-OCR-, lobid- und
  Speicherungstests.

## Nicht Bestandteil dieses Testberichts

Es wurde absichtlich kein echter KI-API-Aufruf ausgefuehrt: Das vermeidet Kosten
und private Bilduebertragungen. Vor der produktiven Nutzung sollten ein eigener
Test-Buchruecken und ein Titelblatt mit dem in Portainer hinterlegten Anbieter
geprueft werden.
