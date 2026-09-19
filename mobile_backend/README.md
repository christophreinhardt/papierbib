# Papierbibliothek mobil — selbst gehostet, Version 0.4.0

Phase 3 ergänzt die Foto-/Projektverwaltung um lokale Barcode-Erkennung,
ISBN-only-OCR, lobid-Abgleich sowie sichere KI-Auswertung einzelner Buchrücken
und Titelblätter.

**Bestehende Installation aktualisieren:** [Portainer-/Cloudflare-Update](PORTAINER-UPDATE.md).
Der Container liefert Web-App und API unter **derselben Adresse** aus.
Es gibt keine Backend-URL und kein API-Token-Feld mehr im Browser.

Enthalten: Anmeldung, Projekte, Rückkamera und native Fotoaufnahme, Drehen,
Zoomen, manuelles Zuschneiden, Originalspeicherung, Zuschnitt-Versionen,
SQLite-Persistenz, eine offline ladbare Oberfläche, lokale Barcode-Worker,
ISBN-Prüfziffern, Tesseract im Homeserver und eine editierbare Trefferprüfung.

**Noch nicht enthalten:** Regalerkennung und Calibre-Export im neuen Dienst.
Diese folgen in Phase 4–5. Die alte Anwendung bleibt im
Quellcode erhalten; sie ist kein Teil des neuen Container-Images.

## Wechsel von Version 0.1.0

1. In der bisherigen GitHub-Pages-App vorhandene Browserdaten als JSON exportieren.
   Diese Daten liegen ausschließlich im jeweiligen Browser. Das frühere Exportformat
   ist **kein direkt kompatibles Calibre-Projekt**. Datei aufbewahren; Migration folgt.
2. Ein laufender 0.1.0-Container hatte keine serverseitigen Projekte.
3. Vor „Pull and redeploy“ in Portainer die neuen Variablen setzen:
   `PAPIERBIB_PASSWORD` und `PUBLIC_ORIGIN`. Ein automatisches Git-Redeploy
   sollte erst nach dieser Konfiguration erfolgen.
4. Die neue Oberfläche auf der Homeserver-Adresse öffnen. GitHub Pages ist
   weiterhin nur die alte Anwendung. Alten Home-Bildschirm-Link durch den neuen ersetzen.
5. Das Calibre-Plugin und dessen Projektdateien bleiben unverändert.

## Portainer / OrbStack: empfohlen mit Tailscale

Auf dem Mac muss OrbStack laufen; Portainer muss dessen **Docker-Standalone**
Environment verwalten, nicht einen Swarm.

1. **Stacks → bisherigen Stack öffnen → Git-Konfiguration**:
   - Repository: `https://github.com/christophreinhardt/papierbib.git`
   - Git-Authentifizierung aus (öffentliches Repository).
   - Reference: `refs/heads/main`
   - Compose path: `mobile_backend/docker-compose.yml`
2. Unter **Environment variables** setzen:

   | Variable | Wert |
   |---|---|
   | PAPIERBIB_PASSWORD | Ein eigenes Passwort mit mindestens 16 Zeichen |
   | PUBLIC_ORIGIN | z. B. `https://homeserver.dein-tailnet.ts.net` |
   | HOST_BIND | `127.0.0.1` |
   | MAX_IMAGE_BYTES | optional, Standard `20971520` (20 MiB) |
   | AI_PROVIDER | optional: `openai` oder `gemini`; Standard `openai` |
   | OPENAI_API_KEY | nur bei OpenAI-KI-Auswertung; sonst leer lassen |
   | OPENAI_VISION_MODEL | optional; Standard `gpt-4o-mini` |
   | GEMINI_API_KEY | nur bei Gemini-KI-Auswertung; sonst leer lassen |
   | GEMINI_VISION_MODEL | optional; Standard `gemini-2.0-flash` |

   `PUBLIC_ORIGIN` ist die exakte Adresse der **neuen** App, ohne Pfad oder
   abschließenden Slash. Nicht die GitHub-Pages-Adresse verwenden.
   Das Passwort ist das Anmeldepasswort in der App. Für KI-Auswertung zusätzlich genau den Schlüssel des gewählten Anbieters setzen.

   Ein zufälliges Passwort lässt sich auf dem Mac mit `openssl rand -hex 24`
   erzeugen. Nur in Portainer und deinem Passwortmanager hinterlegen.
3. **Pull and redeploy / Deploy the stack** ausführen. Portainer baut das Image
   aus `mobile_backend/Dockerfile`. Der Container heißt weiterhin `papierbib-api`.
4. Auf dem Mac testen:

   ```sh
   curl http://127.0.0.1:8888/api/health
   ```

   Erwartet: `{"ok":true,"version":"0.4.0","phase":3}`.
5. Tailscale auf Mac und iPhone mit demselben Tailnet verbinden.
   Auf dem Mac (mit verfügbarer Tailscale-CLI):

   ```sh
   tailscale serve --bg http://127.0.0.1:8888
   tailscale serve status
   ```

   Falls Serve bereits einen anderen Dienst auf Port 443 bedient, eine eigene
   HTTPS-Port-Zuordnung wählen und diese auch in `PUBLIC_ORIGIN` eintragen.
   Tailscale zeigt gegebenenfalls einen Link zur einmaligen HTTPS-Freigabe.
   Die von Serve angezeigte HTTPS-Adresse muss exakt `PUBLIC_ORIGIN` entsprechen.
6. Diese HTTPS-Adresse in Safari auf dem iPhone öffnen, Passwort eingeben.
   Dann **Teilen → Zum Home-Bildschirm**.

Nur innerhalb des Tailnets erreichbar. Kein Tailscale Funnel und keine
Router-Portfreigabe erforderlich. Docker-Port **8888** wird standardmäßig nur
an die Loopback-Adresse des Homeservers gebunden.

### Wenn der Portainer-Git-Build fehlschlägt

Auf dem OrbStack-Mac explizit mit demselben Image-Namen bauen:

```sh
git clone https://github.com/christophreinhardt/papierbib.git
cd papierbib
docker build -t papierbib-mobile:0.4.0 mobile_backend
```

In einem Portainer-Webeditor-Stack den Inhalt von
`mobile_backend/docker-compose.yml` verwenden und **nur `build: .` entfernen**.
`image: papierbib-mobile:0.4.0` bleibt stehen; darunter `pull_policy: never`
ergänzen und beim Update **Re-pull image ausschalten**. Das Image muss auf demselben
Docker-Environment liegen, das Portainer verwaltet. Beim nächsten Update erst
`git pull --ff-only`, erneut bauen und den Stack neu bereitstellen.

Die Architektur des Hosts wird beim lokalen Build automatisch verwendet,
einschließlich Apple Silicon. Zusätzliche Git-Volume-Funktionen werden nicht benötigt.

## Alternative: eigener HTTPS-Reverse-Proxy / Caddy

Wenn Caddy auf dem Host läuft, genügt ein Caddyfile mit eigener Domain:

```caddyfile
papierbib.example.org {
    reverse_proxy 127.0.0.1:8888
}
```

Dazu `PUBLIC_ORIGIN=https://papierbib.example.org` setzen. DNS, Erreichbarkeit
und Zertifikatausstellung für die eigene Domain müssen eingerichtet sein.

Läuft der Proxy als Container, muss er im selben Docker-Netz sein und an
`papierbib-api:8080` weiterleiten. `127.0.0.1` innerhalb des Proxy-Containers
zeigt nicht auf den Papierbib-Container. Den App-Port dafür nicht öffentlich öffnen.

Normales `http://192.168...:8888` reicht für die iPhone-Livekamera nicht.
Die App verwendet in Produktion ausschließlich sichere Cookies über HTTPS.

## Verwendung

1. Anmelden, Projekt anlegen oder wählen.
2. Aufnahmeart wählen: ISBN/Barcode, Buchrücken, Titelblatt oder Regalfoto.
3. **Kamera starten → Foto aufnehmen** oder **iPhone-Kamera / Foto** bzw.
   **Foto auswählen**.
4. Foto mit ±90° oder dem Regler **Frei drehen** in 0,5°-Schritten ausrichten.
   Rahmen an den Ecken ändern, verschieben oder
   außerhalb einen neuen Rahmen ziehen. Der Zoomregler vergrößert nur die Ansicht;
   im vergrößerten Bild kann gescrollt werden. Prozentfelder erlauben genaue Eingaben.
5. Vorschau prüfen. Zum Upload das Kästchen **Original und Zuschnitt auf meinem
   Homeserver speichern** aktivieren und speichern.
6. In der Fotoliste eine Zuschnitt-Version wählen. **Original öffnen / bearbeiten**
   lädt immer das unveränderte Original; Speichern erzeugt eine neue Version.

Live-Videoframes haben nur die tatsächlich vom Browser gelieferte Auflösung.
Der separate native Kamera-Button ist für hochauflösende iPhone-Fotos vorgesehen.
JPEG, PNG und WebP bis 20 MiB / 50 Megapixel; HEIC vorher als JPEG exportieren.
Die Zuschnitte werden serverseitig aus der vollen Originalauflösung erzeugt.
Die Editoransicht ist auf 2200 Pixel begrenzt, ohne die gespeicherte Auflösung zu begrenzen.

Ohne Speicherzustimmung findet **kein Bild-Upload** statt. Die Aufnahme liegt
nur im Arbeitsspeicher des Tabs und geht beim Schließen/Neuladen verloren.
Offline funktionieren Oberfläche, Fotoauswahl und Editor; Serverprojekte und
Speichern benötigen die Verbindung. Kein stilles Zwischenspeichern privater Bilder.

## ISBN-Erkennung und Prüfung

- Live-Kamera bei Aufnahmeart ISBN / Barcode: gültige Buch-ISBN stoppt die Kamera
  und startet die lobid-Suche. Kein Live-Frame verlässt das iPhone.
- Foto: zuerst manuell den ISBN-Bereich zuschneiden, dann **Ausschnitt bestätigen
  und ISBN erkennen**. Barcode zuerst, ISBN-only-OCR als Fallback. Nur der
  Ausschnitt wird temporär im Homeserver verarbeitet. Kein Speicherhäkchen nötig.
- Nummer prüfen, **Bei lobid suchen**, einen Treffer ausdrücklich übernehmen,
  korrigieren und **Speichern und bestätigen** oder **Als Entwurf speichern**.
- Eine gültige ISBN bleibt auch ohne Online-Treffer speicherbar. Autoren und
  Herausgeber sind getrennt. Unterschiedliche Auflagen werden nicht vermischt.
- **Nächstes Buch** beginnt einen neuen Datensatz. Bereits vorhandene ISBNs
  führen zu einer Warnung; dasselbe geöffnete Buch wird beim Speichern aktualisiert.
- Metadaten stehen unter **Erfasste Bücher**, Fotos separat unter **Gespeicherte
  Fotos**. Noch kein Import dieser Datensätze in Calibre (Phase 5).

Eine öffentliche Referenz-ISBN für einen Funktionstest: `0256018243`
(`9780256018240`, Labor economics). Externe Verfügbarkeit ist nicht garantiert.

## Anmeldung und Datenschutz

- Ein privater Haushalt / eine gemeinsame Bibliothek, keine Mehrbenutzerrechte.
- Passwort im Server-Environment; Eingabe einmal pro Sitzung.
- Zufälliges Sitzungscookie, `HttpOnly`, `Secure`, `SameSite=Strict`, 12 Stunden.
  JavaScript kann es nicht lesen. Ein Browser benötigt dieses Sitzungsmerkmal;
  eine Authentifizierung ganz ohne irgendeinen Browser-Nachweis wäre nicht möglich.
- Keine dauerhaften API-Token oder Provider-Schlüssel in JavaScript, LocalStorage,
  SessionStorage, Git, Antworten oder Exporten.
- Serverseitig nur Sitzungshashes. Passwortänderung macht bestehende Sitzungen ungültig.
- Exakte Origin-Prüfung und eigener Header bei schreibenden Anfragen.
- Zehn Anmeldeversuche pro fünf Minuten (global), 240 API-Anfragen pro
  Sitzung/Minute. Rate-Limits werden in SQLite gespeichert.
- Bild-Uploads vor dem Decoder auf Größe begrenzt; 30 s Empfangszeitlimit,
  45 s Browserzeitlimit. Ein Bilddecoder gleichzeitig, ein Uvicorn-Worker.
- Keine Request-Access-Logs, keine Bilder/Secrets in Anwendungslogs.
- Keine CDNs oder Telemetrie. Nur ISBNs gehen bei Suchvorgängen an lobid.
  Ein Buchrücken- oder Titelblatt-Zuschnitt geht nur nach dem ausdrücklichen
  Klick auf **Kostenpflichtig auswerten** an den gewählten KI-Anbieter.
  OCR bleibt ausschließlich im Homeserver.
- Lokaler ZXing-Worker (Apache-2.0); Tesseract über stdin/stdout, 12 s Prozesslimit,
  ein Decoder gleichzeitig, zehn OCR-Anfragen pro Minute.
- lobid: feste HTTPS-Adresse, keine Weiterleitungen, 12 s Netzwerkzeitlimit,
  begrenzte JSON-Antwort, 30 Anfragen pro Minute, 24 h SQLite-Cache.
- Originale können EXIF/GPS-Daten enthalten und bleiben bewusst unverändert.
  Zuschnitte enthalten keine EXIF-Metadaten.
- Serverdaten sind nicht zusätzlich verschlüsselt: Homeserver und Backups absichern.
- `app.py` ist der archivierte 0.1-Gateway; er wird nicht ins Produktivimage kopiert.

## Daten, Updates und Sicherung

Das benannte Compose-Volume `<stackname>_papierbib_data` enthält die SQLite-Datei
`/data/papierbib.sqlite3` mit Projekten, Originalen, Zuschnitten und Sitzungen.
Buchdatensätze und lobid-Cache liegen ebenfalls in SQLite. Schema 1 wird beim
Start additiv auf Schema 2 erweitert; vorher ein Backup erstellen. Ein Downgrade
auf 0.2.0 verlangt eine alte Sicherung.
Original und erster Zuschnitt werden in einer Transaktion geschrieben.
Weitere Zuschnitte bleiben versioniert. Ein Container-Neustart oder Rebuild
erhält die Daten, sofern derselbe Stack-/Volumename verwendet wird.

Für ein konsistentes Backup: Stack stoppen, das **gesamte Volume** über die
Homeserver-/Volume-Sicherung sichern, Stack wieder starten. Bei laufender
Datenbank nicht nur die Hauptdatei kopieren; WAL-Dateien können noch Daten enthalten.
Für eine Wiederherstellung den Stack stoppen und das Volume aus einer geprüften
Sicherung wiederherstellen, Eigentümer UID/GID 10001 beibehalten.

Updates in Portainer per **Pull and redeploy**. Volume nicht löschen und nicht
`docker compose down -v` verwenden. Ein Löschen des Volumes löscht auch die Fotos.
Neue DB-Versionen werden nur durch ausdrückliche Migrationen unterstützt;
unbekannte Versionen verhindern einen Start, statt Daten zu überschreiben.

App-Updates werden über den Service Worker angekündigt. Erst speichern, dann
**Neue App-Version laden**. Der Cache enthält nur die öffentliche Oberfläche,
keine API-Antworten und keine Fotos.

## Entwicklung und Tests

Im Repository-Hauptverzeichnis:

```sh
python -m venv mobile_backend/.venv
# macOS/Linux:
source mobile_backend/.venv/bin/activate
# Windows: mobile_backend/.venv/Scripts/Activate.ps1
pip install -r mobile_backend/requirements-dev.txt
python mobile_backend/tools/make_icons.py mobile_backend/web
python -m unittest discover -s mobile_backend/tests -v
node --test mobile_backend/tests/crop.test.mjs mobile_backend/tests/isbn.test.mjs
python -m playwright install chromium webkit
python -m mobile_backend.tests.browser_smoke
python -m mobile_backend.tests.recognition_smoke
docker build -t papierbib-mobile:0.4.0 mobile_backend
```

Die Browsertests erzeugen synthetische Testbilder und eine temporäre Datenbank.
Screenshots liegen unter `test-results/mobile/`. Keine echten Fotos, Keys
oder externen KI-/Katalogaufrufe nötig.

Lokale HTTP-Entwicklung nur auf localhost:

```sh
export PAPIERBIB_PASSWORD='nur-fuer-lokale-entwicklung'
export PUBLIC_ORIGIN='http://127.0.0.1:8080'
export COOKIE_SECURE=false
export DATABASE_PATH='./mobile_backend/data/dev.sqlite3'
uvicorn mobile_backend.server:create_app --factory --host 127.0.0.1 --port 8080 --no-access-log
```

`COOKIE_SECURE=false` wird für LAN-/Internetadressen abgewiesen.

## Architektur und weitere Phasen

Siehe [ARCHITECTURE.md](ARCHITECTURE.md) für Analyse, Datenmodell,
Calibre-Mapping und Risiken. Aktueller Teststand:
[TEST_REPORT_PHASE3.md](TEST_REPORT_PHASE3.md); vorheriger Stand:
[TEST_REPORT.md](TEST_REPORT.md).

Offen: Regalfoto-Trennung/Mehrfachrahmen (Phase 4), vollständige Projektpakete für
Calibre und Migration alter mobiler Exporte (Phase 5).
