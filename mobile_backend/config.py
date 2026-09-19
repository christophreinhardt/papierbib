"""Fail-closed deployment configuration. No secret-bearing repr or API output."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

VERSION = '0.4.0'

@dataclass(frozen=True)
class Settings:
    password: str = field(repr=False)
    origin: str = 'https://localhost'
    database: Path = Path('/data/papierbib.sqlite3')
    secure_cookie: bool = True
    max_image_bytes: int = 20 * 1024 * 1024
    max_pixels: int = 50_000_000
    session_seconds: int = 12 * 3600
    request_limit: int = 240
    login_limit: int = 10
    ai_provider: str = 'openai'
    openai_api_key: str = field(default='', repr=False)
    openai_vision_model: str = 'gpt-4o-mini'
    gemini_api_key: str = field(default='', repr=False)
    gemini_vision_model: str = 'gemini-2.0-flash'

    def __post_init__(self):
        parsed = urlsplit(self.origin)
        if len(self.password) < 16:
            raise ValueError('PAPIERBIB_PASSWORD muss mindestens 16 Zeichen lang sein.')
        if (parsed.scheme not in ('https', 'http') or not parsed.hostname or
                parsed.path or parsed.query or parsed.fragment or parsed.username):
            raise ValueError('PUBLIC_ORIGIN muss eine Basisadresse ohne Pfad sein.')
        if not self.secure_cookie and parsed.hostname not in ('localhost', '127.0.0.1'):
            raise ValueError('Unsichere Cookies sind nur bei localhost-Entwicklung erlaubt.')
        if self.secure_cookie and parsed.scheme != 'https':
            raise ValueError('PUBLIC_ORIGIN benötigt HTTPS.')
        if not 1 <= self.max_image_bytes <= 30 * 1024 * 1024:
            raise ValueError('MAX_IMAGE_BYTES muss zwischen 1 und 31457280 liegen.')
        if self.ai_provider not in ('openai', 'gemini'):
            raise ValueError('AI_PROVIDER muss openai oder gemini sein.')

    @classmethod
    def from_env(cls):
        return cls(
            password=os.getenv('PAPIERBIB_PASSWORD', ''),
            origin=os.getenv('PUBLIC_ORIGIN', '').rstrip('/'),
            database=Path(os.getenv('DATABASE_PATH', '/data/papierbib.sqlite3')),
            secure_cookie=os.getenv('COOKIE_SECURE', 'true').lower() != 'false',
            max_image_bytes=int(os.getenv('MAX_IMAGE_BYTES', '20971520')),
            ai_provider=os.getenv('AI_PROVIDER', 'openai').lower(),
            openai_api_key=os.getenv('OPENAI_API_KEY', ''),
            openai_vision_model=os.getenv('OPENAI_VISION_MODEL', 'gpt-4o-mini'),
            gemini_api_key=os.getenv('GEMINI_API_KEY', ''),
            gemini_vision_model=os.getenv('GEMINI_VISION_MODEL', 'gemini-2.0-flash'),
        )
