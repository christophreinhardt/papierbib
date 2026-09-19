# Papierbibliothek – Calibre-Plugin mit Kamera-Schnellerfassung

Die neue mobile Erfassung läuft als **selbst gehostete PWA (0.4.1)**
auf dem Homeserver. [Portainer-/OrbStack-Anleitung](mobile_backend/README.md) und
[Architektur/Phasenplan](mobile_backend/ARCHITECTURE.md).
Der GitHub-Pages-Prototyp unter `mobile_web/` bleibt als Altbestand erhalten.
Die PWA umfasst Projekte, Kamera, Zuschnitt, lokale Barcode-Erkennung,
ISBN-only-OCR, lobid und geprüfte Buchdatensätze. [Update bestehender Portainer-
und Cloudflare-Installationen](mobile_backend/PORTAINER-UPDATE.md).
KI, Regaltrennung und Calibre-Übergabe folgen in den nächsten Phasen.

Papierbücher anhand eigener Regalfotos oder direkt per Kamera erfassen und nach Prüfung in Calibre übernehmen. Version **0.6.13** lädt nach Neuanlagen auch Calibres Tabellen-Datenbankcache neu, damit neue Bücher unmittelbar sichtbar werden. Für Kameraaufnahmen wird automatisch das größte von der Kamera gemeldete Videoformat verwendet; lokale Titelblattzuschnitte werden in voller Auflösung gespeichert. Titelblattaufnahme, Drehung, Zuschnitt, Mehrfachlöschung und ausdrücklich bestätigte KI-Auswertung bleiben verfügbar. Keine zusätzlichen Python-Pakete erforderlich.

## Fotos löschen

In der Fotoliste ein Foto oder mit Strg/Cmd beziehungsweise Umschalt mehrere Fotos markieren. **Ausgewählte Fotos löschen** öffnet eine Bestätigung mit der Anzahl betroffener Bücher. Nach Bestätigung verschwinden die ausgewählten Fotos aus der Liste. Bücher und Metadaten bleiben erhalten; Fotozuordnung, zugehörige Regalrahmen und gegebenenfalls Titelblattzuordnung werden entfernt. Bereits gespeicherte Buchrückenausschnitte und KI-Belegbilder bleiben erhalten. Der Fotofilter wird auf **Alle Fotos** zurückgesetzt, sodass die Bücher weiter sichtbar sind.

Die nicht mehr verwendeten Projektkopien und Vorschauen werden unter `.trash/photos-<ID>/` im Projektordner aufbewahrt. Dort liegt auch eine `projekt.json` des Zustands vor dem Löschen. Noch von anderen Datensätzen verwendete Bilddateien bleiben an ihrem Speicherort. Importierte Originaldateien außerhalb des Projekts werden nicht verändert. Falls eine Bilddatei gesperrt ist, bleibt sie am bisherigen Ort und ein Hinweis nennt die betroffenen Dateien. Der Projektpapierkorb wird nicht automatisch geleert; Löschen gibt daher zunächst keinen Speicherplatz frei.

Wiederherstellung eines früheren Stands: den gesamten Projektordner in einen separaten Ordner kopieren, dort `photos/`, `previews/` beziehungsweise `title_pages/` aus dem betreffenden Papierkorbordner zurückkopieren und dessen `projekt.json` als Projektdatei der Kopie verwenden. Bei mehreren Löschvorgängen gegebenenfalls auch die Bilddateien aus späteren Papierkorbordnern zurückkopieren. Die Kopie anschließend öffnen. Änderungen nach dem gewählten Wiederherstellungsstand sind in dieser Kopie nicht enthalten. Eine Wiederherstellungs-Schaltfläche ist noch nicht vorhanden.

## Kameraauflösung

Beim Start des Kameradialogs wählt das Plugin automatisch das Videoformat mit der größten verfügbaren Pixelzahl der ausgewählten Kamera. Die verwendete Auflösung wird bei Titelblattaufnahmen im Status angezeigt. Die USB-Kamera des Entwicklungssystems lieferte im Test 3264 × 2448 Pixel. Die tatsächliche Auflösung hängt von Kamera, Treiber und Lichtbedingungen ab; falls die Kamera keine Formate meldet, verwendet Qt ihre Standardauflösung.

## iPhone-Web-App über GitHub Pages

Im Ordner `mobile_web/` liegt eine eigenständige Smartphone-Webanwendung. Sie
öffnet die iPhone-Rückkamera, unterstützt ISBN/Barcode, Buchrücken und
Titelblatt, fragt ISBNs oder Titel/Autor bei lobid ab und speichert die
Ergebnisse lokal im Browser. JSON und CSV können anschließend für die
Papierbibliothek und den Calibre-Import exportiert werden. Die App enthält eine
GitHub-Pages-Action unter `mobile_web/.github/workflows/pages.yml`; die
Anleitung steht in `mobile_web/README.md`. Kamera-Zugriff erfordert auf iOS
HTTPS, daher muss die Seite über GitHub Pages geöffnet werden.

## Neu: Buch per Kamera erfassen

1. Projekt öffnen und **Buch per Kamera erfassen** drücken. Bei mehreren Kameras das gewünschte Gerät auswählen.
2. Den ISBN-Barcode groß, scharf und gut beleuchtet in die Bildmitte halten. Leichtes langsames Kippen kann Spiegelungen beseitigen. Die Erkennung läuft lokal in Calibres Qt6-Laufzeit. Es werden keine Kameraframes gespeichert oder hochgeladen.
3. Erst nach zwei identischen Lesungen und erfolgreicher ISBN-13-Prüfziffer wird der Scan angenommen. Andere EAN-13-Warencodes werden verworfen; akzeptiert werden ausschließlich Buchpräfixe `978` und `979`.
4. Das Plugin legt einen Papierbuch-Datensatz an und fragt automatisch ausschließlich `https://lobid.org/resources/search` ab. Google Books, Open Library, DNB und der freie Anbieter werden durch den Kameraablauf nicht aufgerufen. Ein konfliktfreier, editionsgenauer lobid-ISBN-Treffer wird automatisch übernommen. Schwache, mehrdeutige oder widersprüchliche Treffer öffnen weiterhin die Vergleichsansicht.
5. Die ISBN wird bereits vor dem Onlinezugriff atomar in `projekt.json` gespeichert. Sind alle Dienste deaktiviert, offline, nicht erreichbar oder liefern keinen Treffer, bleibt der Datensatz mit ISBN erhalten und kann später über **Online-Datenbanken abgleichen** erneut gesucht werden.
6. Eine bereits vorhandene ISBN erzeugt keinen zweiten Projektdatensatz. Ein schon ausgefüllter Datensatz wird nicht stillschweigend überschrieben.
7. Ist nur die gedruckte ISBN sichtbar oder der Barcode beschädigt, **ISBN-Text kostenpflichtig mit KI lesen …** wählen. Danach erscheint die bekannte Ausschnittvorschau mit **Kostenpflichtig auswerten**. Erst dieser zweite ausdrückliche Klick überträgt genau das angezeigte Einzelbild an OpenAI oder Gemini. Laufende Kameraframes werden niemals automatisch an einen KI-Dienst gesendet.

Der automatische lokale Decoder verarbeitet EAN-13/ISBN-Barcodes und toleriert leichte Drehung sowie wechselnde Balkenbreiten durch Perspektive. Er liest keine frei gedruckten ISBN-Ziffern: Dafür bleibt der ausdrücklich bestätigte KI-Fallback erforderlich. Starke Unschärfe, Reflexionen, sehr schräge Perspektiven oder abgeschnittene Randmarkierungen können auch die Barcodeerkennung verhindern. Der eigentliche Import in Calibre bleibt weiterhin ein separater, ausdrücklich bestätigter Schritt.

## Neu: Titelblatt mit USB-Kamera aufnehmen

1. In der Büchertabelle den zugehörigen Datensatz auswählen und **Titelblatt fotografieren** drücken.
2. USB-Kamera auswählen, das Titelblatt ausrichten und ausdrücklich **Titelblatt aufnehmen** drücken. Laufende Vorschaubilder werden nicht gespeichert.
3. Im Zuschneide-Editor mit der Maus ein Rechteck ziehen. Mit **↶ 90° links**, **↷ 90° rechts** oder der Drehauswahl ausrichten und die Vorschau prüfen.
4. **Zuschneiden und speichern** legt ein pixelbereinigtes JPEG ohne EXIF-/GPS-Daten unter `title_pages/` im Projekt ab. Buchrückenfoto und vorhandener Buchrückenausschnitt werden nicht überschrieben.
5. Das gespeicherte Titelblatt erscheint zusätzlich als normaler Eintrag in der Fotoliste. **Titelblatt anzeigen** zeigt es direkt im Bildbereich. Für eine spätere Calibre-Zuordnung bevorzugt `#scan_image` dieses Titelblatt.
6. **Titelblatt mit KI auswerten** öffnet erneut die Ausschnitt- und Drehvorschau. Erst **Kostenpflichtig auswerten** sendet genau den angezeigten, EXIF-freien Ausschnitt an den ausgewählten Anbieter. **Abbrechen** überträgt nichts. Der Vorschlag durchläuft anschließend dieselbe Prüfoberfläche wie ein Buchrücken.

Aufnahme, Drehung, Zuschnitt und Speicherung sind vollständig lokal. Nur die getrennte KI-Aktion benötigt Netzwerkzugriff und eine neue ausdrückliche Bestätigung. Eine Titelblatt-Auswertung ersetzt weder die Zuordnung des Regalbilds noch den gespeicherten Buchrückenausschnitt.

## Neu: Sicherer Import in die aktuelle Calibre-Bibliothek

1. Das Plugin innerhalb der Calibre-Hauptoberfläche öffnen und ein Projekt laden. **Importvorschau für aktuelle Calibre-Bibliothek** berücksichtigt Datensätze mit Titel und Status **Eindeutig zugeordnet**, **Wahrscheinlicher Treffer**, **Manuell bestätigt** oder **Importfehler**. Wahrscheinliche Treffer sind nicht vorausgewählt.
2. Calibre wird anhand einer exakten ISBN gesucht. Existiert die ISBN bereits, bleibt die Zeile standardmäßig abgewählt und auf **Überspringen**. Eine vorhandene Calibre-ID kann ausdrücklich zur Aktualisierung gewählt oder manuell eingegeben werden. Ohne Treffer wird ein neuer Datensatz ohne E-Book-Datei angelegt.
3. Nach der Auswahl folgt eine zweite Zusammenfassung mit der Zahl neuer und zu aktualisierender Datensätze. Erst die Bestätigung verändert die aktuelle Calibre-Bibliothek. Wechselt die aktive Bibliothek zwischen Vorschau und Bestätigung, bricht das Plugin ab.
4. Neue Datensätze erhalten Titel, getrennte Autoren, Verlag, Jahr, Sprache, ISBN, Projekttags und den Tag **Papierbuch**. Bei Aktualisierungen werden nur vorhandene Projektwerte gesetzt; andere Identifikatoren und vorhandene Tags bleiben erhalten. Leere Projektfelder löschen keine Calibre-Metadaten.
5. **Verfügbares Online-Cover herunterladen** ist standardmäßig aus. Die Aktivierung ist eine zusätzliche ausdrückliche Zustimmung. Akzeptiert werden nur HTTPS-Bilder von den bekannten Open-Library-/Google-Books-Coverdomains, ohne Weiterleitungen und bis 10 MB.
6. Bereits vorhandene benutzerdefinierte Calibre-Spalten werden unterstützt: **#scan_status** als Text, **#scan_confidence** als Fließkommazahl sowie **#scan_source**, **#scan_image** und **#scan_review_note** als Text. Das Plugin legt Spalten nicht eigenmächtig an; sie können zuvor unter Calibre → Einstellungen → Eigene Spalten hinzugefügt werden. Fehlende oder unpassend typisierte Spalten verhindern den Buchimport nicht.
7. Der Import läuft im Hintergrund und lässt sich abbrechen. Erfolgreiche Bücher werden nach jedem Datensatz mit Calibre-ID und Status **In Calibre importiert** im Projekt gespeichert. Bereits abgeschlossene Datenbankänderungen werden bei Abbruch nicht zurückgerollt. Fehler werden pro Buch als **Importfehler** mit verständlichem Hinweis gespeichert.

## Neu: Online-Abgleich und ISBN-Fallback

1. Ein Buch in der Tabelle auswählen und **ISBN eingeben und suchen** verwenden. Prüfziffern werden lokal validiert; ISBN-10 wird in ISBN-13 umgerechnet. Alternativ **ISBN-/Barcodefoto auswerten** wählen, ein Bild importieren, den übertragenen Ausschnitt kontrollieren und dem gewählten KI-Anbieter ausdrücklich zustimmen. Erkannter Rohtext, Kandidaten und Konfidenz werden vor jeder Übernahme angezeigt. Für Live-Kameraframes steht zusätzlich der paketfreie lokale EAN-13-Decoder bereit.
2. **Online-Datenbanken abgleichen** kann für das gewählte Buch lobid, Open Library, die Deutsche Nationalbibliothek sowie optional Google Books abfragen. lobid ist standardmäßig aktiv, Google Books bei neuen Konfigurationen aus. Zuerst wird ausschließlich die ISBN verwendet; nur bei fehlendem Treffer folgen Titel/Autor und weitere Angaben. Ein eigener HTTPS-JSON-Anbieter ist konfigurierbar. **Offene Bücher stapelweise abgleichen** verarbeitet geeignete Datensätze im Hintergrund, lässt sich abbrechen und speichert jedes fertige Buch sofort. Der Kameraablauf ist davon getrennt und verwendet immer ausschließlich lobid.
3. Ergebnisse werden je Ausgabe gruppiert und bewertet. Exakte ISBN, Titel, Autor und Verlag fließen in die Bewertung ein. Abweichende Ausgaben und widersprüchliche Felder werden markiert. **Online-Treffer prüfen** zeigt Treffer, Quellen, Abrufzeitpunkt und Konflikte. Metadaten ändern sich erst nach ausdrücklicher Bestätigung; Konflikttreffer lassen sich nicht pauschal übernehmen.
4. Antworten werden 30 Tage in **metadata-cache.json** im Projekt gespeichert. Der Offline-Modus verwendet auch ältere Cacheeinträge und führt keine Netzwerkanfrage aus. Rate-Limits, Timeouts, beschädigte Antworten und Teilausfälle werden pro Anbieter angezeigt; Treffer anderer Anbieter bleiben nutzbar.
5. Open Library und DNB benötigen keinen Schlüssel. Ein optionaler Google-Books-Schlüssel wird ausschließlich aus **GOOGLE_BOOKS_API_KEY**, der Schlüssel des eigenen Anbieters ausschließlich aus **PAPIERBIBLIOTHEK_CUSTOM_API_KEY** gelesen. Schlüssel werden weder protokolliert noch im Projekt, Cache oder Export gespeichert.

Der frei konfigurierbare Anbieter muss eine einfache HTTPS-URL akzeptieren und ein JSON-Objekt mit einer Liste namens **items** und normalisierten Buchfeldern liefern. Ein vorhandener Schlüssel wird als Bearer-Header gesendet. Weiterleitungen und unsichere URLs werden blockiert.

## KI-Anbieter wählen: OpenAI oder Google Gemini

1. ZIP `dist/Papierbibliothek-0.6.13.zip` in Calibre als Erweiterung laden und Calibre neu starten.
2. In **Papierbibliothek → KI- und Datenbank-Einstellungen → KI-Anbieter** entweder **OpenAI** oder **Google Gemini** wählen. OpenAI bleibt die Voreinstellung vorhandener Installationen.
3. Für Gemini einen eigenen API-Schlüssel aus [Google AI Studio](https://aistudio.google.com/apikey) im Feld **Gemini-Schlüssel (nur Sitzung)** eingeben. Alternativ `GEMINI_API_KEY` in der Umgebung bereitstellen, aus der Calibre gestartet wird. `GOOGLE_API_KEY` wird bewusst nicht automatisch verwendet. OpenAI verwendet weiterhin ausschließlich seinen Sitzungsschlüssel oder `OPENAI_API_KEY`.
4. Das jeweilige Modell auswählen oder eine Modell-ID eingeben. Beide Anbieter behalten getrennte Modellwerte und Sitzungsschlüssel. Nicht aktive Eingabefelder sind deaktiviert. **Speichern** übernimmt die Auswahl, aber schreibt keine Schlüssel auf Festplatte.
5. Einzelbuch- und Regal-Erkennung verwenden ab dann den gewählten Anbieter. Die Vorschau und die Zustimmung nennen den Empfänger ausdrücklich. Jede Bildübertragung braucht eine neue Bestätigung. Es gibt keinen automatischen Anbieterwechsel – auch nicht bei Fehlern oder fehlendem Schlüssel.

Gemini-Voreinstellung ist `gemini-3.5-flash-lite`, ein als stabil dokumentiertes kostengünstiges Modell mit Bildinput und Structured Outputs. Weitere Modell-IDs sind frei eingebbar. Die Eignung für schwierige Regalfotos ist nicht durch einen Vergleichsbenchmark belegt. [Modellbeschreibung](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). Die zunächst geprüfte Version 2.5 Flash-Lite antwortete beim vorhandenen Zugang mit HTTP 404; 3.5 Flash-Lite wurde erfolgreich mit Bildinput getestet. Das Plugin nimmt bei Modellfehlern keinen eigenmächtigen Wechsel vor.

Der separate Adapter `vision/gemini.py` verwendet Googles weiterhin unterstützte [generateContent-API](https://ai.google.dev/api/generate-content) über HTTPS mit Inline-JPEG sowie `responseMimeType`/`responseJsonSchema`. Es wird keine Datei über die Files API hochgeladen und kein eigener serverseitiger Chatverlauf angelegt. Der Schlüssel wird ausschließlich als `x-goog-api-key`-Header an `generativelanguage.googleapis.com` geschickt, niemals in URL oder Export. Weiterleitungen werden blockiert. Timeout: 45 Sekunden; keine automatische Wiederholung von Gemini-Anfragen. Fehler erscheinen bereinigt, ohne rohe Antworten oder Schlüssel. Höchstens 3000 Ausgabetokens für Einzelbücher bzw. 12000 für Regalbereiche. Der zunächst untersuchte Interactions-Endpunkt lieferte beim Live-Test HTTP 404 und wird nicht verwendet.

Beide Adapter verwenden dieselben lokal streng validierten Metadaten- und Rahmen-Schemas. Für Gemini werden ausschließlich Zahlen- und Array-Grenzwerte (`minimum`, `maximum`, `minItems`, `maxItems`) aus dem gesendeten Schema entfernt, weil die verschachtelte Regalvariante im Live-Test andernfalls mit HTTP 400 abgelehnt wurde. Pflichtfelder, Typen, Enumerationen und das Verbot zusätzlicher Felder bleiben im API-Schema erhalten. Sämtliche Grenzwerte werden vor Übernahme weiterhin lokal geprüft – insbesondere höchstens 60 Bereiche, gültige Bildkoordinaten und Konfidenzen 0 bis 1. Gemini-Antworten mit Fehlerstatus, Ablehnung, unvollständigem oder ungültigem JSON werden nicht übernommen. Anbieter und Modell bleiben am jeweiligen Ergebnis gespeichert; alte OpenAI-Ergebnisse ändern sich beim Anbieterwechsel nicht.

**Datenschutz:** Die Gemini-generateContent-Anbindung verwendet keine `store=false`-Option. Die bei OpenAI gesetzte Option ist nicht auf Gemini übertragbar. Fehlender Chatverlauf bedeutet nicht, dass Google keinerlei Daten verarbeitet oder aufbewahrt. Googles Datennutzung hängt unter anderem von Tarif und Region ab. Vor privaten Fotos bitte die [Gemini-API-Bedingungen](https://ai.google.dev/gemini-api/terms) und die Kontoeinstellungen prüfen. Im Plugin gibt es keine pauschale Gleichsetzung von kostenlosem und kostenpflichtigem API-Zugang.

Der Gemini-Adapter ist mit simulierten Antworten getestet. Ein echter API-Test mit einem künstlichen Buchrücken erkannte „DAS BLAUE REGAL“, „LENA WINTER“ und „NORDLICHT VERLAG“ korrekt (1253 Input-, 279 Outputtokens). Der zusätzliche Regaltest erkannte alle drei künstlichen Buchbereiche (1254 Input-, 257 Outputtokens). Keine privaten Fotos wurden übertragen. Ein Qualitätsbenchmark mit realen Fotos steht aus. Opt-in-Test: `calibre-debug live_vision_check.py -- --send-synthetic-image --gemini`; zusätzlich `--shelf` prüft ein künstliches Regalbild.

## Neu: Regalfotos aufteilen und Rahmen korrigieren

1. Foto auswählen und **Regal mit KI aufteilen** drücken. Eine Regalreihe auswählen oder das ganze Bild verwenden. Rechts das tatsächlich übertragene Bild prüfen und der kostenpflichtigen Übertragung zustimmen.
2. Ein API-Aufruf beim ausgewählten Anbieter lokalisiert höchstens 60 Bereiche. Er liefert bewusst nur Rahmen, Bereichsart und Lokalisierungskonfidenz, noch keine bibliografischen Metadaten. Maximal 12000 Ausgabetokens; Bild längste Kante 2400 Pixel. Keine zusätzlichen Einzelbuchaufrufe ohne Zustimmung.
3. Nach erfolgreicher Auswertung werden Bereiche und Ausschnitte gemeinsam atomar gespeichert, dann öffnet sich der Rahmeneditor. Alle erkannten Bereiche sind zunächst angehakt. Einen falsch erkannten Rücken durch Entfernen des Hakens ausschließen; der Datensatz bleibt nachvollziehbar als **Ignoriert** erhalten. Er kann durch erneutes Anhaken wieder aufgenommen werden. **Abbrechen** im Editor behält die ursprünglichen KI-Vorschläge, verwirft aber noch nicht gespeicherte Änderungen. **Buchrücken-Rahmen bearbeiten** öffnet die Ansicht später wieder, auch komplett offline.
4. Einen vorhandenen Rahmen in der Liste oder direkt im Foto anklicken. Mit Strg/Cmd oder Umschalt können mehrere Rahmen markiert und gemeinsam bestätigt beziehungsweise ein- oder ausgeschlossen werden. Blau kennzeichnet alle markierten Rahmen. Zum Korrigieren im Foto ein neues Rechteck ziehen und **Rahmen ersetzen** drücken. Fehlende Bücher mit **Buch hinzufügen** ergänzen. **Auswahl bestätigen** bestätigt nur die Geometrie. Änderungen abschließend mit **Speichern** sichern.
5. Untrennbare Gruppen sind rot und haben den Status **Nachscan nötig**. **Gruppe / Einzelbuch** ändert die Einordnung. Zum Aufteilen die Gruppe **ignorieren**, kleinere Einzelrahmen hinzufügen und speichern. Ignorierte Datensätze bleiben erhalten. Eine Gruppe kann nicht als einzelnes Buch bestätigt werden. Die Tabellenanzahl umfasst auch solche Platzhalter, ist also noch keine verlässliche Bücherzählung.
6. Für einen Einzelrahmen in der Haupttabelle **Gewähltes Buch erneut auswerten** wählen. Der gespeicherte Rahmen ist vorausgewählt; Bild und gegebenenfalls Drehung prüfen, ausdrücklich zustimmen und anschließend Metadaten prüfen. Pro Einzelbuch erfolgt ein gesonderter API-Aufruf.

Koordinaten beziehen sich auf das EXIF-orientierte Original, nicht auf die Dateirohdimensionen. Normierte API-Koordinaten werden auf den gewählten Regalabschnitt zurückgerechnet. Rahmen müssen vollständig im Bild liegen und mindestens 8×8 Pixel groß sein. Die Originalfotos bleiben unverändert. Änderungen am Rahmen erzeugen neue Ausschnitte und verwerfen überholte OCR-Vorschläge/Konfidenzen; bereits erfasste Metadaten bleiben erhalten, aber wieder prüfpflichtig.

Eine erneute Erkennung auf demselben Foto überspringt stark ähnliche Rahmen (Intersection-over-Union ≥ 0,7), ohne bestehende Datensätze zu überschreiben. Andere Überlappungen über 0,1 werden zur Prüfung gemeldet. Das ist eine geometrische Heuristik, keine bibliografische Dublettenprüfung. Fotoübergreifende Dubletten werden noch nicht erkannt. Abbruch vor dem atomaren Speichern verwirft die neue Gruppe von Ergebnissen; eventuell bereits erzeugte Ausschnittdateien bleiben zur Wiederherstellung erhalten. Pro Regalabschnitt wird ein gespeicherter Zwischenstand erstellt.

**Grenzen:** Vision-Modelle können Bücher übersehen oder ungenaue Rahmen liefern; insbesondere bei dichtem, schrägem, dunklem oder teilweise verdecktem Inhalt. Die Rahmen sind achsenparallel, keine polygonalen Konturen. Kleine Regalabschnitte und die manuelle Sichtkontrolle sind deshalb wichtig. Lokalisierungskonfidenzen stehen im Rahmeneditor und sind unabhängig von den OCR-Konfidenzen des Tabellenfilters. Ein Qualitätsbenchmark mit echten Regalfotos steht aus.

## Einzelbuch-Auswertung und Prüfung (OpenAI-Beispiel)

1. Unter **KI- und Datenbank-Einstellungen** das Modell wählen. Voreinstellung ist `gpt-5.6-luna` mit Reasoning `none`, Bilddetail `high` und höchstens 3000 Ausgabetokens. Es gibt keinen automatischen Wechsel auf ein teureres Modell.
2. API-Schlüssel entweder in `OPENAI_API_KEY` bereitstellen (Calibre muss diese Umgebung beim Start erben) oder im Passwortfeld für die aktuelle Plugin-Sitzung eingeben. Er wird nicht in Einstellungen, Projektdateien, Exporten oder Logs gespeichert. Beim Schließen des Plugin-Fensters wird der Sitzungsschlüssel verworfen.
3. Foto auswählen und **Buchrücken mit KI erfassen** drücken. Im Originalfoto ein Rechteck um genau einen Buchrücken ziehen. Für ein Einzelfoto ist auch **Ganzes Foto** möglich. Bei Bedarf den Ausschnitt um 90/180/270 Grad drehen.
4. Rechts die tatsächliche Übertragungsvorschau kontrollieren. Sobald der Ausschnitt gültig ist, wird **Kostenpflichtig auswerten** aktiv. Der Klick auf diesen Button ist die ausdrückliche Zustimmung, genau den angezeigten Ausschnitt an den genannten Anbieter zu übertragen; ein zusätzliches Häkchen gibt es nicht. **Abbrechen** überträgt nichts.
5. Das Plugin sendet ausschließlich den ausgewählten, höchstens 2400 Pixel langen JPEG-Ausschnitt an `https://api.openai.com/v1/responses`. Er enthält keine EXIF-/GPS-Daten oder Dateipfade. `store=false` deaktiviert die optionale Responses-Speicherung, ist aber keine Zusicherung einer vollständig fehlenden Verarbeitung oder Aufbewahrung beim Anbieter.
6. Der KI-Vorschlag wird vor dem Prüfdialog im Projekt gesichert. **Später prüfen** verliert ihn daher nicht. **KI-Vorschlag prüfen** öffnet ihn später wieder.
7. Im Vergleich zwischen „Bisher“ und „KI-Vorschlag“ gewünschte Felder anhaken und Vorschläge bei Bedarf direkt korrigieren. Links steht **Speichern und bestätigen** als Standardaktion und kann mit Enter ausgelöst werden; sie verlangt weiterhin einen Titel. Danach folgen **Als Entwurf speichern**, **Nachscan nötig** und **Später prüfen**. Der Entwurf erlaubt unvollständige Datensätze ohne Titel und belässt sie im Status **Prüfen**. Ungültige Jahres- oder ISBN-Angaben werden mit der konkreten Validierungsmeldung abgelehnt.
8. **Gewähltes Buch erneut auswerten** legt einen neuen Vorschlag am vorhandenen Datensatz ab, ohne dessen Metadaten ungefragt zu ersetzen. Die zuletzt gespeicherte KI-Auswertung bleibt als Beleg erhalten, auch wenn Metadaten manuell korrigiert werden. Erneute Auswertung ersetzt den vorherigen Vorschlag; alte Ausschnittdateien werden nicht gelöscht.

KI-Konfidenzen werden pro erkanntem Feld sowie als Gesamtwert gespeichert. Es handelt sich um unkalibrierte Modellschätzungen, nicht um verifizierte Treffer. Der Filter **Unter Prüfgrenze** nutzt den KI-Gesamtwert; Felder unterhalb der einstellbaren Grenze werden im Prüfdialog farbig hervorgehoben. KI-Auswertungen ergeben grundsätzlich **Prüfen** oder **Nachscan nötig**. Erst der separate Online-Abgleich kann einen Datensatz als eindeutig oder wahrscheinlich zugeordnet markieren; der Calibre-Import bleibt anschließend ausdrücklich bestätigungspflichtig.

Der HTTP-Adapter ist hinter `VisionProvider.analyze()` austauschbar. Lokale Vision-Modelle können später denselben validierten Ergebnisvertrag verwenden. Der vorhandene Adapter akzeptiert ausschließlich den festen OpenAI-Endpunkt; Weiterleitungen werden verhindert. Netzwerkarbeit läuft im Hintergrund. Ein Abbruch verwirft noch nicht gespeicherte Ergebnisse, kann eine schon beim Anbieter eingegangene Anfrage aber nicht zurückholen. Timeout: 45 Sekunden pro Versuch; genau ein Wiederholungsversuch bei temporärem HTTP 429, keiner bei fehlendem Kontingent oder sonstigen Fehlern.

**Modellwahl:** [GPT-5.6 Luna](https://developers.openai.com/api/docs/models/gpt-5.6-luna) unterstützt Bildinput und Structured Outputs und ist aktuell ein günstiger Einstieg. Dokumentierte Preise: 0,20 USD pro Million Inputtokens, 1,20 USD pro Million Outputtokens. Ältere günstigere Modelle sind teilweise als veraltet gekennzeichnet. Ein echter Test mit einem künstlichen Buchrücken erkannte Autor, Titel und Verlag korrekt (1177 Input-/149 Outputtokens). Das ist noch kein Qualitätsbenchmark für reale, schräge oder schlecht beleuchtete Regalfotos.

## Upgrade von 0.1.0 / 0.2.0

Vor dem Upgrade den gesamten Projektordner sichern. Das neue ZIP wie unten beschrieben laden; Calibre aktualisiert das gleichnamige Plugin. Projekte der Schemaversionen 1 bis 4 werden eingelesen und beim nächsten Speichern als Version 5 geschrieben. Bereits vorhandene Titelblätter aus Version 4 werden beim Öffnen automatisch als Projektfotos ergänzt. Ältere Plugin-Versionen können Version 5 nicht öffnen. `projekt.backup.json` ist nur die unmittelbar vorherige Fassung und ersetzt keine dauerhafte Sicherung. Es wurde keine Installation in deiner normalen Calibre-Konfiguration vorgenommen.

## Installation

1. Calibre öffnen. Unter **Einstellungen → Erweiterungen → Erweiterung aus Datei laden** die Datei `dist/Papierbibliothek-0.6.13.zip` auswählen. Je nach Übersetzung heißt der Bereich „Plugins“.
2. Calibre neu starten.
3. Falls der Eintrag fehlt: Unter **Einstellungen → Symbolleisten & Menüs → Hauptsymbolleiste** die Aktion **Papierbibliothek** hinzufügen.
4. **Papierbibliothek** in der Symbolleiste öffnen.

Voraussetzung: Calibre ab 7 mit Qt 6. Windows-Testumgebung: **Calibre 9.14, Python 3.14.7, Qt 6.10.1**. macOS und Linux sind freigegeben; Laufzeittests dort stehen aus. Calibre verwaltet das ZIP, es wird nicht mit pip installiert.

Optional ohne Installation aus diesem Quellcodeordner:

```powershell
calibre-debug run_standalone.py
```

Unter macOS liegt `calibre-debug` üblicherweise unter `/Applications/calibre.app/Contents/MacOS/`.

## Bedienung

1. **Neues Projekt**: einen noch nicht vorhandenen Ordnernamen angeben und die Sammlung benennen.
2. **Fotos hinzufügen** für einzelne/mehrere Dateien oder **Fotoordner hinzufügen** für einen Ordner samt Unterordnern. Regal/Fach optional angeben, etwa „Arbeitszimmer, Regal A, Fach 3“.
3. Ein Foto auswählen. Mausrad zoomt, Ziehen verschiebt. **Bild einpassen** zeigt das ganze Foto, **Original ansehen** lädt die hochauflösende Fassung im Hintergrund.
4. **Buchdatensatz manuell anlegen**: Metadaten eingeben, optional ein Regalfoto zuordnen und die Position notieren, etwa „5 von links“. Sämtliche Angaben dürfen für einen leeren Entwurf zunächst fehlen. Mehrere Autoren mit ` & ` trennen, Tags mit Komma. **Speichern** legt den Datensatz sofort an und wählt ihn aus; doppelte ISBNs werden verhindert. Danach können Titelblatt, ISBN oder Barcode ergänzt werden.
5. Für die Schnellerfassung **Buch per Kamera erfassen** verwenden. Der lokale ISBN-Barcode startet den Online-Abgleich automatisch; dafür muss mindestens eine Datenbankquelle aktiv sein oder ein passender Cacheeintrag im Offline-Modus existieren.
6. Für ein geprüftes Buch **Manuell bestätigt** wählen. Bei Unklarheiten **Prüfen** oder **Nachscan nötig** verwenden. **Ignoriert** behält den Datensatz im Projekt.
7. Tabelle per Suchfeld, Status oder ausgewähltem Foto filtern. Mehrere Zeilen lassen sich mit Strg bzw. Cmd oder Umschalt auswählen; **Buch entfernen** wirkt nach Bestätigung auf die gesamte Auswahl. Doppelklick öffnet bei vorhandenen bibliografischen Daten den Editor. Bei einem noch leeren Buchbereich startet er direkt die KI-Ausschnittsauswertung; ein bereits gespeicherter, aber noch nicht übernommener KI-Vorschlag öffnet stattdessen die Prüfansicht.
8. **CSV exportieren** oder **JSON exportieren** exportiert die gesamte Sammlung, unabhängig vom Tabellenfilter. Ziel ist standardmäßig `exports/` im Projekt.
9. Das zuletzt verwendete Projekt wird beim nächsten Öffnen des Plugins automatisch geladen, sofern seine `projekt.json` noch vorhanden ist. Ein anderes Projekt lässt sich jederzeit mit **Projekt öffnen** wählen. Alle gespeicherten Änderungen sind bereits in dessen `projekt.json` gesichert.

Das Foto-Regal/Fach ist eine Vorgabe für neue Bücher. Eine spätere Änderung dieser Vorgabe verändert vorhandene Buchstandorte nicht. „Buch entfernen“ löscht nur die gewählten Datensätze. Fotos bleiben erhalten. Die unmittelbar vorherige Projektfassung liegt in `projekt.backup.json` und wird bei der nächsten erfolgreichen Speicherung ersetzt.

## Fotos und Speicherung

- JPEG, PNG und WEBP werden mit Calibres Qt-Decodern gelesen. EXIF-Orientierung gilt für Vorschau und Originalansicht.
- HEIC/HEIF wird nur gelesen, wenn Calibre einen passenden Decoder mitbringt. Auf dem getesteten Windows-System fehlt er. Solche Dateien werden mit Hinweis übersprungen; bitte auf dem Telefon als JPEG exportieren. Keine automatische Codec-Installation.
- Originalfotos werden bytegetreu nach `photos/` kopiert. Gedrehte JPEG-Vorschauen mit maximal 2400 Pixeln längster Kante liegen in `previews/`. Kleine Bilder werden nicht vergrößert. Die Originalansicht begrenzt sehr große Bilder auf 16000 Pixel längster Kante.
- Identische Fotos werden per SHA-256 übersprungen, auch bei anderem Dateinamen. Unterschiedliche Fotos überlappender Regalausschnitte werden in Phase 1 nicht zusammengeführt.
- Import läuft im Hintergrund, speichert nach jedem Foto und lässt sich abbrechen. Ein laufender Decoder beendet zuerst seine aktuelle Arbeit. Bereits importierte Fotos bleiben erhalten. Fehler erscheinen pro Datei in einer Detailansicht.
- Bilder oberhalb von 120 Megapixeln werden abgelehnt; Qt kann zusätzliche Speichergrenzen anwenden.
- Eine Dateisperre schützt Projekte vor gleichzeitiger Bearbeitung durch Plugin-Fenster. Die Speicherung erkennt zusätzlich externe Änderungen. Neue Inhalte werden erst nach vollständigem Schreiben atomar übernommen.

## Projekt und Exportformate

```text
Meine-Sammlung/
  projekt.json             # Vollständiges Datenmodell, Version 5
  projekt.backup.json      # Vorherige gespeicherte Fassung
  metadata-cache.json      # Buchdatenbankantworten; keine Schlüssel
  photos/                  # Unveränderte importierte Fotos
  previews/                # Gedrehte/verkleinerte Vorschauen
  crops/                   # Erkannte und/oder analysierte Buchrücken-Ausschnitte
  title_pages/             # Lokal zugeschnittene Titelblattfotos
  exports/                 # CSV-/JSON-Ausgaben
  .trash/                  # Entfernte Fotos und Projektstand vor dem Löschen
```

Für Umzug/Sicherung den **gesamten Projektordner** kopieren. Bildpfade sind relativ. JSON-Exporte enthalten alle Metadaten und KI-Belege, jedoch keine Bildbytes. Zum Wiederherstellen: neuen Ordner anlegen, Export als `projekt.json` darin ablegen und `photos/`, `previews/`, `crops/` und `title_pages/` aus dem zugehörigen Projekt ergänzen. Ohne Bilder bleiben Metadaten bearbeitbar; fehlende Originale werden beim Öffnen gemeldet. Die vorherige Fassung kann ebenso aus `projekt.backup.json` in einem separaten Ordner wiederhergestellt werden. Unbekannte Schemaversionen werden mit Fehlermeldung abgewiesen.

CSV: UTF-8 mit BOM, Semikolon, Kopfzeile und maskierte mehrzeilige Texte. ISBNs sind Zeichenfolgen: In Excel die ISBN-Spalten als Text importieren. Führende Zeichen, die Tabellenformeln auslösen könnten, werden mit Apostroph entschärft. JSON ist das verlustfreie Austauschformat. Unbekannte Werte erscheinen in JSON als `null`, in CSV leer. Manuelle Eingaben erhalten keine erfundene KI-Konfidenz; diese Werte bleiben `null`.

CSV bleibt ein allgemeiner Metadatenexport. Es enthält zusätzlich `crop_path`, `title_page_path`, `title_page_photo_id`, `vision_image_path`, `bounding_box` und `detection` (die letzten beiden als JSON-Zellen). JSON-Exporte enthalten auch alle Rahmen, Titelblatt- und KI-Belegpfade, deren Konfidenzen, Quellen und Prüfzeitpunkte. Der direkte Phase-5-Import legt Calibre-Datensätze ohne E-Book-Datei an. Der Status „Manuell bestätigt“ behauptet keinen Online-Treffer.

## Entwicklung und Tests

```powershell
python build_plugin.py
calibre-debug run_tests.py
calibre-debug verify_plugin.py
```

Tests verwenden temporäre Projekte, künstliche Bilder und eine automatisch gelöschte Testbibliothek. Prüffälle: ISBNs, Validierung, Wiederöffnen/Umzug, atomare Speicherung, Bildfehler, EXIF, Dubletten, Abbruch, CSV/JSON, Qt-Oberfläche, Metadatenabgleich und Calibre-Import. `verify_plugin.py` prüft die ZIP-Installation mit temporärer Calibre-Konfiguration. Die normale Calibre-Bibliothek und Benutzerkonfiguration werden nicht verwendet.

`calibre_plugin/` enthält den Calibre-Einstieg, `ui/` Qt einschließlich Kameradialog, `models.py` das Datenmodell, `persistence/` die Speicherung, `image_processing/` Import/Ausschnitte, `isbn/` ISBN-Prüfung, `import_export/` Exporte, `vision/` die Bildanbieter und `metadata_providers/` Onlineanbieter, Cache, Bewertung und Workflow. `barcode/` enthält den lokalen EAN-13-/ISBN-Kameradecoder.

Die automatischen Tests verwenden simulierte API-Antworten und verursachen keine API-Kosten. Ein separater Live-Test mit ausschließlich künstlichen Daten ist opt-in:

```powershell
calibre-debug live_vision_check.py -- --send-synthetic-image
```

## Offene Phasen

- **Phase 2 ist implementiert:** Einzelne Buchrücken, Responses API, strikter Ergebnisvertrag, Konfidenzen, Zustimmung und manuelle Prüfung. Noch ausstehend ist eine Qualitäts-/Kostenmessung an repräsentativen echten Regalfotos.
- **Phase 3 ist implementiert:** Mehrere Buchrücken, validierte Bildkoordinaten, Ausschnitte, Overlay, Gruppenmarkierung und manuelle Korrektur. Ausstehend: Erkennungsbenchmark mit echten Regalfotos; keine Garantie vollständiger oder pixelgenauer Erkennung.
- **Phase 4 ist implementiert:** Open Library, Google Books, Deutsche Nationalbibliothek und konfigurierbarer HTTPS-Anbieter; priorisierte Suche, Quellen/Abrufzeit, Cache/Offlinebetrieb, Konfliktprüfung, Bestätigung, Stapelabgleich sowie manuelle, lokale Kamera- und KI-gestützte ISBN-/Barcode-Erfassung. Zusätzlich stehen lokale Titelblattaufnahme, Drehung, Zuschnitt, Fotozuordnung und die ausdrücklich bestätigte Titelblatt-KI-Auswertung bereit.
- **Phase 5 ist implementiert:** Calibre-Datensätze ohne E-Book-Datei, exakte ISBN-Dublettenprüfung, explizite Zuordnung/Aktualisierung, optionale Cover, benutzerdefinierte Scan-Felder, Abbruch und schrittweise Projektzuordnung. Optionaler OPF-Export bleibt offen.

## Geprüfte Dokumentation

- [Calibre: Plugins entwickeln](https://manual.calibre-ebook.com/creating_plugins.html): ZIP-Struktur, Importmarker, GUI-Wrapper und InterfaceAction.
- [Calibre Plugin-API](https://manual.calibre-ebook.com/plugins.html).
- [Calibre Datenbank-API](https://manual.calibre-ebook.com/de/db_api.html): threadsichere `new_api`, Suche, Metadatenfelder und Cover.
- [OpenAI Responses API](https://developers.openai.com/api/reference/typescript/resources/beta/subresources/responses/methods/create).
- [OpenAI Bilderkennung](https://developers.openai.com/api/docs/guides/images-vision) und [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs): Grundlage für Bildinput und strikte Schemas; die dokumentierten Grenzen räumlicher Lokalisation begründen die manuelle Rahmenprüfung.
