import app
from unittest import TestCase
from pymongo import MongoClient
from datetime import datetime

db = MongoClient(app.server.config['MONGO_URI']).get_database()
readings = db.readings
sensors = db.sensors
sensors.drop()
readings.drop()

readings.insert({'name': 'sensor', 'field': 1, 'time': datetime.now()})
sensors.insert({'name': 'sensor', 'field': 'mm'})

class TestApp(TestCase):
    def test_app(self):
        self.assertIsNotNone(app.app)

    def test_create_layout(self):
        app.create_layout()

    def test_create_plot(self):

        app.create_plot(name='sensor', field='field')
