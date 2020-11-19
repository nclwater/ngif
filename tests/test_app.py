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
            with open('tests/lysimeter.txt', 'rb') as f:
                self.assertEqual(client.post('/upload', data={
                    'upload_file': (f, 'GP2-10-58 (Lysimeter 1) 2020-11-19 10.27.04.txt')},
                                             content_type='multipart/form-data').status_code, 200)

            with open('tests/ensemble.txt', 'rb') as f:
                self.assertEqual(client.post('/upload', data={
                    'upload_file': (f, 'GP2-10-60 (Ensemble E + RG) 2020-11-18 13.52.10.txt')},
                                             content_type='multipart/form-data').status_code, 200)
