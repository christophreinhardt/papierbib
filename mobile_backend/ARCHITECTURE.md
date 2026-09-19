# Analyse und Architekturentscheidungen — Phase 1

## Bestand

- `papierbibliothek/`: funktionierendes Calibre-Plugin, Qt-UI, Projektmodell
  `schema_version=5`, Dateispeicherung und atomare Backups. Unverändert.
- `mobile_web/`: GitHub-Pages-Prototyp, IndexedDB pro Browser, CDN-OCR/Barcode,
  separate Backend-URL und Token im SessionStorage. OCR kann weiterhin ohne
  KI-Versuch starten; die vorige Aussage „ausschließlich nach KI“ war im Code
  nicht durchgängig umgesetzt. Keine automatisierte Browserprüfung vorhanden.
- `mobile_backend/app.py`: zustandsloser 0.1-Gateway. Keine Projektverwaltung,
  keine streng validierte KI-Ausgabe nach dem JSON-Parsing, keine echte
  ISBN-Prüfziffernkontrolle, keine vollständigen Ressourcen-/Ratenlimits.
  MIME-Typen wurden nur aus Uploadangaben übernommen.
- Der alte JSON-Export enthält `schema_version:1, books:[...]`, aber keine
  vollständigen Project-/Photo-Felder; auch `year`, `captureType`, Bild-Data-URLs
  weichen vom Pluginformat ab. Er kann nicht ohne Mapping als Projekt geladen werden.

GitHub Pages ist nicht grundsätzlich unsicher; die bisherige konkrete
Trennung erforderte jedoch CORS, zwei Deployments und vom Browser lesbare
dauerhafte Zugangsdaten. Docker allein behebt keine Erkennungsqualität.
Die neue Architektur vereinfacht Betrieb und schafft überprüfbare Bild-/Datenwege.

## Phase-1-Aufbau

```text
Safari / installierte PWA
  HTTPS, gleiche Origin, geschütztes Sitzungscookie
    Reverse Proxy (Tailscale Serve oder eigener Caddy)
      Container papierbib-api, intern 8080, Host 8888
        server.py       FastAPI, Anmeldung, Projekte, Fotos, Revisionen
        config.py       Fail-closed-Konfiguration
        storage.py      SQLite, Transaktionen, Sitzungen, Rate-Limits
        images.py       EXIF, Validierung, Drehung, Zuschnitt
        web/            Kamera, Touch-Editor, Galerie, Offline-Oberfläche
        /data           benanntes, dauerhaftes Volume
```

Keine Netzwerkanfragen an externe Dienste in Phase 1. Bilder verlassen den
Browser nur bei bestätigtem Speichern. Die vorhandenen Provider im Calibre-Plugin
werden nicht in den Webserver importiert (Qt-Abhängigkeiten und andere Verträge).
Neue Provider in Phase 3 erhalten eine getrennte, austauschbare Schnittstelle.

## Datenmodell (SQLite user_version 1)

- `projects`: UUID, Name, UTC-Zeitstempel.
- `captures`: Foto-UUID, Projekt-ID, Aufnahmeart, Original-BLOB, geprüfter
  MIME-Typ, SHA-256, EXIF-orientierte Breite/Höhe, UTC-Zeitstempel.
- `crops`: separate UUID, Foto-ID, Drehung und normierte Box, JPEG-BLOB,
  tatsächliche Ausgabegröße, UTC-Zeitstempel. Keine Überschreibung.
- `book_records`: vorbereitete Ablage für spätere Erkennung: UUID, Projekt,
  Foto, Crop, Status `needs_scan`, versionierbare Metadaten. In Phase 1 leer.
- `sessions`: Hash eines zufälligen Sitzungsschlüssels, Ablauf, Bindung an
  Passwortkonfiguration.
- `rate_limits`: transaktionale Zeitfenster.

BLOB-Speicherung wurde für diese persönliche Bibliothek gewählt, damit Foto,
Crop und Metadaten zusammen committen oder zurückrollen. Große Sammlungen
vergrößern die DB; spätere Auslagerung in Dateispeicher benötigt eine Migration.

Koordinaten gelten nach EXIF-Ausrichtung und anschließend der expliziten
Drehung im Uhrzeigersinn. Boxwerte liegen zwischen 0 und 1 und beziehen sich
auf das gedrehte Bild. Jeder Crop wird aus dem unveränderten Original erzeugt.
Nach Drehen wird der Rahmen auf das ganze gedrehte Bild zurückgesetzt.
Zoomen betrifft nur die Editoransicht.

## Vorgesehene Calibre-Übergabe (Phase 5)

Kein eigener „Calibre-kompatibler“ Export wird ohne Prüfung behauptet.
Ziel ist ein Projektpaket mit `projekt.json` gemäß dem bestehenden Schema 5
und separaten Bilddateien unter relativen Pfaden:

| Mobiler Wert | Pluginfeld |
|---|---|
| project_id/name/created_at/updated_at | Project, identische Felder |
| photo_id + Original | Photo, photos/<UUID>.<Format> |
| tatsächlicher gewählter Crop | Book.crop_path, separater relativer Pfad |
| title/author/publisher | Book, identische Felder |
| gültiges ganzzahliges Jahr | Book.publication_year |
| normalisierte, geprüfte ISBN | Book.isbn10 / isbn13 |
| manueller Entwurf | needs_manual_review / needs_scan |
| unbekannte Konfidenz | null, nicht erfundene 0 oder 1 |
| Drehung und normierte Box | nachvollziehbare Umrechnung/Exportbild; nicht blind bounding_box kopieren |

Das Plugin erwartet auch photos, gültige Hashes, Referenzintegrität, Status
und Konfidenzfelder. Buchgruppen sind keine einzelnen Book-Records.
Vor Implementierung der Übergabe das aktuelle Plugin erneut gegenprüfen.

## Phasengrenzen und Risiken

- Phase 1 enthält bewusst keine KI-/OCR-/Barcode-Buttons ohne Funktion.
- Ein Cookie ist für Anmeldung nötig. Die Forderung „kein Token im Browser“
  wird als „kein langlebiges API-/Provider-Token im JavaScript/Storage“ umgesetzt;
  das kurzlebige HttpOnly-Cookie bleibt notwendiger Browserzustand.
- Der Nutzer erteilt Speicherzustimmung je Foto bzw. neuer Crop-Version.
  Abmeldung löscht die aktuelle lokale Aufnahme nach Rückfrage.
- Kein automatischer Upload ruhiger Live-Kameraframes.
- HEIC-Import nicht garantiert; JPEG/PNG/WebP sind ausdrücklich unterstützt.
- iPhone-Auflösung hängt vom Browser und Kameramodus ab. Keine pauschale Zusage
  der Sensor-Maximalauflösung. Native Fotoaufnahme als Alternative.
- Offline: Oberfläche und aktueller Editor, keine persistente lokale Fotowarteschlange.
- Eine gemeinsame private Bibliothek; noch keine Rollen oder Benutzertrennung.
- DB-Gesamtgröße durch verfügbare Volume-Kapazität begrenzt; einzelne Uploads/
  Pixelzahl und parallele Decoder begrenzt. Bei Speicherfehler keine Erfolgsmeldung.
- PWA kann ausschließlich an einer eigenen Domainwurzel betrieben werden,
  nicht unter einem Unterpfad.
- Echte iPhone-Kamera, Fingerscrollen/Zoom, Home-Bildschirm-Installation und
  Portainer auf dem persönlichen Mac erfordern abschließende Vor-Ort-Abnahme.

## Primärdokumentation

- [FastAPI: Cookies](https://fastapi.tiangolo.com/advanced/response-cookies/)
- [FastAPI: StaticFiles](https://fastapi.tiangolo.com/tutorial/static-files/)
- [Docker Compose Build-Kontext](https://docs.docker.com/reference/compose-file/build/)
- [Portainer: Git-Stacks](https://docs.portainer.io/user/docker/stacks/add)
- [Tailscale Serve](https://tailscale.com/docs/reference/tailscale-cli/serve)
- [MDN: Kamera und sichere Kontexte](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)
- [MDN: Service Worker](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API)
