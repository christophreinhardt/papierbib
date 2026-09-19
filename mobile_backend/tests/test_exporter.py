import csv
import io
import json
import sys
import types
import unittest
from uuid import uuid4

# The domain model itself has no Calibre dependency; only its package wrapper
# imports this base class. A minimal stub lets this compatibility test run in
# the lightweight mobile test environment.
if 'calibre.customize' not in sys.modules:
    calibre = types.ModuleType('calibre')
    customize = types.ModuleType('calibre.customize')
    customize.InterfaceActionBase = type('InterfaceActionBase', (), {})
    calibre.customize = customize
    sys.modules.setdefault('calibre', calibre)
    sys.modules.setdefault('calibre.customize', customize)

from papierbibliothek.models import Project
from mobile_backend import exporter
from mobile_backend.tests import test_backend as base


class ExportTests(unittest.TestCase):
    setUp = base.ApiTests.setUp
    tearDown = base.ApiTests.tearDown
    post = base.ApiTests.post
    login = base.ApiTests.login
    project = base.ApiTests.project

    def test_calibre_schema_five_export_reopens_in_plugin_model(self):
        project_id = self.project()
        data = dict(book_id=str(uuid4()), status='confirmed', title='Straße & Æther',
                    authors=['Müller, Anna', 'René'], publisher='Verlag',
                    publication_year=2024, language='de', isbn13='9780306406157')
        self.assertEqual(self.post(f'/api/projects/{project_id}/books', json=data).status_code, 200)
        response = self.client.get(f'/api/projects/{project_id}/export/calibre')
        self.assertEqual(response.status_code, 200)
        self.assertIn('projekt.json', response.headers['content-disposition'])
        raw = response.json()
        reopened = Project.from_dict(raw)
        self.assertEqual(reopened.books[0].author, 'Müller, Anna; René')
        self.assertEqual(reopened.books[0].status, 'manual_confirmed')
        self.assertEqual(reopened.books[0].isbn13, '9780306406157')
        self.assertEqual(reopened.photos, [])

    def test_csv_is_utf8_and_formula_safe(self):
        project = dict(name='Mobil', project_id='p', created_at='2026-01-01T00:00:00Z', updated_at='2026-01-01T00:00:00Z')
        records = [dict(book_id='b', title='=1+1', authors=['Müller'], status='draft',
                        created_at='2026-01-01T00:00:00Z', updated_at='2026-01-01T00:00:00Z')]
        rows = list(csv.DictReader(io.StringIO(exporter.csv_export(records).decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(rows[0]['title'], "'=1+1")
        self.assertEqual(json.loads(exporter.json_export(project, records))['schema_version'], 5)


if __name__ == '__main__':
    unittest.main()
