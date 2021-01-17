# -*- coding: utf-8 -*-

# Run this app with `python app.py` and
# visit http://127.0.0.1:8050/ in your web browser.

import dash
import dash_core_components as dcc
import dash_html_components as html
import dash_table
import plotly.express as px
import pandas as pd
import flask
import os
from flask_pymongo import PyMongo, DESCENDING, ASCENDING
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import urllib.parse
from datetime import timedelta, datetime
import re


def convert(text):
    return int(text) if str(text).isdigit() else text.lower()


external_stylesheets = ['https://codepen.io/chriddyp/pen/bWLwgP.css']

server = flask.Flask(__name__)
server.config["MONGO_URI"] = os.getenv('MONGO_URI', 'mongodb://test:password@localhost:27017/test?authSource=admin')
mongo = PyMongo(server)

readings = mongo.db.readings

lookup = pd.read_csv('ngif-sensor-fields.csv')
to_drop = lookup[lookup['To keep?'] == 'N']['Current field'].values.tolist()


class Sensors:
    def __init__(self):
        self.metadata = None
        self.names = None
        self.update()

    def update(self):
        self.get_metadata()
        self.get_names()

    def get_names(self):
        self.names = self.metadata.name.unique().tolist()

    def get_metadata(self):
        rows = []
        for sensor in mongo.db.sensors.find({}, {'_id': False}, sort=[('name', ASCENDING)]):

            for field, metadata in sensor.items():
                if field not in ['name'] + to_drop:
                    rows.append({'name': sensor['name'], 'field': field, **metadata})

        self.metadata = pd.merge(pd.DataFrame(rows), lookup.drop('units', axis=1),
                                 left_on=['name', 'field'], right_on=['Current name', 'Current field'])

        for col in ['name', 'field', 'units']:
            new_col = f'New {col}'
            self.metadata[new_col].loc[self.metadata[new_col].isnull()] = \
                self.metadata[col][self.metadata[new_col].isnull()]

    def get_field_metadata(self, name, field):
        return self.metadata.loc[(self.metadata.name == name) & (self.metadata.field == field)].iloc[0]


sensors = Sensors()


def get_field_with_units(name, field):
    metadata = sensors.get_field_metadata(name, field)
    return f'{metadata["New field"]} ({metadata["New units"]})'


app = dash.Dash(
    __name__,
    server=server,
    external_stylesheets=external_stylesheets,
    title='NGIF'
)


def create_layout():
    sensors.update()
    start_date = datetime.utcnow().date() - timedelta(days=2)
    end_date = datetime.utcnow().date()
    name = sensors.names[0] if len(sensors.names) > 0 else None
    field = sensors.metadata[sensors.metadata.name == name].field[0] if len(sensors.metadata) > 0 else None

    options = sorted([{'label': sensors.metadata[sensors.metadata.name == n]['New name'].iloc[0], 'value': n}
                      for n in sensors.names],
                     key=lambda key: [convert(int(c) if c.isdigit() else c.lower())
                                      for c in re.split('([0-9]+)', key['label'])])

    return html.Div(children=[

        html.H1(children='National Green Infrastructure Facility (NGIF)'),

        html.Div([
            dcc.Dropdown(
                id='name',
                options=options,
                value=options[0]['value'] if len(options) > 0 else None,
            )
        ], style={'display': 'inline-block', 'width': '49%'}),
        html.Div([
            dcc.Dropdown(
                id='field',
            )
        ], style={'display': 'inline-block', 'width': '49%'}),

        dcc.DatePickerRange(
            id='date-picker',
            min_date_allowed=datetime(2000, 1, 1),
            max_date_allowed=end_date + timedelta(days=1),  # https://github.com/plotly/dash-core-components/issues/867
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
                              figure=create_plot(name, field, start_date.isoformat(), end_date.isoformat()) if
                              name is not None else None)),
        dash_table.DataTable(
            id='table',
            columns=[
                {"name": name.title(), "id": name, "deletable": False, "selectable": False} for i, name in
                enumerate(['sensor', 'field', 'units', 'time of last reading', 'value of last reading'])
            ],
            data=get_table_data(),
            editable=False,
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            row_deletable=False,
            cell_selectable=False,
            page_action="native",
            page_current=0,
            page_size=10,
        ),
        html.A('Download metadata table', href='/download-metadata')
    ])


@app.callback(Output(component_id='table', component_property='data'),
              [Input('update', 'n_clicks')])
def update_table(_):
    return get_table_data()


def get_table_data():

    rows = sensors.metadata[['New name', 'New field', 'New units', 'last_updated', 'last_value']]
    rows.columns = ['sensor', 'field', 'units', 'time of last reading', 'value of last reading']

    return rows.to_dict('records')


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
        fig.update_layout({'xaxis': {'title': None}, 'yaxis': {'title': get_field_with_units(name, field)}})
        fig.update_traces(mode='lines+markers')
    else:
        fig = {}
    return fig


@app.callback(Output(component_id='field', component_property='options'),
              [Input(component_id='name', component_property='value')])
def update_fields(name):
    if name is None:
        raise PreventUpdate
    # return [{'label': n, 'value': n} for n in sensors.metadata[name].keys()]

    return [{'label': row['New field'], 'value': row.field}
            for i, row in sensors.metadata[sensors.metadata.name == name].iterrows()]


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
        columns={field: get_field_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)
    metadata = sensors.get_field_metadata(name, field)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{metadata["New name"]}]-[{metadata["New field"]}].csv',
                           as_attachment=True)


@app.server.route('/download-metadata')
def download_metadata():
    import io
    csv = io.StringIO()
    pd.DataFrame(get_table_data()).drop('id', axis=1).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-metadata.csv',
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
        columns={field: get_field_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    metadata = sensors.get_field_metadata(name, field)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{metadata["New name"]}]-[{metadata["New field"]}].csv',
                           as_attachment=True)


app.layout = create_layout

if __name__ == '__main__':
    app.run_server(debug=True)
