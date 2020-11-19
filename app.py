# -*- coding: utf-8 -*-

# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.

import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.express as px
import pandas as pd
import flask
from flask import request, make_response
import os
from flask_pymongo import PyMongo, DESCENDING

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

server = flask.Flask(__name__)
server.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://test:password@localhost:27017/test?authSource=admin')
mongo = PyMongo(server)

readings = mongo.db.readings
units = mongo.db.units

app = dash.Dash(
    __name__,
    server=server,
    routes_pathname_prefix='/dash/',
    external_stylesheets=external_stylesheets
)


@server.route('/')
def index():
    return flask.redirect('/dash')


@server.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        # check if the post request has the file part
        if 'upload_file' not in request.files:
            return make_response({'error': 'upload_file not present'}, 400)

        f = request.files['upload_file']
        name = f.filename
        name = name[name.index('(') + 1:name.index('+') - 1 if '+' in name else name.index(')')]

        # Update units
        units.update_one({'name': name}, {'$set': {field: unit for field, unit in zip(
                f.stream.readline().strip().decode().split('\t'), f.stream.readline().strip().decode().split('\t'))}
        }, upsert=True)
        f.stream.seek(0)

        data = pd.read_csv(f, sep='\t', parse_dates=[0], dayfirst=True, skiprows=range(1, 2), na_values=['#+INF'])
        data = data.rename(columns={data.columns[0]: 'time'})
        # Get the latest inserted time
        last_entry = readings.find_one(
            {'name': name}, {'time': 1},
            sort=[('_id', DESCENDING)]
        )
        if last_entry is not None:
            last_time = pd.to_datetime(last_entry['time'])
            data = data[data.time > last_time]

        if len(data) > 0:
            readings.insert_many({'name': name, **{k: v for k, v in row.items() if pd.notna(v)}}
                                 for row in data.to_dict('records'))

        return make_response({}, 200)


def create_layout():
    sensors = {sensor['name']: {k: v for k, v in sensor.items() if k != 'name'}
               for sensor in list(units.find({}, {'_id': False}))}
    names = list(sensors.keys())

    df = pd.DataFrame(list(readings.find({'name': 'Lysimeter 1', 'Theta 800mm': {"$exists": True}},
                                         sort=[('_id', DESCENDING)]).limit(100)))
    if len(df) > 0:
        fig = px.line(df, x="time", y="Theta 800mm", title='Lysimeter 1')
        fig.update_layout({'xaxis': {'title': None}})
    else:
        fig = None

    return html.Div(children=[
        html.H1(children='NGIF'),

        html.Div(children='''
            National Green Infrastructure Facility.
        '''),

        dcc.Dropdown(
            id='name',
            options=[{'label': n, 'value': n} for n in names],
            value=names[0] if len(names) > 0 else None
        ),
        dcc.Dropdown(
            id='field',
            options=[{'label': n, 'value': n} for n in sensors[names[0]].keys()] if len(names) > 0 else [],
            value=list(sensors[names[0]].keys())[0] if len(names) > 0 else None
        ),

        dcc.Graph(
            id='example-graph',
            figure=fig,

        )])


app.layout = create_layout

# app.layout=html.Div()
if __name__ == '__main__':
    # app.run_server(debug=True)
    server.run(debug=True)
