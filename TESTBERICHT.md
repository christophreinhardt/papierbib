# Testbericht – Papierbibliothek 0.6.11

## Wartungsstand 0.6.11 – maximale Kameraauflösung und volle Titelblattauflösung

Der Kameradialog wählt automatisch das größte von der Kamera gemeldete Format
nach Pixelzahl und zeigt die verwendete Auflösung bei Titelblattaufnahmen an.
Der reale USB-Kameratest lieferte 3264 × 2448 Pixel; der lokale gedrehte
Ausschnitt wurde mit 1798 × 2400 Pixeln erzeugt. Das Bild wurde weder
gespeichert noch übertragen. **148 automatisierte Tests bestanden.**

Das Plugin-ZIP wurde anschließend mit dem echten Calibre-Plugin-Loader geprüft.
`Papierbibliothek-0.6.11.zip`: 89.344 Bytes, SHA-256
`030CB6B8D70E22232A20422EF78294A4C9506D0FD24B8C9D26FD5F8D232B2983`.

## Historie – Wartungsstand 0.6.9 – Fotos löschen

Stand: 17. September 2026. Fotoliste mit Mehrfachauswahl und Schaltfläche
**Ausgewählte Fotos löschen**, expliziter Bestätigung und Projektpapierkorb.
Bücher, Metadaten, Calibre-Zuordnung und vorhandene Ausschnitt-/KI-Belege
bleiben erhalten. Entfernte Titelblätter werden beim nächsten Öffnen nicht
erneut in die Fotoliste aufgenommen. Das Schema bleibt Version 5.

**147 automatisierte Tests bestanden**, Laufzeit 3,465 Sekunden. Sieben neue
Tests decken Erhalt der Daten und Originale, wiederherstellbare Projektkopien,
geteilte Bilddateien, Titelblattzuordnung, Speicher- und Verschiebefehler,
ungültige Auswahl sowie den UI-Ablauf mit Abbruch und Mehrfachlöschung ab.
Netzwerkzugriffe und Änderungen an Benutzerprojekten fanden nicht statt.

`Papierbibliothek-0.6.9.zip` wurde gebaut und in einer temporären
Calibre-9.14-Konfiguration erfolgreich installiert. Hauptfenster und Kameradialog
wurden über den echten ZIP-Plugin-Loader geöffnet. Das Archiv enthält 41 Dateien,
ist 88.773 Bytes groß und hat die SHA-256-Prüfsumme
`D08549DF491C7A3173118C55EC915FE32458AF7D823C9A66E5738D96C2B691C2`.

## Historie – Wartungsstand 0.6.8 – drehbares Titelblatt als Foto und KI-Quelle

Stand: 16. September 2026. Der Titelblatt-Editor besitzt nun eindeutige
Schaltflächen für 90° links und rechts. Ein gespeichertes Titelblatt wird als
normaler Fotoeintrag im Projekt geführt und kann über **Titelblatt mit KI
auswerten** erneut zugeschnitten, gedreht und nach dem ausdrücklichen Klick auf
**Kostenpflichtig auswerten** an den gewählten Anbieter gesendet werden.
Buchrückenfoto, Buchrückenausschnitt und Titelblattbeleg bleiben dabei getrennt.
Projekte aus Schema 4 ergänzen vorhandene Titelblätter beim Laden automatisch in
der Fotoliste; das aktuelle Schema ist Version 5.

**140 automatisierte Tests bestanden** im finalen Lauf in 3,204 Sekunden. Der
reale Hardwaretest mit „SunplusIT Inc“ erfasste 1280 × 720 Pixel und erzeugte
nach 90°-Drehung einen Ausschnitt mit 710 × 1270 Pixeln und 174.730 Bytes. Das
Testbild wurde weder gespeichert noch übertragen.

Das ZIP wurde in einer frischen temporären Calibre-9.14-Konfiguration als
Version 0.6.8 geladen; Haupt- und Kameradialog öffneten erfolgreich.
Paketprüfung: `Papierbibliothek-0.6.8.zip`, 85.954 Bytes, 40 Dateien, SHA-256
`1F215BE65F5E64DB2CF8184217501DDAA98DF154953645DFAB7E36E82F9E9FA0`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.7 – manuellen Buchdatensatz anlegen

Stand: 16. September 2026. Die bisherige Schaltfläche „Buch erfassen“ heißt nun
eindeutig **Buchdatensatz manuell anlegen**. Der Dialog kann vollständige
Metadaten oder einen komplett leeren Entwurf mit Status „Prüfen“ speichern.
Nach erfolgreichem atomarem Projektspeichern wird der neue Datensatz ausgewählt,
sodass unmittelbar Titelblatt, ISBN oder Barcode ergänzt werden können. ISBN-10
wird weiterhin in ISBN-13 umgerechnet; eine ISBN, die bereits einem anderen
Projektbuch gehört, wird nicht erneut gespeichert. Die Speichern-Schaltfläche
ist die Standardaktion.

**138 automatisierte Tests bestanden** im finalen Lauf in 3,258 Sekunden. Das
ZIP wurde in einer frischen temporären Calibre-9.14-Konfiguration als Version
0.6.7 geladen; Haupt- und Kameradialog öffneten erfolgreich. Paketprüfung:
`Papierbibliothek-0.6.7.zip`, 84.611 Bytes, 40 Dateien, SHA-256
`8D2E9E8FFBFA0C764AF85CEA0C3E34EC13391F27101144AA7CBE61280C74D4FE`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.6 – lokale Titelblattaufnahme

Stand: 16. September 2026. Neu sind **Titelblatt fotografieren** und
**Titelblatt anzeigen** für den ausgewählten Buchdatensatz. Der getrennte
Kameramodus führt keine Barcode- oder KI-Erkennung aus; erst der ausdrückliche
Aufnahmeklick übernimmt ein Frame. Danach ermöglicht der lokale Editor freie
Rechteckauswahl, Ganzbild, Einpassen, 90°-Drehungen und eine Vorschau. Das
bereinigte JPEG wird atomar unter `title_pages/` gespeichert und über
`title_page_path` im neuen Projektschema 4 zugeordnet. Buchrückenbilder bleiben
unverändert. CSV/JSON und Calibres optionales Feld `#scan_image` berücksichtigen
den Titelblattpfad.

**137 automatisierte Tests bestanden** im Vorab-Lauf in 3,120 Sekunden. Der
reale Hardwaretest mit „SunplusIT Inc“ erfasste ein Frame mit 1280 × 720 Pixeln
und erzeugte daraus lokal ein JPEG mit 151.032 Bytes. Das Testbild wurde weder
gespeichert noch übertragen.

Das ZIP wurde in einer frischen temporären Calibre-9.14-Konfiguration als
Version 0.6.6 geladen; Haupt- und Kameradialog öffneten erfolgreich.
Paketprüfung: `Papierbibliothek-0.6.6.zip`, 84.363 Bytes, 40 Dateien, SHA-256
`8B209D92F08D9FFB77CDA5EC3F1336D96DA6CE3B0BD5AA4910A9B106CC3DC988`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.5 – Erkennung außerhalb des UI-Threads

Stand: 16. September 2026. Die Windows-Ereignisanzeige weist die beiden vom
Benutzer beobachteten Fehler ausdrücklich als `AppHangB1` von Calibre 9.14 aus,
nicht als nativen Prozessabsturz. Version 0.6.4 begrenzte zwar einen einzelnen
Decoderlauf, startete ihn aber weiterhin regelmäßig im UI-Thread.

Die Barcodeerkennung läuft nun in genau einem separaten `QThread`. Solange er
beschäftigt ist, werden neue Frames verworfen und nicht aufgestaut. Beim
Schließen bleibt ein noch aktiver Arbeiter bis zu seinem natürlichen Ende
referenziert, damit Qt keinen laufenden Thread zerstört. Ein Regressionstest
weist nach, dass ein absichtlich blockierter Decoder den Kameracallback sofort
zurückgibt und kein zweiter Auftrag eingereiht wird.

**133 automatisierte Tests bestanden** im Vorab-Lauf in 3,075 Sekunden. Im
fünfsekündigen Hardware-Dauertest lieferte die Kamera „HD USB Camera“ 57 Frames
mit 1024 × 768 Pixeln; zugleich wurden 45 von 50 erwarteten UI-Heartbeats
verarbeitet. Es wurde kein Bild gespeichert oder übertragen.

Das ZIP wurde in einer frischen temporären Calibre-9.14-Konfiguration als
Version 0.6.5 geladen; Haupt- und Kameradialog öffneten erfolgreich.
Paketprüfung: `Papierbibliothek-0.6.5.zip`, 82.522 Bytes, 39 Dateien, SHA-256
`896B3CF299D39C127D6EF1BB661ED20E157052A68396F487FF0AA12E96706017`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.4 – Kameraabsturz behoben

Stand: 16. September 2026. Ein kontrastreiches Worst-Case-Bild reproduzierte
den Fehler: Der Decoder war nach 30 Sekunden noch nicht fertig und blockierte
den UI-Thread. Nach Begrenzung und Priorisierung der Barcodekandidaten benötigt
dasselbe Bild 0,307 Sekunden. Fehlerhafte Frames werden im Qt-Callback
abgefangen, Bilddaten vor der Verarbeitung vom Multimedia-Puffer getrennt und
das Schließen des Dialogs wird aus dem Videocallback heraus verzögert.

**132 automatisierte Tests bestanden** im finalen Lauf in 3,074 Sekunden,
einschließlich Laufzeitgrenze und simuliertem Decoderfehler. Der reale
Hardwaretest empfing vier Frames mit 1280 × 720 Pixeln von „SunplusIT Inc“ und
beendete den Dialog verzögert außerhalb des Videocallbacks. Es wurde kein Bild
gespeichert oder übertragen.

Das ZIP wurde in einer frischen temporären Calibre-9.14-Konfiguration als
Version 0.6.4 geladen; Haupt- und Kameradialog öffneten erfolgreich.
Paketprüfung: `Papierbibliothek-0.6.4.zip`, 82.109 Bytes, 39 Dateien, SHA-256
`47740202B5B97EB7BBE9BEDDFAAF17FC0B910175441A3673182DCA110C6DB659`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.3 – robustere lokale Barcodeerkennung

Stand: 16. September 2026. **130 automatisierte Tests bestanden** im finalen
Lauf in 2,812 Sekunden. Neu geprüft sind perspektivisch veränderliche
Modulbreiten, ein um 11 Grad gedrehtes Kamerabild und das Überbrücken eines
einzelnen unlesbaren Frames. Der Decoder normalisiert nun jedes EAN-Ziffernmuster
separat, prüft ISBN-Präfix und Prüfziffer und wertet zusätzlich diagonale
Scanlinien mit Rauschmittelung aus.

Gedruckte ISBN-Ziffern ohne lesbaren Barcode werden weiterhin nicht lokal per
OCR erkannt. Dafür steht nur der ausdrücklich bestätigte, kostenpflichtige
KI-Fallback bereit; Kameraframes werden nicht automatisch gespeichert oder
übertragen.

Der reale Hardwaretest aktivierte die Kamera „SunplusIT Inc“, empfing fünf
Frames mit 1280 × 720 Pixeln und speicherte oder übertrug kein Bild. Ein echter
Buchbarcode war dabei nicht Teil des automatisierten Tests. Das ZIP wurde in
einer frischen temporären Calibre-9.14-Konfiguration als Version 0.6.3 geladen;
Haupt- und Kameradialog öffneten erfolgreich. Paketprüfung:
`Papierbibliothek-0.6.3.zip`, 81.496 Bytes, 39 Dateien, SHA-256
`2E1999160710537AAC5D35E640206C8E874D8215352742F7759238872E6C0128`.
Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.2 – Kamera verwendet nur lobid

Stand: 16. September 2026. **128 automatisierte Tests bestanden** im finalen
Lauf in 2,699 Sekunden. Der Kameraablauf übergibt ausschließlich einen
`LobidProvider`; Google Books wird dabei unabhängig von den Einstellungen nicht
instanziiert oder abgefragt. lobid ist zusätzlich als regulär auswählbare
Metadatenquelle verfügbar, während Google Books bei neuen Konfigurationen
standardmäßig deaktiviert ist. Parser und Anfrage `q=isbn:…` sind gegen eine
gespeicherte reale lobid-Antwort getestet. Mehrere lobid-Katalogkopien derselben
exakten ISBN werden innerhalb des Adapters auf den vollständigsten Datensatz
reduziert, damit interne Katalogunterschiede keinen falschen Ausgabenkonflikt
erzeugen.

Der reale End-to-End-Test mit ISBN `9783150099001` fragte ausschließlich lobid
ab und übernahm „Die Verwandlung“, Franz Kafka und die ISBN automatisch in ein
anschließend gelöschtes Testprojekt. Die normale Calibre-Bibliothek blieb
unverändert.

Paketprüfung: `Papierbibliothek-0.6.2.zip`, 79.958 Bytes, 39 Dateien,
SHA-256 `FF8C90E891D8A55FAC8D80FA929AC914E0CBF00AFB2068C8AA3063DE9A695D2C`.
Calibre 9.14 lud Version 0.6.2 sowie Haupt- und Kameradialog aus einer
temporären Installation. Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Wartungsstand 0.6.1

Stand: 14. September 2026. **126 automatisierte Tests bestanden** im finalen
Lauf in 2,811 Sekunden. Zwei zusätzliche Prüfungen laden die Projektdatei nach
einem Provider-Netzwerkfehler beziehungsweise ohne aktivierte Datenquelle neu.
In beiden Fällen ist ISBN `9783150099001` dauerhaft vorhanden. Die Oberfläche
meldet: „ISBN gespeichert; Online-Abfrage nicht erfolgreich. Später erneut
abgleichen.“

Paketprüfung: `Papierbibliothek-0.6.1.zip`, 78.638 Bytes, 39 Dateien,
SHA-256 `10A1CFB1A2C06D18C9764D0A92919A7197BBB70881630E5D134F066861BED4D6`.
Calibre 9.14 lud Version 0.6.1 sowie Haupt- und Kameradialog aus einer
temporären Installation. Der Inhalts- und Geheimnisscan war ohne Befund.

## Historie – Kamera-Schnellerfassung 0.6.0

Stand: 14. September 2026. Windows, Calibre 9.14 mit gebündeltem Python 3.14.7 und Qt 6.10.1.

- **124 automatisierte Tests bestanden** im finalen Lauf in 2,642 Sekunden.
- Neu geprüft: EAN-13-Modulmuster, ISBN-Präfix und Prüfziffer, skalierte und gespiegelte Scanlines, geringe Guard-Beschädigung, synthetisches QImage-Kameraframe, fehlendes Kameragerät, automatischer exakter Metadatenabgleich sowie projektinterne Dublettenvermeidung.
- Der Decoder benötigt keine zusätzliche Bibliothek. Er verarbeitet Kameraframes ausschließlich lokal und akzeptiert erst zwei identische gültige Lesungen. Nur der separate KI-Textfallback kann nach der vorhandenen Vorschau und ausdrücklichen Zustimmung ein Einzelbild übertragen.
- Exakte konfliktfreie ISBN-Treffer können im neuen Kameraworkflow automatisch auf den neu angelegten Projektdatensatz angewendet werden. Schwache oder widersprüchliche Treffer bleiben prüfpflichtig. Der Calibre-Import bleibt separat und bestätigungspflichtig.

- Hardware-Smoke-Test erfolgreich: Die vorhandene USB-Kamera (`SunplusIT Inc`)
  lieferte drei Frames mit 1280 × 720 Pixeln. Es wurde kein Frame gespeichert
  oder übertragen.
- Live-End-to-End-Test erfolgreich: ISBN `9783150099001` wurde über Open Library
  abgefragt und im automatisch gelöschten Testprojekt als „Die Verwandlung“ von
  Franz Kafka automatisch übernommen. Die normale Calibre-Bibliothek blieb
  unverändert. DNB antwortete im getrennten Live-Test ebenfalls; Google Books
  behandelte das aktuelle HTTP-429-Limit erwartungsgemäß als Providerfehler.
- **Papierbibliothek-0.6.0.zip** wurde gebaut: 78.427 Bytes, 39 Dateien,
  SHA-256 `E0BD84FA0390CB4DF1BC80C256658955338F45363E50DA7FFE542799F9C47895`.
  Calibres echter Plugin-Lader erkannte Version 0.6.0 in einer temporären
  Konfiguration und öffnete Haupt- sowie Kameradialog direkt aus der ZIP.
  Der Archivscan fand weder Bytecode/Cachedateien noch typische
  OpenAI-/Gemini-Schlüsselmuster.

Ein Qualitätsbenchmark mit einer repräsentativen Auswahl realer Buchbarcodes
steht weiterhin aus.

## Historie – Wartungsstand 0.5.4

Stand: 13. September 2026. Windows, Calibre 9.14 mit gebündeltem Python 3.14.7 und Qt 6.10.1.

- **119 automatisierte Tests bestanden** im finalen Lauf in 2,638 Sekunden. Neu geprüft sind die feste Schaltflächenreihenfolge **Speichern und bestätigen**, **Als Entwurf speichern**, **Nachscan nötig**, **Später prüfen**, die links außen stehende Bestätigungsaktion als Qt-Standardbutton und deaktiviertes Auto-Default der Nebenaktionen. Rahmenauswahl, Upload-Zustimmung, automatisches Projektladen, KI-Doppelklick, Entwurfsspeicherung und alle Phase-5-Prüfungen bleiben grün.
- Zusätzlich zu den Mocks wurde ein echter Schreib-/Lesezyklus gegen eine kurze, automatisch gelöschte temporäre Calibre-Bibliothek ausgeführt. Ein Papierbuch ohne E-Book-Datei wurde angelegt, über ISBN wiedergefunden und mit Titel, zwei Autoren und Tag Papierbuch zurückgelesen. Keine normale Benutzerbibliothek wurde geöffnet oder verändert.
- Der Adapter verwendet die mit Calibre 9.14 geprüfte threadsichere new_api mit create_book_entry, search, get_metadata, set_field und set_cover. Ein Bibliothekswechsel zwischen Vorschau und Bestätigung wird erkannt und verhindert den Schreibvorgang.
- Vorhandene ISBNs sind standardmäßig abgewählt und werden nicht erneut angelegt. Aktualisierungen brauchen eine konkrete Calibre-ID und doppelte Nutzerbestätigung. Nichtleere Projektwerte werden gesetzt; andere Identifikatoren und vorhandene Tags werden zusammengeführt.
- Online-Cover sind opt-in, HTTPS-/Host-beschränkt, ohne Weiterleitungen und auf 10 MB begrenzt. Custom Fields werden nur gesetzt, wenn sie bereits mit unterstütztem Datentyp existieren; Fehler dort verhindern nicht den übrigen Datensatzimport.
- Hauptfenster und Importvorschau wurden mit synthetischen Daten offscreen gerendert. Importvorschau, Dubletten-IDs, Aktionen und Cover-Opt-in sind ohne Zugriff auf eine echte Sammlung darstellbar.
- **Papierbibliothek-0.5.4.zip** wurde gebaut (73.239 Bytes, 37 Dateien), in einer frischen temporären Calibre-Konfiguration installiert und durch den echten Plugin-Lader als Version 0.5.4 geladen. Der Dialog wurde geöffnet und geschlossen, die geänderte KI-Prüfansicht wurde neu gerendert und im ZIP wurden keine typischen OpenAI-/Gemini-Schlüsselmuster gefunden.

Bekannte Grenzen: macOS/Linux sind nicht praktisch getestet. Ein Import besteht aus mehreren Calibre-API-Aufrufen und kann nach einem Prozessabsturz teilweise abgeschlossen sein; nach normalem Abbruch bleiben bereits bestätigte Datensätze absichtlich erhalten und sind im Projekt zugeordnet. Optionaler OPF-Export, lokaler Barcode-Decoder und eigener Titelblattmodus bleiben offen.

## Historie – Phase 4

Stand: 13. September 2026. Windows, Calibre 9.14 mit gebündeltem Python 3.14.7 und Qt 6.10.1.

- **102 automatisierte Tests bestanden** in 2,042 Sekunden. Neu geprüft sind Open Library, Google Books, DNB-MARC21, eigener HTTPS-JSON-Anbieter, bereinigte Providerfehler, exakte ISBN-Filterung, priorisierte Suchstufen, Cache/Offlinebetrieb, Teilausfälle, Abbruch, schrittweiser Stapelabgleich, Zusammenführung/Bewertung, Konfliktsperre, ausdrückliche Trefferübernahme sowie streng validierte ISBN-/Barcodefoto-Antworten von OpenAI und Gemini.
- Alle regulären Netzwerk- und KI-Tests verwenden Mocks. Testprojekte, Bilder und Calibre-Konfigurationen sind temporär oder synthetisch. Eine zuvor lokale Gemini-Auswahl beeinflusst die Tests nicht mehr; die UI-Workflows wählen ihre Fake-Provider explizit und können daher keine echte API versehentlich aufrufen.
- Live-Smoke-Test mit ISBN 9783150099001: Open Library lieferte einmal erfolgreich die editionsspezifische Ausgabe „Die Verwandlung“ und war bei der Wiederholung transient nicht erreichbar; DNB lieferte gültige MARC21-Datensätze, deren Steuerzeichen korrekt bereinigt wurden. Google Books antwortete mit HTTP 429. Beide Fehlerzustände wurden erwartungsgemäß als nutzerfreundliche Providerfehler behandelt, ohne den übrigen Abgleich abzubrechen.
- Der Live-Test deckte eine reale Open-Library-Falle auf: Die allgemeine Suche liefert Werke mit vielen Ausgaben. ISBN-Abfragen verwenden jetzt den offiziellen editionsspezifischen Books-Endpunkt und übernehmen nie eine beliebige erste ISBN aus einem Werk. Google-Books- und DNB-Ergebnisse werden zusätzlich auf dieselbe angefragte ISBN-13 gefiltert.
- ISBN-/Barcodefotos verwenden denselben expliziten Upload-Consent wie andere Bilder. Das lokale strikte Schema akzeptiert Rohtext und Kandidaten, aber eine Übernahme erfolgt nur bei genau einer lokal prüfziffervaliden ISBN und nach einer zweiten Nutzerbestätigung. Ein lokaler Barcode-Decoder ist mangels geeigneter Bibliothek in der getesteten Calibre-Laufzeit noch nicht enthalten.
- Die Phase-4-Oberfläche wurde mit synthetischen Daten offscreen gerendert. Der vergrößerte Einstellungsdialog umfasst getrennte OpenAI-/Gemini-Wahl, Datenbankauswahl, Offlinebetrieb, Treffergrenze und eigenen Anbieter. Keine privaten Fotos wurden verwendet.
- **Papierbibliothek-0.4.0.zip** wurde gebaut (65.077 Bytes) und in einer frischen temporären Calibre-Konfiguration installiert. Der echte Calibre-Plugin-Lader meldete Version 0.4.0, lud die Aktion und öffnete/schloss den Phase-4-Dialog. Normale Calibre-Konfiguration und Bibliothek blieben unverändert.

Bekannte Grenzen: Google Books war beim Live-Test rate-limitiert; macOS/Linux sind nicht praktisch ausgeführt. Onlinequellen können dieselbe ISBN für mehrere Druckjahre führen – solche Unterschiede werden absichtlich als Konflikt zur manuellen Prüfung angezeigt. Direkter Calibre-Import, bibliotheksweite Dublettenprüfung, benutzerdefinierte Calibre-Felder, lokaler Barcode-Decoder und eigener Titelblattmodus folgen in Phase 5 beziehungsweise als Ergänzung.

## Historie – Gemini-Erweiterung 0.3.1

Stand: 13. September 2026. Windows, Calibre 9.14 mit gebündeltem Python/Qt.

- **82 automatisierte Tests bestanden**: die 62 bisherigen Tests plus 20 Gemini-Prüfungen. Abdeckung: Anbieterwahl, getrennte Modelle und Schlüssel, keine Schlüssel in Einstellungen/Requests/Ergebnissen, klare Empfängerzustimmung, keine Anfragen ohne Zustimmung, kein Anbieter-Fallback, Abbruch, fehlende Schlüssel, HTTP-/Netzwerkfehler, ungültige/abgelehnte/abgeschnittene Antworten, Prompt-Blockierung, Typen/Grenzwerte, Tokenzählung, Schema-Kompatibilität ohne Mutation und beide Qt-Hintergrundworkflows bis zur dauerhaften Speicherung.
- **Live-Einzelbuchtest erfolgreich** mit `gemini-3.5-flash-lite` und `generateContent`. Künstliches Bild: „DAS BLAUE REGAL“, „LENA WINTER“, „NORDLICHT VERLAG“ korrekt erkannt; 1253 Input-, 279 Outputtokens.
- **Live-Regaltest erfolgreich**: alle drei künstlichen Buchbereiche erkannt; 1254 Input-, 257 Outputtokens. Kein Benchmark für echte Regale und keine Garantie pixelgenauer Lokalisation.
- Der zunächst geprüfte Interactions-Endpunkt und Generation mit Gemini 2.5 Flash-Lite lieferten HTTP 404. Modellauflistung allein erwies sich deshalb nicht als ausreichender Verfügbarkeitsnachweis. Gemini 3.5 Flash-Lite funktioniert über `generateContent` und ist nun die Voreinstellung.
- Die verschachtelte Regal-Schemavariante wurde zunächst mit HTTP 400 abgelehnt. Nach Entfernen der Zahlen-/Array-Grenzen ausschließlich aus dem gesendeten Schema war der Live-Test erfolgreich. Alle ursprünglichen Limits werden weiterhin lokal geprüft; eigene Regressionstests verhindern eine Aufweichung der Ergebnisvalidierung.
- Anbieter-Einstellungen und Gemini-Uploadvorschau mit künstlichen Daten visuell geprüft: `test-results/ki-anbieter.png`, `test-results/gemini-upload.png`. Keine privaten Fotos verwendet; Schlüsselwerte nicht ausgegeben.

`Papierbibliothek-0.3.1.zip` wurde gebaut (50.311 Bytes) und erfolgreich in einer temporären Calibre-Konfiguration installiert. Der echte Plugin-Lader lädt Aktion und Dialog aus dem ZIP; das Fenster wurde geöffnet und geschlossen. Finaler Testlauf: 82 Tests in 1,718 Sekunden ohne Prozessstart. Die normale Bibliothek und Konfiguration blieben unverändert. macOS/Linux sowie Erkennungsqualität mit echten Regalfotos bleiben ungetestet.

## Historie – Phase 3 (0.3.0)

Windows, Calibre 9.14, Python 3.14.7, Qt 6.10.1. Testlauf vom 12. September 2026.

- **62 automatisierte Tests bestanden**: alle bisherigen 46 Tests plus 16 neue Prüfungen für Phase 3. Netzwerkaufrufe simuliert; keine privaten Fotos hochgeladen und kein kostenpflichtiger Regal-Live-Test ausgeführt.
- Neue Abdeckung: striktes Regalschema, Ganzzahl-/Grenz-/Konfidenzvalidierung, maximal 60 Bereiche, Consent und Refusal, EXIF-orientierte Koordinaten und Teilbild-Rückrechnung, Gruppenstatus, Ausschnittdateien, Originalschutz, geometrische Wiederholungs-Dubletten, Überlappungswarnungen, unvollständige/zu kleine Bereiche, Abbruch und Speicherfehler, Migration 1/2→3, manuelle Rahmenkorrektur/-ergänzung, Ignorieren, Gruppenbestätigungsschutz, CSV-/JSON-Roundtrip mit Koordinaten und Quellen.
- Qt-End-to-End-Test: Original im Hintergrund laden → bestätigter Upload → simulierte Regal-Erkennung nachweislich außerhalb des UI-Threads → atomare Speicherung → Rahmeneditor später verlassen → Vorschläge wieder laden.
- **ZIP 0.3.0 gebaut und isoliert installiert**. Calibres echter Plugin-Lader lädt Aktion und Phase-3-Dialog aus dem Archiv; Fenster geöffnet und geschlossen. Normale Calibre-Konfiguration und Bibliothek nicht verändert.
- Rahmeneditor und Uploadvorschau mit künstlichem Regalbild gerendert und visuell geprüft. Bilder passen vollständig in die Ansichten; Bedienelemente lesbar. Ausgewählter Rahmen blau, unsichere Gruppen rot. Dateien: `test-results/regal-rahmen.png`, `test-results/regal-upload.png`, `test-results/hauptfenster.png`.

**Grenzen:** Kein Qualitäts-/Kostenbenchmark mit echten Regalfotos; Erkennungsgenauigkeit, vollständige Buchzählung und pixelgenaue Grenzen nicht nachgewiesen. Bounding Boxes sind achsenparallel. Metadaten werden nach der Regalaufteilung separat je Buch ausgewertet. macOS/Linux und ältere Calibre-Versionen nicht ausgeführt. Die bekannten Qt-Offscreen-Warnungen zu Fonts/propagateSizeHints verhindern die Tests nicht. Für Bildschirmprüfungen wird die vorhandene Windows-Schrift geladen.

## Historie – Phase 2 (0.2.0)

Testumgebung: Windows mit Calibre 9.14, Python 3.14.7 und Qt 6.10.1. Testlauf vom 12. September 2026.

- **46 automatisierte Tests bestanden**, letzter Lauf 1,054 Sekunden ohne Prozessstart: alle 26 Phase-1-Tests und 20 neue Prüfungen für Phase 2.
- Neue Abdeckung: strikte JSON-Antworten mit Pflichtfeldern/Typen/Konfidenzen, doppelte Schlüssel/NaN, Refusal/unvollständige Antworten, Responses-Requestformat, keine Anfrage ohne Zustimmung, fehlender Schlüssel, bereinigte Fehlermeldungen, HTTP 429/Quota, keine Weiterleitung von Schlüsseln, Projektmigration 1→2, Ausschnitt/Drehung/Metadatenentfernung, erneute Zustimmung bei verändertem Ausschnitt, dauerhafte Vorschläge ohne Überschreiben alter Daten, schlechte Lesbarkeit/ungültige ISBN, selektive manuelle Übernahme, Abbruch, Vorschlag später bearbeiten, Konfidenzen nach manuellen Korrekturen und Freigabe des Sitzungsschlüssels beim Schließen.
- **Echter API-Test erfolgreich** mit `gpt-5.6-luna`, Responses API, Bilddetail `high`, Reasoning `none`, strengem JSON-Schema. Übertragen wurde nur ein selbst erzeugter künstlicher Buchrücken. Ergebnis: „Das blaue Regal“, „Lena Winter“, „Nordlicht Verlag“. Verbrauch: 1177 Input- und 149 Outputtokens. Keine privaten Regalfotos verwendet.
- **ZIP 0.2.0 gebaut und isoliert installiert**: Calibres Plugin-Lader lädt Aktion und Phase-2-Dialog erfolgreich aus dem ZIP. Normale Calibre-Konfiguration/Bibliothek nicht verändert.
- Hauptfenster, Ausschnittauswahl und Prüfoberfläche mit künstlichen Daten gerendert und visuell geprüft. Die abschließende Sichtprüfung nach der Unterbrechung bestätigt korrekt eingepasste Bilder und lesbare Bedienelemente. Vorschauen: `test-results/ki-ausschnitt.png`, `test-results/ki-pruefen.png`, `test-results/hauptfenster.png`.

Die künstliche Aufnahme bestätigt technische Anbindung und grundlegende Erkennung, aber nicht die Qualität bei realen, schrägen oder verdeckten Buchrücken. Eine repräsentative Qualitäts-/Kostenmessung mit echten Aufnahmen steht aus. macOS/Linux wurden nicht ausgeführt. Der günstigste geeignete Modus für reale Aufnahmen ist noch nicht durch Vergleichsmessungen bestimmt; Luna ist eine günstige aktuelle Voreinstellung.

## Historie – Phase 1 (0.1.0)

Stand: 12. September 2026. Windows, Calibre 9.14, Python 3.14.7, Qt 6.10.1.

## Ergebnis

- `calibre-debug run_tests.py`: **26 Tests erfolgreich**, letzter Lauf 0,731 Sekunden (ohne Prozessstart).
- `python build_plugin.py`: `dist/Papierbibliothek-0.1.0.zip` erzeugt.
- `calibre-debug verify_plugin.py`: finales ZIP in temporärer Calibre-Konfiguration installiert; Calibre-Aktionsklasse und Dialog erfolgreich aus dem ZIP geladen, Dialog geöffnet und geschlossen.
- `calibre-debug render_preview.py`: Hauptfenster mit künstlichem Regalbild und fünf Büchern sowie Bucheditor gerendert und visuell geprüft. Vorschauen: `test-results/hauptfenster.png`, `test-results/buch-erfassen.png`.

## Abdeckung

13 Kerntests: ISBN-Prüfziffern und Konvertierung; unbekannte Konfidenzen; fehlerhafte Jahre/ISBNs; Pflichtfeld bei manueller Bestätigung; Unicode-/Null-Roundtrip; Schutz vorhandener Ordner; atomare Dateispeicherung bei Fehlern; Backup und konkurrierende Änderungen; Schemaversion/Referenzen; Pfade innerhalb des Projekts; CSV mit Umlauten, führender ISBN-Null, mehrzeiligen Texten und Formelschutz; JSON-Export/Wiederherstellung; Schutz vor Überschreiben von Projektdateien beim Export.

13 Bild-/Oberflächentests: unveränderte Originalbytes; EXIF-Drehung; Verkleinerung; rekursiver Ordnerimport und Inhaltsdubletten; beschädigtes Bild neben gültigem Bild; Abbruch während und vor Import; verschobene Projekte; Bucheditor samt ISBN-Konvertierung; ungültige Eingabe und Abbrechen; Projektsperre; Hintergrundimport → Erfassung → Filter → Export → Wiederöffnen; 600 Bücher mit Sortierung und korrekter Datensatzzuordnung.

Die ersten Läufe fanden zwei Windows-Randfälle, die behoben und erneut geprüft wurden: offener Bilddecoder bei fehlerhafter Datei und eine Sperre bei erneutem Schließen eines bereits unsichtbaren Dialogs. In der Sichtprüfung wurden zu schmale Eingabefelder korrigiert.

## Grenzen

Qt meldet beim unsichtbaren Testbetrieb fehlende mitgelieferte Fonts und `propagateSizeHints`. Beide verhindern die Tests nicht; für die Sichtprüfung wurde die vorhandene Windows-Schrift Segoe UI geladen.

Keine Tests unter macOS/Linux oder älteren Calibre-Versionen. Keine realen Regalaufnahmen verwendet. HEIC-Decoder fehlt in dieser Windows-Installation; JPEG, PNG und WEBP stehen laut Qt zur Verfügung. KI, Online-Datenbanken, Barcode-Erkennung und das Schreiben in die echte Calibre-Bibliothek sind nicht Teil von Phase 1.

Das Plugin wurde ausschließlich in der temporären Testkonfiguration installiert. Die normale Calibre-Konfiguration und Bibliothek wurden nicht verändert.
