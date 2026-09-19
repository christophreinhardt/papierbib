# Papierbibliothek Vision-Backend

Privater API-Gateway für die mobile GitHub-Pages-App. Der Container verarbeitet
Buchrücken- und Titelblattfotos im Speicher und ruft wahlweise OpenAI Responses
oder Gemini auf. API-Schlüssel werden niemals an den Browser ausgeliefert.

## OrbStack starten

```sh
cp .env.example .env
# .env bearbeiten: PAPIERBIB_API_TOKEN und genau einen KI-Schlüssel setzen
docker compose up -d --build
curl http://localhost:8080/api/health
```

Für das iPhone darf die API nicht als ungeschütztes `http://` aus einer
HTTPS-GitHub-Page aufgerufen werden. Verwende einen HTTPS-Reverse-Proxy oder
einen privaten Tailscale-FQDN und trage dessen Origin in `CORS_ORIGINS` ein.
Das Zugriffstoken wird nur als Bearer-Token an das Backend gesendet.

## Endpunkte

- `GET /api/health` – Status ohne Authentifizierung
- `POST /api/vision/book-spine` – Multipart-Feld `image`
- `POST /api/vision/title-page` – Multipart-Feld `image`
- `POST /api/lookup/isbn` – JSON `{ "isbn": "..." }`

Alle außer `/api/health` benötigen `Authorization: Bearer ...`. Bilder werden
nicht auf Datenträger geschrieben und nicht protokolliert. Größenlimit und
Timeout sind über `.env` konfigurierbar.

## Anbieter

`AI_PROVIDER=openai` verwendet die Responses API und Structured Outputs.
`AI_PROVIDER=gemini` verwendet die JSON-Ausgabe von Gemini. Der Anbieter kann
ohne Änderung am Frontend gewechselt werden.