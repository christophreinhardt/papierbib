# Papierbibliothek mobil

**Altbestand: GitHub-Pages-Prototyp.** Die neue selbst gehostete Anwendung
liegt unter [mobile_backend/](../mobile_backend/README.md). Vor dem Wechsel
hier gespeicherte Browserdaten exportieren und aufbewahren; sie werden
nicht automatisch in die neue SQLite-Datenbank übernommen.

Statische, iPhone-taugliche Webanwendung für die Erfassung von Papierbüchern.
Sie kann direkt über GitHub Pages ausgeliefert werden und benötigt keinen
Server und keinen API-Schlüssel.

## Funktionen

- Kamera mit Rückkamera und größtmöglicher per Browser meldbarer Auflösung
- drei Aufnahmemodi: ISBN/Barcode, Buchrücken und Titelblatt
- `BarcodeDetector`, wenn der Browser ihn bereitstellt
- lokale ISBN-10-/ISBN-13-Prüfung und Umwandlung
- Suche in `lobid-resources / hbz` über ISBN oder Titel/Autor
- optionales OCR im Browser über Tesseract.js vom CDN
- lokale Speicherung mit IndexedDB
- JSON- und CSV-Export für den späteren Import in die Papierbibliothek/Calibre
- keine Bildübertragung ohne ausdrückliche Bedienhandlung; Bilder bleiben lokal

## GitHub Pages

1. Den Inhalt dieses Ordners in ein GitHub-Repository kopieren, zum Beispiel in
   den Ordner `mobile/`. Im Papierbibliothek-Repository ist der Workflow bereits
   zusätzlich unter `.github/workflows/pages.yml` abgelegt.
2. In GitHub unter **Settings → Pages** als Quelle **GitHub Actions** wählen.
3. Bei einem eigenen App-Repository die Workflow-Datei nach
   `.github/workflows/pages.yml` kopieren oder Pages alternativ direkt aus dem
   Repository-Root veröffentlichen.
4. Die erzeugte `https://<konto>.github.io/<repository>/`-Adresse auf dem iPhone
   in Safari öffnen und zum Home-Bildschirm hinzufügen.

Kamera-Zugriff funktioniert auf iOS nur über HTTPS oder auf `localhost`. Die
Website muss daher über GitHub Pages geöffnet werden; eine lokale `file://`-Datei
erhält keinen Kamerazugriff.

## Datenmodell und Grenzen

Die Anwendung speichert `schema_version: 1`, Aufnahmeart, ISBN, Titel, Autor,
Verlag, Jahr, OCR-Rohtext, Status, Quelle, Zeitstempel und optional das lokale
Aufnahmebild. Die Webanwendung schreibt nicht direkt in eine Calibre-Bibliothek.
Nach dem Export kann die JSON/CSV-Datei in der Papierbibliothek geprüft und
importiert werden.

Die iOS-Safari-Versionen stellen `BarcodeDetector` nicht überall bereit. In
diesem Fall bleibt die manuelle ISBN-Eingabe verfügbar. OCR wird erst nach dem
Klick auf **OCR versuchen** aus dem öffentlichen Tesseract-CDN geladen. Für
automatische bibliographische Erkennung aus Buchrücken-/Titelblattbildern kann
später ein eigener, geschützter Serverproxy ergänzt werden; ein OpenAI- oder
Gemini-Schlüssel gehört niemals in diese statische GitHub-Seite.

## Lokaler Test

```powershell
python -m http.server 8080 --directory mobile_web
```

Für Kamera-Zugriff auf dem iPhone muss der lokale Test über einen HTTPS-Tunnel
oder GitHub Pages geöffnet werden. Ohne Kamera lässt sich die ISBN- und
Exportlogik im Desktopbrowser testen.
