"""No network or private photographs. Test the actual API and image/database boundary."""
import io
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image
from mobile_backend.config import Settings
from mobile_backend.server import create_app, COOKIE
from mobile_backend.images import CropSpec, crop_image, InvalidImage

PASSWORD = 'test-only-password-123456'
ORIGIN = 'https://books.test'

def photograph():
    image = Image.new('RGB', (160, 120), 'red')
    for x in range(80, 160):
        for y in range(120):
            image.putpixel((x, y), (0, 0, 255))
    data = io.BytesIO()
    image.save(data, format='PNG')
    return data.getvalue()

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.settings = Settings(password=PASSWORD, origin=ORIGIN,
                                 database=Path(self.tmp.name) / 'library.sqlite3')
        self.app = create_app(self.settings)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.client.__enter__()
        self.headers = {'Origin': ORIGIN, 'X-Papierbib': '1'}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def post(self, path, **kwargs):
        return self.client.post(path, headers=self.headers, **kwargs)

    def login(self):
        r = self.post('/api/login', json={'password': PASSWORD})
        self.assertEqual(r.status_code, 200)
        return r

    def project(self):
        self.login()
        return self.post('/api/projects', json={'name': 'Bücher – Straße'}).json()['project_id']

    def upload(self, project, **spec):
        params = dict(kind='spine', store_images='true', **spec)
        return self.post(f'/api/projects/{project}/captures', params=params, content=photograph())

    def test_health_and_static_no_secrets(self):
        self.assertEqual(self.client.get('/api/health').json()['ok'], True)
        self.assertEqual(self.client.get('/').status_code, 200)
        self.assertNotIn(PASSWORD, self.client.get('/').text)
        self.assertEqual(self.client.get('/api/projects').status_code, 401)
        self.assertEqual(self.client.get('/.env').status_code, 404)
        self.assertEqual(self.client.get('/app.py').status_code, 404)

    def test_login_cookie_origin_logout(self):
        denied = self.client.post('/api/login', json={'password': PASSWORD})
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(self.post('/api/login', json={'password': 'bad'}).status_code, 401)
        cookie = self.login().headers['set-cookie']
        for flag in ('HttpOnly', 'Secure', 'SameSite=strict'):
            self.assertIn(flag, cookie)
        token = self.client.cookies.get(COOKIE)
        self.assertEqual(self.client.get('/api/session').status_code, 200)
        self.assertEqual(self.post('/api/logout', json={}).status_code, 200)
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.get('/api/session').status_code, 401)

    def test_validation_never_echoes_password(self):
        response = self.post('/api/login', json={'password': [PASSWORD]})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(PASSWORD, response.text)

    def test_rate_limit_login(self):
        for _ in range(10):
            self.post('/api/login', json={'password': 'bad'})
        self.assertEqual(self.post('/api/login', json={'password': PASSWORD}).status_code, 429)

    def test_projects_images_and_versions_survive_restart(self):
        project = self.project()
        saved = self.upload(project, rotation=90, x=0, y=0, width=1, height=0.5)
        self.assertEqual(saved.status_code, 201, saved.text)
        photo, first_crop = saved.json()['photo_id'], saved.json()['crop_id']
        original = self.client.get(f'/api/captures/{photo}/original')
        self.assertEqual(original.content, photograph())
        self.assertEqual(original.headers['cache-control'], 'no-store')
        crop = self.client.get(f'/api/crops/{first_crop}/image')
        self.assertEqual(Image.open(io.BytesIO(crop.content)).size, (120, 80))
        second = self.post(f'/api/captures/{photo}/crops', json=dict(rotation=0,x=0.5,y=0,width=0.5,height=1))
        self.assertEqual(second.status_code, 201, second.text)
        self.assertNotEqual(first_crop, second.json()['crop_id'])
        # Original and old revision are byte-for-byte unchanged.
        self.assertEqual(self.client.get(f'/api/captures/{photo}/original').content, photograph())
        self.assertEqual(self.client.get(f'/api/crops/{first_crop}/image').content, crop.content)
        with TestClient(create_app(self.settings), base_url=ORIGIN) as restarted:
            restarted.post('/api/login', headers=self.headers, json={'password': PASSWORD})
            rows = restarted.get(f'/api/projects/{project}/captures').json()
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0]['crops']), 2)

    def test_no_consent_no_persistence(self):
        project = self.project()
        response = self.post(f'/api/projects/{project}/captures?kind=isbn', content=photograph())
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.get(f'/api/projects/{project}/captures').json(), [])

    def test_corrupt_image_and_invalid_crop_do_not_create_rows(self):
        project = self.project()
        response = self.post(f'/api/projects/{project}/captures?kind=isbn&store_images=true', content=b'not an image')
        self.assertEqual(response.status_code, 422)
        for spec in (dict(x=.8,width=.5), dict(rotation=17), dict(width=-1), dict(x='NaN')):
            self.assertEqual(self.upload(project, **spec).status_code, 422)
        self.assertEqual(self.client.get(f'/api/projects/{project}/captures').json(), [])

    def test_oversized_chunked_request(self):
        settings = replace(self.settings, max_image_bytes=256)
        with TestClient(create_app(settings), base_url=ORIGIN) as client:
            client.post('/api/login', headers=self.headers, json={'password': PASSWORD})
            project = client.post('/api/projects', headers=self.headers, json={'name':'Test'}).json()['project_id']
            response = client.post(f'/api/projects/{project}/captures?kind=isbn&store_images=true',
                                   headers=self.headers, content=iter([b'x'*200,b'x'*200]))
            self.assertEqual(response.status_code, 413)

    def test_unknown_resources_and_old_api(self):
        self.login()
        for path in ('/api/captures/missing/original','/api/crops/missing/image','/api/projects/missing/captures'):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.post('/api/vision/book-spine', content=b'').status_code, 404)

    def test_transaction_rolls_back_on_failure(self):
        project = self.project()
        with patch.object(self.app.state.store, '_insert_crop', side_effect=__import__('sqlite3').OperationalError('disk full')):
            self.assertEqual(self.upload(project).status_code, 503)
        self.assertEqual(self.client.get(f'/api/projects/{project}/captures').json(), [])

    def test_session_expiry_and_password_rotation(self):
        self.login()
        with self.app.state.store.connect() as db:
            db.execute('UPDATE sessions SET expires=?', (time.time()-1,))
        self.assertEqual(self.client.get('/api/session').status_code, 401)
        self.login()
        with TestClient(create_app(replace(self.settings,password=PASSWORD+'new')), base_url=ORIGIN) as other:
            other.cookies.update(self.client.cookies)
            self.assertEqual(other.get('/api/session').status_code, 401)

class ImageTests(unittest.TestCase):
    def test_rotation_crop_geometry_and_color(self):
        _, crop = crop_image(photograph(), CropSpec(rotation=90, height=.5), 100000)
        image = Image.open(io.BytesIO(crop['data']))
        self.assertEqual(image.size, (120,80))
        self.assertGreater(image.getpixel((60,40))[0], 240)

    def test_exif_orientation_and_no_metadata_in_crop(self):
        image = Image.new('RGB',(160,120),'white')
        exif = Image.Exif(); exif[274] = 6
        data = io.BytesIO(); image.save(data,format='JPEG',exif=exif)
        info, crop = crop_image(data.getvalue(), CropSpec(), 100000)
        self.assertEqual((info['width'],info['height']), (120,160))
        self.assertEqual(dict(Image.open(io.BytesIO(crop['data'])).getexif()), {})

    def test_limits_animation_and_minimum_crop(self):
        with self.assertRaises(InvalidImage):
            crop_image(photograph(), CropSpec(), 100)
        with self.assertRaises(InvalidImage):
            crop_image(photograph(), CropSpec(width=.001), 100000)
        data=io.BytesIO();Image.new('RGB',(20,20)).save(data,format='GIF')
        with self.assertRaises(InvalidImage):
            crop_image(data.getvalue(),CropSpec(),100000)

class ConfigTests(unittest.TestCase):
    def test_configuration_fails_closed(self):
        for changes in (dict(password='short'),dict(origin='http://lan'),dict(origin='https://host/path'),
                        dict(origin='https://host',secure_cookie=False)):
            with self.assertRaises(ValueError):
                replace(Settings(password=PASSWORD,origin=ORIGIN), **changes)
        self.assertNotIn(PASSWORD,repr(Settings(password=PASSWORD,origin=ORIGIN)))

if __name__ == '__main__':
    unittest.main()
