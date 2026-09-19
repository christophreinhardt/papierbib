# Update auf 0.3.0 – ISBN-Erkennung

Für den bereits funktionierenden Stack mit Cloudflare Tunnel. Keine neuen
API-Schlüssel oder Umgebungsvariablen notwendig. Calibre bleibt unverändert.

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
docker build -t papierbib-mobile:0.3.0 mobile_backend
docker image inspect papierbib-mobile:0.3.0 --format '{{.Id}}'
```

Das Image enthält Tesseract und die lokal bereitgestellte Barcode-Bibliothek.
Es wird nicht aus einer öffentlichen Container-Registry heruntergeladen.

## 3. Bestehenden Portainer-Webeditor-Stack ändern

Nur die Image-Version ändern. `build: .` bleibt im Webeditor entfernt:

```yaml
services:
  papierbib-api:
    image: papierbib-mobile:0.3.0
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

Erwartet: `{"ok":true,"version":"0.3.0","phase":2}`.

Auf dem iPhone die App öffnen und gegebenenfalls **Neue App-Version laden**
wählen. Oben muss **0.3.0** stehen.

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

## Grenzen

Noch keine KI-Erkennung von Titel/Autor, keine Regalfoto-Trennung und kein
Calibre-Export. Drehung weiterhin in 90°-Schritten; freie Feinrotation ist offen.
OCR erkennt ausschließlich prüfziffergültige ISBNs und korrigiert keine vermuteten
Ziffern. Schlechte Beleuchtung, Unschärfe, kleine oder schräge Schrift können
eine manuelle ISBN-Eingabe erfordern. Physisches iPhone bitte selbst abnehmen.

lobid kann zeitweise ausfallen, begrenzen oder eine Zugriffsschutz-Seite liefern.
Dann bleibt Entwurfsspeicherung möglich. Es erfolgt kein Wechsel zu Google.

Bei Cloudflare Fehlern prüfen: `/api/health` lokal, gemeinsame Docker-Netze und
Tunnel-Serviceadresse. Die externe HTTPS-Adresse ist nicht die interne Serviceadresse.
