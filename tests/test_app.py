from app import app, server
from unittest import TestCase
from pymongo import MongoClient

db = MongoClient('mongodb://test:password@localhost:27017/').test
readings = db.readings
readings.drop()


class TestApp(TestCase):
    def test_app(self):
        self.assertIsNotNone(app)

    def test_upload(self):
        with server.test_client() as client:
            with open('tests/data.csv', 'rb') as f:
                self.assertEqual(client.post('/upload', data={'upload_file': (f, 'test.csv')},
                                             content_type='multipart/form-data').status_code, 200)
