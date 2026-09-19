# Testbericht Phase 1 – Version 0.2.0

Stand: 19. September 2026. Ausschließlich synthetische Bilder, temporäre
Datenbanken und öffentliche Testpasswörter; keine kostenpflichtigen API-Aufrufe.

## Ergebnisse

| Prüfung | Ergebnis |
|---|---|
| Python-Backendtests (Windows, Python 3.13) | 15 bestanden |
| Node-Zuschnittgeometrie | 3 bestanden |
| Chromium, iPhone-Viewport | Browserablauf bestanden |
| WebKit, iPhone-Viewport | Browserablauf bestanden |
| Docker Linux/amd64, Python 3.12 | Image gebaut; Container-Smoke bestanden |
| Docker Linux/arm64 | Image gebaut; Container gestartet; Health erfolgreich |
| Bestehende Calibre-Tests | 147 von 148 bestanden; bestehender Versions-Testfehler |
| git diff --check | Keine Whitespace-Fehler |

Backendprüfungen umfassen Anmeldung, Cookie-Eigenschaften, Origin-Schutz,
Sitzungsablauf, Passwortwechsel, Rate-Limits, Uploadgrenzen, beschädigte Bilder,
Zustimmung, EXIF-Rotation, Zuschnittvalidierung, Transaktionen, Revisionen und
Neustart-Persistenz. Originalbytes werden unverändert erhalten.

Browserabläufe mit Playwright 1.63.0 prüfen Anmeldung, Projekte, Dateiimport,
Mausziehen des Rahmens, Prozentfelder, Drehen, Zoom, Speicherzustimmung,
Revisionen, Neuladen, Cookie-Schutz und die offline verfügbare Oberfläche.
Chromium nutzt Offline-Emulation; für WebKit wird der lokale Testserver beendet,
weil dessen Windows-Offline-Emulation beim Neuladen einen internen Browserfehler
auslöste. Beide Varianten prüfen anschließend die Service-Worker-Oberfläche
und lokale Bildbearbeitung ohne erreichbares Backend.
Screenshots: `test-results/mobile/` (nicht versioniert), zusätzlich CI-Artefakte.

Der Compose-Test überprüft nichtprivilegierten Betrieb, Schreiben im Volume,
Originaldownload, Zuschnitt, Authentifizierung und Daten nach Container-Neustart.
ARM64 wurde lokal emuliert, nicht auf einem echten OrbStack-Mac ausgeführt.

Der unveränderte Calibre-Test `tests/test_photo_deletion.py:141` erwartet
Version 0.6.10, während das bestehende Plugin bereits 0.6.11 angibt. Diese
Abweichung besteht auch im vorherigen Git-Stand. Weder Plugin noch dessen
Tests wurden für diese mobile Phase geändert.

## Reproduzieren

Aus dem Repository-Verzeichnis, nach Installation gemäß README:

```sh
python -m unittest discover -s mobile_backend/tests -v
node --test mobile_backend/tests/crop.test.mjs
python -m mobile_backend.tests.browser_smoke
docker build -t papierbib-mobile:0.2.0 mobile_backend
docker buildx build --platform linux/arm64 --load -t papierbib-mobile:0.2.0-arm64 mobile_backend
```

Container-Smoke (separater Teststack, keine produktiven Daten):

```sh
export PAPIERBIB_PASSWORD=only-for-isolated-container-test
export PUBLIC_ORIGIN=https://papierbib.test
docker compose -p papierbib-phase1-test -f mobile_backend/docker-compose.yml -f mobile_backend/tests/compose.smoke.yml up -d --no-build
python -m mobile_backend.tests.container_smoke
docker compose -p papierbib-phase1-test -f mobile_backend/docker-compose.yml -f mobile_backend/tests/compose.smoke.yml down
```

Der Test behält sein synthetisches Datenvolume. Die neue GitHub-Workflowdatei
führt Backend-, Geometrie-, Browser- und amd64-Containertests automatisch aus.

## Geänderte und neue Dateien

Geändert: `.gitignore`, `README.md`, `mobile_web/README.md` sowie die unten
mit `(geändert)` markierten Backenddateien. Alle übrigen Einträge sind neu.
`mobile_backend/app.py` und der Calibre-Quellcode bleiben unverändert.

```text
.github/workflows/mobile-tests.yml
mobile_backend/
  .dockerignore
  .env.example                    (geändert)
  __init__.py
  ARCHITECTURE.md
  README.md                       (geändert)
  TEST_REPORT.md
  Dockerfile                      (geändert)
  docker-compose.yml              (geändert)
  requirements.txt                (geändert)
  requirements-dev.txt
  config.py
  images.py
  server.py
  storage.py
  tools/make_icons.py
  tests/
    test_backend.py
    crop.test.mjs
    browser_smoke.py
    container_smoke.py
    compose.smoke.yml
  web/
    index.html
    style.css
    app.mjs
    crop.mjs
    sw.js
    manifest.webmanifest
    icon.svg
    icon-192.png
    icon-512.png
```

## Noch nicht verifiziert / nicht implementiert

- Physisches iPhone, echte Kameraauflösung, Safari-PWA-Installation und
  Touch-Gesten müssen auf dem Zielgerät abgenommen werden.
- Portainer auf OrbStack und der konkrete HTTPS-/Tailscale-Proxy des Nutzers
  wurden nicht ferngesteuert eingerichtet oder getestet.
- Offline keine dauerhafte Speicherung privater Fotos; nur Oberfläche und
  Bearbeitung im Arbeitsspeicher. HEIC wird nicht unterstützt.
- Phase 2: Barcode, ISBN-only-OCR, lobid und Metadatenprüfung.
- Phase 3: neue sichere OpenAI-/Gemini-Adapter und strukturierte Auswertung.
- Phase 4: mehrere Buchrücken und bearbeitbare Mehrfachrahmen.
- Phase 5: Calibre-kompatibler Export einschließlich Bildern sowie Migration
  alter mobiler Exporte. Aktuell noch kein mobiler Calibre-Importweg.

Die Implementierung ist eine getestete Phase-1-Grundlage, keine Behauptung
einer bereits auf dem konkreten iPhone abgenommenen Gesamtlösung.
