import app
from unittest import TestCase
from pymongo import MongoClient
from datetime import datetime, date

db = MongoClient(app.server.config['MONGO_URI']).get_database()
readings = db.readings
sensors = db.sensors
sensors.drop()
readings.drop()

name = 'GP2-10-68 (Ensemble F + Pavement)'
field = 'Drain_F1#@15m'
readings.insert({'name': name, field: 1, 'time': datetime.now()})
sensors.insert({'name': name,
                field: {'units': 'mm', 'last_updated': datetime.now(), 'last_value': 1}})


class TestApp(TestCase):
    def test_app(self):
        self.assertIsNotNone(app.app)

    def test_create_layout(self):
        app.create_layout()

    def test_create_plot(self):

        app.create_plot(name='Ensemble F', field=field, start_date=date.today().isoformat(),
                        end_date=date.today().isoformat())
