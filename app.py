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
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate
import urllib.parse

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
    external_stylesheets=external_stylesheets
)


def create_layout():
    sensors.update()
    return html.Div(children=[
        html.H1(children='National Green Infrastructure Facility (NGIF)'),

        html.Div([
            dcc.Dropdown(
                id='name',
                options=[{'label': n, 'value': n} for n in sensors.names],
                value=sensors.names[0] if len(sensors.names) > 0 else None,
                className='two columns'
            ),
            dcc.Dropdown(
                id='field',
                className='two columns'
            )], className='row'),

        dcc.Loading(dcc.Graph(id='plot')),

        html.A(id='download-link', children='Download Data')])


@app.callback(Output(component_id='plot', component_property='figure'),
              [Input(component_id='name', component_property='value'),
               Input(component_id='field', component_property='value')
               ])
def update_plot(name, field):
    return create_plot(name, field)


def create_plot(name, field):
    if name is None or field is None:
        raise PreventUpdate
    df = pd.DataFrame(list(readings.find({'name': name, field: {"$exists": True}}, {field: 1, 'time': 1},
                                         sort=[('_id', DESCENDING)]).limit(500)))
    if len(df) > 0:
        fig = px.line(df, x="time", y=field)
        fig.update_layout({'xaxis': {'title': None}, 'yaxis': {'title': get_name_with_units(name, field)}})
    else:
        fig = None
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


@app.callback(Output('download-link', 'href'),
              [
                  Input(component_id='name', component_property='value'),
                  Input(component_id='field', component_property='value')
               ])
def update_href(name, field):
    return urllib.parse.quote(f'/download/{name}/{field}')


@app.server.route('/download/<name>/<field>')
def serve_static(name, field):
    import io
    csv = io.StringIO()
    pd.DataFrame(list(readings.find({'name': name, field: {"$exists": True}}, {'_id': False, field: 1, 'time': 1, },
                                    sort=[('_id', DESCENDING)]))).rename(
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
    server.run(debug=True, host='0.0.0.0')
