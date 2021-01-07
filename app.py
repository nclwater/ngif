# -*- coding: utf-8 -*-

# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.

import dash
import dash_core_components as dcc
import dash_html_components as html
import plotly.express as px
import pandas as pd
import flask
import os
from flask_pymongo import PyMongo, DESCENDING, ASCENDING
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import urllib.parse
from datetime import date, timedelta, datetime

external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

server = flask.Flask(__name__)
server.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://test:password@localhost:27017/test?authSource=admin')
mongo = PyMongo(server)

readings = mongo.db.readings


class Sensors:
    def __init__(self):
        self.units = None
        self.names = None
        self.update()

    def update(self):
        self.units = {sensor['name']: {k: v for k, v in sensor.items() if k != 'name'}
                      for sensor in list(mongo.db.sensors.find({}, {'_id': False}, sort=[('name', ASCENDING)]))}

        self.names = list(self.units.keys())


sensors = Sensors()


def get_name_with_units(name, field):
    return f'{field} ({sensors.units[name][field]})'


app = dash.Dash(
    __name__,
    server=server,
    external_stylesheets=external_stylesheets,
    title='NGIF'
)


def create_layout():
    sensors.update()
    start_date = date.today() - timedelta(days=2)
    end_date = date.today()
    name = sensors.names[0] if len(sensors.names) > 0 else None
    field = list(sensors.units[name].keys())[0] if len(sensors.names) > 0 else None
    return html.Div(children=[

        html.H1(children='National Green Infrastructure Facility (NGIF)'),

        html.Div([
            dcc.Dropdown(
                id='name',
                options=[{'label': n, 'value': n} for n in sensors.names],
                value=sensors.names[0] if len(sensors.names) > 0 else None,
            )
        ], style={'display': 'inline-block', 'width': '49%'}),
        html.Div([
            dcc.Dropdown(
                id='field',
            )
        ], style={'display': 'inline-block', 'width': '49%'}),

        dcc.DatePickerRange(
            id='date-picker',
            min_date_allowed=date(1995, 8, 5),
            max_date_allowed=date.today(),
            start_date=start_date,
            end_date=end_date,
            display_format='DD/MM/YYYY',
            minimum_nights=0
        ),
        html.P(),
        html.A(html.Button('Update Plot'), id='update'),
        html.A(html.Button('Download Selected Period'), id='download-link'),
        html.A(html.Button('Download Entire Series'), id='download-all-link'),

        dcc.Loading(dcc.Graph(id='plot',
                              figure=create_plot(name, field, start_date.isoformat(), end_date.isoformat()))),
    ])


@app.callback(Output(component_id='plot', component_property='figure'),
              [Input('update', 'n_clicks')],
              [State(component_id='name', component_property='value'),
               State(component_id='field', component_property='value'),
               State(component_id='date-picker', component_property='start_date'),
               State(component_id='date-picker', component_property='end_date')
               ])
def update_plot(_, name, field, start_date, end_date):
    return create_plot(name, field, start_date, end_date)


def create_plot(name, field, start_date, end_date):
    if name is None or field is None:
        raise PreventUpdate
    df = pd.DataFrame(list(readings.find({'name': name, field: {"$exists": True},
                                          "time": {"$lt": datetime.fromisoformat(end_date) + timedelta(days=1),
                                                   "$gte": datetime.fromisoformat(start_date)}},

                                         {field: 1, 'time': 1},
                                         sort=[('_id', DESCENDING)])))
    if len(df) > 0:
        fig = px.line(df, x="time", y=field)
        fig.update_layout({'xaxis': {'title': None}, 'yaxis': {'title': get_name_with_units(name, field)}})
        fig.update_traces(mode='lines+markers')
    else:
        fig = {}
    return fig


@app.callback(Output(component_id='field', component_property='options'),
              [Input(component_id='name', component_property='value')])
def update_fields(name):
    if name is None:
        raise PreventUpdate
    return [{'label': n, 'value': n} for n in sensors.units[name].keys()]


@app.callback(
    dash.dependencies.Output('field', 'value'),
    [dash.dependencies.Input('field', 'options')])
def update_selected_field(available_options):
    return available_options[0]['value']


@app.callback(Output('download-all-link', 'href'),
              [
                  Input(component_id='name', component_property='value'),
                  Input(component_id='field', component_property='value')
               ])
def update_href(name, field):
    return urllib.parse.quote(f'/download-all/{name}/{field}')


@app.callback(Output('download-link', 'href'),
              [
                  Input(component_id='name', component_property='value'),
                  Input(component_id='field', component_property='value'),
                  Input(component_id='date-picker', component_property='start_date'),
                  Input(component_id='date-picker', component_property='end_date')
               ])
def update_href(name, field, start_date, end_date):
    return urllib.parse.quote(f'/download/{name}/{field}/{start_date}/{end_date}')


@app.server.route('/download-all/<name>/<field>')
def download_all(name, field):
    import io
    csv = io.StringIO()
    pd.DataFrame(list(readings.find({'name': name, field: {"$exists": True}}, {'_id': False, field: 1, 'time': 1, },
                                    sort=[('_id', ASCENDING)]))).rename(
        columns={field: get_name_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{name}]-[{field}].csv',
                           as_attachment=True)


@app.server.route('/download/<name>/<field>/<start_date>/<end_date>')
def download(name, field, start_date, end_date):
    import io
    csv = io.StringIO()
    pd.DataFrame(list(readings.find({'name': name, field: {"$exists": True},
                                     "time": {"$lt": datetime.fromisoformat(end_date) + timedelta(days=1),
                                              "$gte": datetime.fromisoformat(start_date)}},
                                    {'_id': False, field: 1, 'time': 1, },
                                    sort=[('_id', ASCENDING)]))).rename(
        columns={field: get_name_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{name}]-[{field}].csv',
                           as_attachment=True)


app.layout = create_layout

if __name__ == '__main__':
    server.run(debug=True)
