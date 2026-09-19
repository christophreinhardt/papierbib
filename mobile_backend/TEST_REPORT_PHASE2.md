# Testbericht Phase 2 – Version 0.3.1

Stand: 19. September 2026. Keine privaten Fotos, echten Zugangsdaten oder
kostenpflichtigen KI-Aufrufe. Calibre-Code und GitHub-Pages-Prototyp unverändert.

## Ergebnisse

| Prüfung | Ergebnis |
|---|---|
| Python-Backendtests, Windows / Python 3.13 | 32 bestanden |
| Node: Zuschnittgeometrie und ISBN | 5 bestanden |
| Chromium + WebKit: bestehender Fotoablauf | Beide bestanden |
| Chromium + WebKit: Erkennungsablauf | Beide bestanden |
| Docker Linux/amd64, Python 3.12 | Image gebaut, Container-Smoke bestanden |
| Echte Tesseract-OCR im Docker-Image | Synthetische ISBN korrekt erkannt |
| Container-Neustart | Originalfoto und ISBN-Entwurf erhalten |
| Reale lobid-ISBN-Abfrage | `0256018243` → ein Treffer „Labor economics“, `9780256018240` |
| ARM64-Build | Lokal blockiert: `exec format error`, siehe unten |

## Getestete Fälle

- ISBN-10, ISBN-13, X-Prüfziffer, Unicode-Ziffern und Bindestriche, ungültige
  Prüfziffern, beliebige Nicht-ISBN-Barcodes; keine erfundenen Korrekturen.
- Echter EAN-13-Testbarcode mit dem ausgelieferten ZXing-Worker in beiden
  Browsern; erfolgreicher Barcode verursacht keinen OCR-Bildupload.
- Leeres Bild löst OCR-Fallback aus. Vom 800×600-Testbild kommt nach dem
  halben Zuschnitt nur 400×300 beim OCR-Aufruf an.
- OCR- und Katalogaufrufe im Browsertest gemockt. Katalogtreffer wird ausdrücklich
  übernommen und bestätigt; simuliertes Offline-lobid lässt ISBN-Entwurf zu.
- Metadaten überstehen Neuladen; Erkennung allein speichert kein Foto.
- Echte Tesseract-OCR separat im schreibgeschützten Nicht-Root-Container;
  synthetische gedruckte Zeile `ISBN 978-0-306-40615-7`, keine Test-Mocks.
- Parser gegen unveränderte offizielle CC0-hbz-Fixture, Quellenlink und Stand
  in `tests/fixtures/README.md`; Autoren und Herausgeber getrennt.
- Verschiedene Auflagen bleiben getrennt, falsche ISBN-Treffer werden verworfen.
- Timeouts, ungültiges JSON, HTML-Zugriffsschutz, Antwortgrößenlimit und Caching.
- Anmeldung, Origin-Schutz, Rate-Limits, abgelehnte Uploads und fehlende
  Crop-Bestätigung; kein OCR-Rohtext in der API-Antwort.
- Schema-1-Migration erhält Originalbytes; Schreibvorgänge prüfen Projekt-/
  Foto-/Crop-Zuordnung; wiederholte Datensatz-ID erzeugt keine Dublette.
- Vorhandener Phase-1-Ablauf einschließlich Offline-Oberfläche erneut geprüft.

Die Live-Abfrage ist getrennt von deterministischen Tests. lobid lieferte bei
einzelnen Anfragen auch HTML-Zugriffsschutz statt JSON; kein Umgehungsversuch.
Dieser Fall wird als Ausfall angezeigt, die ISBN bleibt speicherbar.

## Reproduzieren

```sh
python -m unittest discover -s mobile_backend/tests -v
node --test mobile_backend/tests/crop.test.mjs mobile_backend/tests/isbn.test.mjs
python -m mobile_backend.tests.browser_smoke
python -m mobile_backend.tests.recognition_smoke
docker build -t papierbib-mobile:0.3.1 mobile_backend
```

Container-Smoke wie im vorherigen Bericht, mit dem aktualisierten Compose-Image:

```sh
export PAPIERBIB_PASSWORD=only-for-isolated-container-test
export PUBLIC_ORIGIN=https://papierbib.test
docker compose -p papierbib-phase2-test -f mobile_backend/docker-compose.yml -f mobile_backend/tests/compose.smoke.yml up -d --no-build
python -m mobile_backend.tests.container_smoke
docker compose -p papierbib-phase2-test -f mobile_backend/docker-compose.yml -f mobile_backend/tests/compose.smoke.yml down
```

Screenshots unter `test-results/mobile/`; WebKit-Prüfansicht visuell kontrolliert.
Die CI führt dieselben automatisierten Tests aus; der Docker-Test verwendet
synthetische Bilder und echte lokale OCR, keinen externen Katalog.

## Geänderte / neue Dateien

Neu:

```text
mobile_backend/
  isbn.py, lobid.py, ocr.py, records.py
  PORTAINER-UPDATE.md, TEST_REPORT_PHASE2.md
  web/isbn.mjs, scanner.mjs, barcode-worker.js, recognition.mjs
  web/vendor/zxing-0.23.0.min.js, ZXING-LICENSE.txt, README.md
  tests/test_recognition.py, isbn.test.mjs, recognition_smoke.py
  tests/fixtures/lobid-990021367710206441.json, README.md
```

Geändert:

```text
README.md
.github/workflows/mobile-tests.yml
mobile_backend/
  README.md, ARCHITECTURE.md, .dockerignore, Dockerfile, docker-compose.yml
  config.py, server.py, storage.py
  tests/container_smoke.py
  web/app.mjs, crop.mjs, index.html, style.css, sw.js
```

## Grenzen / noch offen

- ARM64-Ausführung schlägt in der aktuellen lokalen Docker-Umgebung bereits
  bei `/bin/sh` fehl. Auch `uname` im unveränderten vorherigen ARM64-Image
  scheitert identisch. Keine Änderungen an globaler Docker-Emulation vorgenommen.
  Version 0.3.1 deshalb hier nicht als ARM64-getestet ausweisen; nativer Build
  auf dem OrbStack-Mac steht noch aus.
- Kein physisches iPhone, keine echte Kamera und kein Zugriff auf den
  Homeserver des Nutzers. WebKit mit iPhone-Viewport ersetzt keine Geräteabnahme.
- Livekamera-Loop ist implementiert; automatische Erkennung realer bewegter
  Kamerabilder muss am Gerät geprüft werden. Browsertests verwenden Bilddateien.
- Barcodebibliothek befindet sich upstream im Maintenance-Modus; fest
  versioniert und lokal bereitgestellt. Unscharfe/kleine Barcodes und schräge
  Schrift können manuelle Eingabe erfordern. Kein OCR-Erfolgsversprechen.
- Die Korrektur 0.3.1 ergänzt freie Drehung (0,5°-Schritte) und wird im
  Browserablauf mit 17,5° und anschließendem 90°-Zuschnitt geprüft.
- KI für Titel/Autor (Phase 3), Regaltrennung (Phase 4), Calibre-Export und
  Migration alter mobiler Exporte (Phase 5) noch nicht implementiert.
- Calibre-Tests nicht erneut ausgeführt, da dessen Code unverändert bleibt;
  der vorher dokumentierte Versions-Testfehler bleibt unberührt.
