"""Private vision gateway for Papierbibliothek mobile web app.

API keys never leave this container. Images are processed in memory and are not
written to disk or logged. The service is intentionally stateless.
"""
from __future__ import annotations

import base64
import json
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

APP_VERSION = "0.1.0"
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", "12000000"))
API_TOKEN = os.getenv("PAPIERBIB_API_TOKEN", "").strip()
AI_PROVIDER = os.getenv("AI_PROVIDER", "openai").strip().lower()
OPENAI_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
GEMINI_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-2.0-flash")

SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "title": {"type": ["string", "null"]},
        "subtitle": {"type": ["string", "null"]},
        "author": {"type": ["string", "null"]},
        "publisher": {"type": ["string", "null"]},
        "year": {"type": ["string", "null"]},
        "isbn10": {"type": ["string", "null"]},
        "isbn13": {"type": ["string", "null"]},
        "language": {"type": ["string", "null"]},
        "rawText": {"type": ["string", "null"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["title", "subtitle", "author", "publisher", "year", "isbn10", "isbn13", "language", "rawText", "confidence"],
}

app = FastAPI(title="Papierbibliothek API", version=APP_VERSION)
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

class IsbnRequest(BaseModel):
    isbn: str


def authorized(value: str | None) -> None:
    if not API_TOKEN or value != f"Bearer {API_TOKEN}":
        raise HTTPException(status_code=401, detail="Ungültiges oder fehlendes Zugriffstoken")


def media_type(upload: UploadFile) -> str:
    value = (upload.content_type or "").lower()
    return value if value in {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"} else "image/jpeg"

async def read_image(upload: UploadFile) -> tuple[bytes, str]:
    data = await upload.read(MAX_IMAGE_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Leeres Bild")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Bild ist zu groß")
    return data, media_type(upload)


def prompt(kind: str) -> str:
    return ("Analysiere dieses Foto eines deutschen Buches. Extrahiere nur Angaben, die "
            "im Bild erkennbar sind. Erfinde niemals ISBNs. Setze unbekannte Werte auf null. "
            "Trenne Autor und Titel sorgfältig. Gib alle Felder gemäß JSON-Schema zurück. "
            f"Aufnahmeart: {kind}.")


def openai_text(payload: dict[str, Any]) -> str:
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if isinstance(content, dict) and content.get("text"):
                return content["text"]
    return payload.get("output_text", "")

async def call_openai(data: bytes, mime: str, kind: str) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY ist im Backend nicht gesetzt")
    body = {
        "model": OPENAI_MODEL,
        "input": [{"role": "user", "content": [
            {"type": "input_text", "text": prompt(kind)},
            {"type": "input_image", "image_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"},
        ]}],
        "text": {"format": {"type": "json_schema", "name": "book_metadata", "strict": True, "schema": SCHEMA}},
    }
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"OpenAI-Fehler HTTP {response.status_code}")
    try:
        result = json.loads(openai_text(response.json()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Ungültige strukturierte OpenAI-Antwort") from exc
    return result

async def call_gemini(data: bytes, mime: str, kind: str) -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY ist im Backend nicht gesetzt")
    body = {"contents": [{"parts": [{"text": prompt(kind)}, {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode('ascii')}}]}], "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.post(url, params={"key": key}, json=body)
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail=f"Gemini-Fehler HTTP {response.status_code}")
    try:
        text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail="Ungültige strukturierte Gemini-Antwort") from exc


def clean_isbn(value: Any) -> str | None:
    if not value:
        return None
    text = re.sub(r"[^0-9Xx]", "", str(value)).upper()
    return text if len(text) in (10, 13) else None

async def vision(data: bytes, mime: str, kind: str) -> dict[str, Any]:
    result = await (call_gemini(data, mime, kind) if AI_PROVIDER == "gemini" else call_openai(data, mime, kind))
    result["isbn10"] = clean_isbn(result.get("isbn10"))
    result["isbn13"] = clean_isbn(result.get("isbn13"))
    result["source"] = AI_PROVIDER
    result["captureType"] = kind
    return result

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "version": APP_VERSION, "provider": AI_PROVIDER, "configured": bool(API_TOKEN)}

@app.post("/api/vision/{kind}")
async def vision_endpoint(kind: str, image: UploadFile = File(...), authorization: str | None = Header(default=None)) -> dict[str, Any]:
    if kind not in {"book-spine", "title-page"}:
        raise HTTPException(status_code=404, detail="Unbekannter Aufnahmetyp")
    authorized(authorization)
    data, mime = await read_image(image)
    return await vision(data, mime, kind)

@app.post("/api/lookup/isbn")
async def lookup_isbn(request: IsbnRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    authorized(authorization)
    isbn = re.sub(r"[^0-9Xx]", "", request.isbn).upper()
    if len(isbn) not in (10, 13):
        raise HTTPException(status_code=400, detail="Ungültige ISBN")
    params = {"q": f"isbn:{isbn}", "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=float(os.getenv("LOBID_TIMEOUT_SECONDS", "12"))) as client:
            response = await client.get("https://lobid.org/resources/search", params=params, headers={"Accept": "application/json", "User-Agent": "Papierbibliothek-API/0.1"})
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="lobid ist derzeit nicht erreichbar") from exc