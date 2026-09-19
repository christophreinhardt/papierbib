"""Same-origin PWA with ISBN recognition. Legacy app.py is intentionally not mounted."""
import asyncio
import hashlib
import hmac
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from .config import Settings, VERSION
from .images import CropSpec, InvalidImage, crop_image
from .storage import Store
from .records import BookInput, LookupRequest
from . import lobid, ocr, vision

COOKIE = 'papierbib_session'

class Login(BaseModel):
    password: str = Field(min_length=1, max_length=512)

class NewProject(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)

class TooLarge(Exception):
    pass

async def bounded_body(request, maximum):
    parts, size = [], 0
    try:
        async with asyncio.timeout(30):
            async for part in request.stream():
                size += len(part)
                if size > maximum:
                    raise TooLarge()
                parts.append(part)
    except TimeoutError as exc:
        raise HTTPException(408, 'Upload dauerte zu lange.') from exc
    return b''.join(parts)

def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = Store(settings.database)
    credential = hashlib.sha256(settings.password.encode()).hexdigest()
    image_gate = asyncio.Semaphore(1)
    lookup_gate = asyncio.Semaphore(1)
    vision_gate = asyncio.Semaphore(1)

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        yield

    app = FastAPI(title='Papierbibliothek mobil', version=VERSION,
                  docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic errors can contain raw input, including passwords.
        return JSONResponse({'detail': 'Eingaben fehlen oder sind ungültig.'}, status_code=422)

    @app.exception_handler(TooLarge)
    async def size_error(request, error):
        return JSONResponse({'detail': 'Bild überschreitet das Uploadlimit.'}, status_code=413)

    @app.exception_handler(InvalidImage)
    async def image_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=422)

    @app.exception_handler(sqlite3.Error)
    async def database_error(request, error):
        return JSONResponse({'detail': 'Speichern fehlgeschlagen. Speicherplatz und Datenvolume prüfen.'}, status_code=503)

    @app.middleware('http')
    async def security(request, call_next):
        path = request.url.path
        response = None
        if path.startswith('/api/') and path != '/api/health':
            if request.method not in ('GET', 'HEAD'):
                if (request.headers.get('origin') != settings.origin or
                        request.headers.get('x-papierbib') != '1'):
                    response = JSONResponse({'detail': 'Anfrage stammt nicht von der konfigurierten App-Adresse.'}, status_code=403)
            if response is None:
                if path == '/api/login':
                    # Global login limiter avoids spoofable proxy IP headers.
                    allowed = store.throttle('login', settings.login_limit, 300)
                else:
                    token = request.cookies.get(COOKIE, '')
                    if not store.authenticated(token, credential):
                        response = JSONResponse({'detail': 'Bitte anmelden.'}, status_code=401)
                    allowed = response is not None or store.throttle(
                        'session:' + store.digest(token), settings.request_limit, 60)
                if not allowed:
                    response = JSONResponse({'detail': 'Zu viele Anfragen. Bitte später erneut versuchen.'},
                                            status_code=429, headers={'Retry-After': '300' if path == '/api/login' else '60'})
            if response is None and request.method not in ('GET', 'HEAD'):
                maximum = settings.max_image_bytes if path.endswith('/captures') or path in ('/api/isbn/ocr', '/api/vision/analyze') else 16384
                # Auth precedes upload; bound even chunked requests before body parsing.
                try:
                    request._body = await bounded_body(request, maximum)
                except TooLarge:
                    response = JSONResponse({'detail': 'Upload überschreitet das Größenlimit.'}, status_code=413)
                except HTTPException as exc:
                    response = JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
        if response is None:
            response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store' if path.startswith('/api/') else 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(self), microphone=(), geolocation=()'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' blob: data:; media-src 'self' blob:; connect-src 'self'; "
            "worker-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        return response

    @app.get('/api/health')
    def health():
        with store.connect() as db:
            db.execute('SELECT 1')
        return dict(ok=True, version=VERSION, phase=3)

    @app.post('/api/login')
    def login(payload: Login, response: Response):
        submitted = hashlib.sha256(payload.password.encode()).hexdigest()
        if not hmac.compare_digest(submitted, credential):
            raise HTTPException(401, 'Anmeldung fehlgeschlagen.')
        token = store.new_session(credential, settings.session_seconds)
        response.set_cookie(COOKIE, token, max_age=settings.session_seconds,
                            httponly=True, secure=settings.secure_cookie, samesite='strict', path='/')
        return dict(ok=True)

    @app.get('/api/session')
    def session():
        return dict(ok=True, version=VERSION)

    @app.post('/api/logout')
    def logout(request: Request, response: Response):
        store.logout(request.cookies.get(COOKIE, ''))
        response.delete_cookie(COOKIE, path='/', secure=settings.secure_cookie, httponly=True, samesite='strict')
        return dict(ok=True)

    @app.get('/api/projects')
    def projects():
        return store.projects()

    @app.post('/api/projects', status_code=201)
    def create_project(payload: NewProject):
        return store.create_project(payload.name)

    @app.get('/api/projects/{project_id}/captures')
    def captures(project_id: str):
        if not store.has_project(project_id):
            raise HTTPException(404, 'Projekt nicht gefunden.')
        return store.captures(project_id)

    @app.post('/api/projects/{project_id}/captures', status_code=201)
    async def capture(project_id: str, request: Request,
                      kind: Literal['isbn', 'spine', 'titlepage', 'shelf'],
                      rotation: float = 0,
                      x: float = 0, y: float = 0, width: float = 1, height: float = 1,
                      store_images: bool = False):
        if not store_images:
            raise HTTPException(400, 'Bildspeicherung muss ausdrücklich bestätigt sein.')
        if not store.has_project(project_id):
            raise HTTPException(404, 'Projekt nicht gefunden.')
        from pydantic import ValidationError
        try:
            spec = CropSpec(rotation=rotation, x=x, y=y, width=width, height=height)
        except ValidationError as exc:
            raise HTTPException(422, 'Ungültiger Ausschnitt.') from exc
        data = await request.body()
        async with image_gate:
            info, crop = await run_in_threadpool(crop_image, data, spec, settings.max_pixels)
            return await run_in_threadpool(store.save_capture, project_id, kind, data, info, crop, spec.model_dump())

    @app.post('/api/captures/{photo_id}/crops', status_code=201)
    async def crop_version(photo_id: str, spec: CropSpec):
        async with image_gate:
            original = await run_in_threadpool(store.original, photo_id)
            if not original:
                raise HTTPException(404, 'Foto nicht gefunden.')
            _, crop = await run_in_threadpool(crop_image, original[0], spec, settings.max_pixels)
            return await run_in_threadpool(store.save_crop, photo_id, crop, spec.model_dump())

    @app.get('/api/captures/{photo_id}/original')
    def original(photo_id: str):
        image = store.original(photo_id)
        if not image:
            raise HTTPException(404, 'Foto nicht gefunden.')
        return Response(image[0], media_type=image[1])

    @app.get('/api/crops/{crop_id}/image')
    def crop_file(crop_id: str):
        image = store.crop(crop_id)
        if image is None:
            raise HTTPException(404, 'Zuschnitt nicht gefunden.')
        return Response(image, media_type='image/jpeg')

    @app.post('/api/isbn/lookup')
    async def lookup_isbn(payload: LookupRequest):
        cached = await run_in_threadpool(store.cached_metadata, payload.isbn)
        if cached is not None:
            return dict(isbn13=payload.isbn, matches=cached, cached=True, error=None)
        if not store.throttle('lobid', 30, 60):
            raise HTTPException(429, 'Zu viele Kataloganfragen. ISBN kann trotzdem als Entwurf gespeichert werden.')
        try:
            async with asyncio.timeout(20):
                async with lookup_gate:
                    cached = await run_in_threadpool(store.cached_metadata, payload.isbn)
                    if cached is None:
                        cached = await run_in_threadpool(lobid.lookup, payload.isbn)
                        await run_in_threadpool(store.cache_metadata, payload.isbn, cached)
            return dict(isbn13=payload.isbn, matches=cached, cached=False, error=None)
        except (lobid.ProviderError, TimeoutError):
            return dict(isbn13=payload.isbn, matches=[], cached=False,
                        error='lobid ist derzeit nicht verfügbar oder liefert keine nutzbare Antwort. ISBN als Entwurf speichern oder später erneut suchen.')

    @app.post('/api/isbn/ocr')
    async def isbn_ocr(request: Request, crop_confirmed: bool = False):
        if not crop_confirmed:
            raise HTTPException(400, 'Zuerst den ISBN-Ausschnitt im Editor bestätigen.')
        if not store.throttle('ocr', 10, 60):
            raise HTTPException(429, 'Zu viele OCR-Anfragen. Bitte kurz warten oder ISBN manuell eingeben.')
        data = await request.body()
        try:
            async with asyncio.timeout(20):
                async with image_gate:
                    numbers = await run_in_threadpool(ocr.recognize_isbns, data, settings.max_pixels)
            return dict(isbns=numbers, method='isbn-only-ocr', stored=False)
        except (ocr.OCRUnavailable, TimeoutError):
            raise HTTPException(503, 'ISBN-OCR ist nicht verfügbar oder hat das Zeitlimit erreicht. ISBN manuell eingeben.')

    @app.get('/api/vision/status')
    def vision_status():
        providers = vision.configured(settings)
        return dict(configured=providers, default_provider=settings.ai_provider if settings.ai_provider in providers else None,
                    models={name: settings.openai_vision_model if name == 'openai' else settings.gemini_vision_model for name in providers})

    @app.post('/api/vision/analyze')
    async def analyze_vision(request: Request, kind: Literal['spine', 'titlepage'], provider: Literal['openai', 'gemini'] | None = None,
                             consent: bool = False):
        if not consent:
            raise HTTPException(400, 'Bitte die kostenpflichtige KI-Auswertung ausdrücklich bestätigen.')
        if not vision.configured(settings):
            raise HTTPException(503, 'Kein KI-Anbieter ist konfiguriert. API-Schlüssel nur in Portainer hinterlegen.')
        if not store.throttle('vision', 8, 300):
            raise HTTPException(429, 'Zu viele KI-Auswertungen. Bitte kurz warten.')
        data = await request.body()
        try:
            async with asyncio.timeout(40):
                async with vision_gate:
                    result = await run_in_threadpool(vision.analyze, settings, provider, data, kind)
            return dict(result=result, stored=False)
        except (vision.VisionError, TimeoutError):
            raise HTTPException(503, 'KI-Auswertung fehlgeschlagen oder hat das Zeitlimit erreicht. Ausschnitt prüfen oder später erneut versuchen.')

    @app.get('/api/projects/{project_id}/books')
    def books(project_id: str):
        if not store.has_project(project_id):
            raise HTTPException(404, 'Projekt nicht gefunden.')
        return store.books(project_id)

    @app.post('/api/projects/{project_id}/books')
    def save_book(project_id: str, payload: BookInput):
        if not store.has_project(project_id):
            raise HTTPException(404, 'Projekt nicht gefunden.')
        if payload.status == 'confirmed' and not payload.title:
            raise HTTPException(422, 'Zum Bestätigen einen Titel eingeben oder als Entwurf speichern.')
        try:
            return store.save_book(project_id, payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.api_route('/api/{unknown:path}', methods=['GET', 'POST', 'PUT', 'DELETE', 'PATCH'])
    def unknown_api(unknown: str):
        raise HTTPException(404, 'Diese Funktion ist noch nicht verfügbar.')

    web = Path(__file__).parent / 'web'

    @app.get('/')
    def index():
        return FileResponse(web / 'index.html')

    app.mount('/', StaticFiles(directory=web), name='pwa')
    return app
