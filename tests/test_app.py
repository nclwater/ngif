from app import app, server
from unittest import TestCase


class TestApp(TestCase):
    def test_app(self):
        self.assertIsNotNone(app)

    def test_upload(self):
        with server.test_client() as client:
            self.assertEqual(client.post('/upload', data={'upload_file': (None, 'test.csv')},
                                         content_type='multipart/form-data').status_code, 200)
