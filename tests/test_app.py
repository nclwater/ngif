from app import app
from unittest import TestCase


class TestApp(TestCase):
    def test_app(self):
        self.assertIsNotNone(app)
