# Update auf 0.4.1 – iPhone-SE-Oberfläche und Calibre-Export

Für den bereits funktionierenden Stack mit Cloudflare Tunnel. Calibre bleibt
unverändert. KI ist optional und benötigt genau einen API-Schlüssel im Backend.

## 1. Sichern

Den Papierbib-Stack stoppen, sein vollständiges Datenvolume sichern und wieder
starten. SQLite wird beim ersten Start von Schema 1 auf Schema 2 erweitert.
Fotos, Zuschnitt-Versionen und Projekte bleiben erhalten. Ein Rückwechsel auf
0.2.0 erfordert die alte Sicherung (nicht die migrierte Datenbank verwenden).

## 2. Auf dem Homeserver bauen

Im vorhandenen Repository-Verzeichnis, auf demselben Docker-Environment wie Portainer:

```sh
cd ~/papierbib
git pull --ff-only
docker build -t papierbib-mobile:0.4.1 mobile_backend
docker image inspect papierbib-mobile:0.4.1 --format '{{.Id}}'
```

Das Image enthält Tesseract und die lokal bereitgestellte Barcode-Bibliothek.
Es wird nicht aus einer öffentlichen Container-Registry heruntergeladen.

## 3. Bestehenden Portainer-Webeditor-Stack ändern

Nur die Image-Version ändern. `build: .` bleibt im Webeditor entfernt:

```yaml
services:
  papierbib-api:
    image: papierbib-mobile:0.4.1
    pull_policy: never
    container_name: papierbib-api
    # Alle bisherigen Einstellungen darunter unverändert behalten.
```

Dies ist nur ein Ausschnitt, kein vollständiger Stack. Passwort, PUBLIC_ORIGIN,
Port 8888, Volume und Netzwerke aus der bisherigen Konfiguration behalten.
**Update the stack**, dabei **Re-pull image ausschalten**. Datenvolume nicht löschen.

Bei einem Git-Stack, der lokal bauen kann, lautet der Compose-Pfad weiter
`mobile_backend/docker-compose.yml`; bei erzwungenem Registry-Pull den oben
beschriebenen Webeditor-Weg nutzen.

## 4. Cloudflare-Netzwerk prüfen

Cloudflared und papierbib-api müssen weiterhin im selben Docker-Netzwerk sein.
Die Cloudflare-Serviceadresse bleibt `http://papierbib-api:8080`.
PUBLIC_ORIGIN bleibt die exakte öffentliche HTTPS-Adresse ohne Pfad.

Eine nur über „Join a network“ angelegte Verbindung kann beim Neuerstellen
eines Containers verloren gehen. Gemeinsames Netzwerk deshalb in beiden
Compose-Stacks deklarieren; in bestehenden Netzwerkkonfigurationen ergänzen:

```yaml
services:
  papierbib-api:
    networks:
      - shared_tunnel
networks:
  shared_tunnel:
    external: true
    name: HIER_DEN_TATSAECHLICHEN_NETZWERKNAMEN_EINTRAGEN
```

Beim Cloudflare-Stack dieselbe externe Netzwerkdefinition dessen tatsächlichem
Servicenamen zuordnen. Bestehende Netzwerkzuordnungen behalten. Der Netzwerkname
muss in Portainer unter Networks bereits existieren; keine geratenen Namen benutzen.

## 5. Prüfen und benutzen

```sh
curl http://127.0.0.1:8888/api/health
```

Erwartet: `{"ok":true,"version":"0.4.1","phase":3}`.

Auf dem iPhone die App öffnen und gegebenenfalls **Neue App-Version laden**
wählen. Oben muss **0.4.1** stehen.

Projektwahl, KI-Anbieter und Export befinden sich jetzt unter **☰ Menü**. Die
Kamera versucht nach Anmeldung automatisch zu starten. Bei ISBN-Aufnahmen wird
zunächst lokal gescannt; nach sechs Sekunden ohne Treffer erscheint der runde
Fotoauslöser direkt im Kamerabild.

- Live: Aufnahmeart ISBN / Barcode, Kamera starten, Barcode ruhig ins Bild halten.
  Gültige ISBN stoppt den Scanner und startet lobid. Noch kein automatisches Speichern.
- Foto: ISBN-Text oder Barcode eng und waagerecht zuschneiden, dann
  **Ausschnitt bestätigen und ISBN erkennen**. Zuerst lokaler Barcodeversuch,
  sonst ISBN-only-OCR des Zuschnitts auf dem Homeserver.
- Erkannte ISBN prüfen; **Bei lobid suchen**, passenden Treffer ausdrücklich
  übernehmen, Felder prüfen, **Speichern und bestätigen**.
- Ohne Treffer: **Als Entwurf speichern**. Die gültige ISBN bleibt erhalten.
- Mit **Nächstes Buch** beginnt ein neuer Datensatz. Erneutes Speichern desselben
  geöffneten Datensatzes aktualisiert ihn; vorhandene ISBNs erzeugen eine Warnung.

Die reine Erkennung erfordert keine Speicherung des Fotos. Ohne separate
Speicherzustimmung werden keine Bilddateien oder OCR-Rohtexte dauerhaft gespeichert.
Metadaten werden erst beim Speichern des Buches in SQLite gesichert.

## 6. Optional: einen KI-Anbieter in Portainer aktivieren

Unter **Environment variables** genau eine der folgenden Varianten eintragen
und den Stack danach aktualisieren. API-Schlüssel nicht im YAML, nicht in Git
und nicht im Browser ablegen.

| Variante | Variablen |
|---|---|
| OpenAI | `AI_PROVIDER=openai`, `OPENAI_API_KEY=...`, optional `OPENAI_VISION_MODEL=gpt-4o-mini` |
| Gemini | `AI_PROVIDER=gemini`, `GEMINI_API_KEY=...`, optional `GEMINI_VISION_MODEL=gemini-2.0-flash` |

Danach bei Aufnahmeart **Buchrücken** oder **Titelblatt** ein Foto zuschneiden
und **Kostenpflichtig auswerten** wählen. Erst die explizite Bestätigung sendet
den aktuellen JPEG-Zuschnitt an den ausgewählten Anbieter. Der KI-Vorschlag ist
nicht automatisch gespeichert: Felder prüfen, optional per ISBN bei lobid suchen,
anschließend bestätigen oder als Entwurf sichern.

Der Schlüsselwert ist in `/api/vision/status`, Health, SQLite-Export und Logs nicht
enthalten. Ohne gültigen Schlüssel bleibt die Auswertung deaktiviert.

## Grenzen

Noch keine Regalfoto-Trennung und noch kein Exportpaket mit Fotos. Der reine
Metadatenexport für das Calibre-Plugin ist vorhanden. Der Regler **Frei drehen** korrigiert schiefe Fotos in
0,5°-Schritten; anschließend den ISBN-/Barcodebereich eng einrahmen.
OCR erkennt ausschließlich prüfziffergültige ISBNs und korrigiert keine vermuteten
Ziffern. Schlechte Beleuchtung, Unschärfe, kleine oder schräge Schrift können
eine manuelle ISBN-Eingabe erfordern. Physisches iPhone bitte selbst abnehmen.

lobid kann zeitweise ausfallen, begrenzen oder eine Zugriffsschutz-Seite liefern.
Dann bleibt Entwurfsspeicherung möglich. Es erfolgt kein Wechsel zu Google.

Bei Cloudflare Fehlern prüfen: `/api/health` lokal, gemeinsame Docker-Netze und
Tunnel-Serviceadresse. Die externe HTTPS-Adresse ist nicht die interne Serviceadresse.
