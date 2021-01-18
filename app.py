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


class Metadata:
    def __init__(self):
        self.df = None
        self.names = None
        self.update()

    def update(self):
        rows = []
        for sensor in mongo.db.sensors.find({}, {'_id': False}, sort=[('name', ASCENDING)]):
            for field, field_metadata in sensor.items():
                if field != 'name':
                    rows.append({'name': sensor['name'], 'field': field, **field_metadata})

        if len(rows) == 0:
            self.df = pd.DataFrame()
            self.names = []
            return

        self.df = pd.merge(pd.DataFrame(rows), lookup.drop('units', axis=1),
                           left_on=['name', 'field'], right_on=['Current name', 'Current field'], how='left')

        self.df = self.df[self.df['To keep?'] != 'N']

        self.df['db_name'] = self.df['name']
        self.df['name'] = self.df['name'].replace(self.df.set_index('name')['New name'].dropna().to_dict())

        self.df['db_field'] = self.df['field']
        self.df.loc[self.df['New field'].notnull(), 'field'] = self.df.loc[self.df['New field'].notnull(), 'New field']

        self.df.loc[self.df['New units'].notnull(), 'units'] = self.df.loc[self.df['New units'].notnull(), 'New units']

        self.names = self.df.name.unique().tolist()

    def get_field_metadata(self, name, field):
        return self.df.loc[(self.df.name == name) & (self.df.field == field)].iloc[0]

    def get_field_with_units(self, name, field):
        field_metadata = self.get_field_metadata(name, field)
        return f'{field_metadata.field} ({field_metadata.units})'

    def as_table(self):
        if len(self.df) > 0:
            return self.df[['name', 'field', 'units', 'last_updated', 'last_value']].to_dict('records')
        else:
            return {}


metadata = Metadata()

app = dash.Dash(
    __name__,
    server=server,
    external_stylesheets=external_stylesheets,
    title='NGIF'
)


def create_layout():
    metadata.update()
    start_date = datetime.utcnow().date() - timedelta(days=2)
    end_date = datetime.utcnow().date()

    options = sorted([{'label': n, 'value': n}
                      for n in metadata.names],
                     key=lambda key: [convert(int(c) if c.isdigit() else c.lower())
                                      for c in re.split('([0-9]+)', key['label'])])

    name = options[0]['value'] if len(options) > 0 else None
    field = metadata.df[metadata.df.name == name].field.iloc[0] if len(options) > 0 else None

    locations = metadata.df.drop_duplicates('name').set_index('name')['Long. Lat'].str.split(',', expand=True) \
        if len(metadata.df) > 0 else None
    map_figure = px.scatter_mapbox(
        locations.index,
        lat=locations.iloc[:, 0].astype(float).tolist(),
        lon=locations.iloc[:, 1].astype(float).tolist(),
        hover_name="name",
        zoom=16,
        mapbox_style='open-street-map') if locations is not None else {}

    return html.Div(children=[

        html.Div([html.Img(src=app.get_asset_url('NGIF_logo_web_thumb.jpg'),
                 alt='National Green Infrastructure Facility', width=400)]),

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
        html.Div([dash_table.DataTable(
            id='table',
            columns=[{
                "name": col.replace('_', ' ').title(),
                "id": col,
                "deletable": False,
                "selectable": False
            } for col in ['name', 'field', 'units', 'last_updated', 'last_value']],
            data=metadata.as_table(),
            editable=False,
            filter_action="native",
            sort_action="native",
            sort_mode="multi",
            row_deletable=False,
            cell_selectable=False,
            page_action="native",
            page_current=0,
            page_size=10
        ), html.A('Download metadata table', href='/download-metadata')], style={'padding-bottom': 40}),

        dcc.Graph(figure=map_figure),
        html.Div(
            [
                html.Img(src=app.get_asset_url('ncl logo no bkgrd.png'), width=150, alt='Newcastle University',
                         style={'padding-right': 20}),
                html.Img(src=app.get_asset_url('UKCRIC_logo.jpg'), width=150, alt='UKCRIC')],
            style={'width': 320, 'margin': 'auto'}),

    ], style={'max-width': 800, 'margin': 'auto'})


@app.callback(Output(component_id='table', component_property='data'),
              [Input('update', 'n_clicks')])
def update_table(_):
    metadata.update()
    return metadata.as_table()


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

    field_metadata = metadata.get_field_metadata(name, field)
    df = pd.DataFrame(list(readings.find({'name': field_metadata.db_name, field_metadata.db_field: {"$exists": True},
                                          "time": {"$lt": datetime.fromisoformat(end_date) + timedelta(days=1),
                                                   "$gte": datetime.fromisoformat(start_date)}},

                                         {field_metadata.db_field: 1, 'time': 1},
                                         sort=[('_id', DESCENDING)])))
    if len(df) > 0:
        fig = px.line(df, x="time", y=field_metadata.db_field)
        fig.update_layout({'xaxis': {'title': None}, 'yaxis': {'title': metadata.get_field_with_units(name, field)}})
        fig.update_traces(mode='lines+markers')
    else:
        fig = {}
    return fig


@app.callback(Output(component_id='field', component_property='options'),
              [Input(component_id='name', component_property='value')])
def update_fields(name):
    if name is None:
        raise PreventUpdate

    return [{'label': row.field, 'value': row.field} for i, row in metadata.df[metadata.df.name == name].iterrows()]


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
    field_metadata = metadata.get_field_metadata(name, field)
    pd.DataFrame(list(readings.find({'name': field_metadata.db_name, field_metadata.db_field: {"$exists": True}},
                                    {'_id': False, field_metadata.db_field: 1, 'time': 1, },
                                    sort=[('_id', ASCENDING)]))).rename(
        columns={field_metadata.db_field: metadata.get_field_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{name}]-[{field}].csv',
                           as_attachment=True)


@app.server.route('/download-metadata')
def download_metadata():
    import io
    csv = io.StringIO()
    pd.DataFrame(metadata.as_table()).drop('id', axis=1).to_csv(csv, index=False)

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
    field_metadata = metadata.get_field_metadata(name, field)
    pd.DataFrame(list(readings.find({'name': field_metadata.db_name, field_metadata.db_field: {"$exists": True},
                                     "time": {"$lt": datetime.fromisoformat(end_date) + timedelta(days=1),
                                              "$gte": datetime.fromisoformat(start_date)}},
                                    {'_id': False, field_metadata.db_field: 1, 'time': 1, },
                                    sort=[('_id', ASCENDING)]))).rename(
        columns={field_metadata.db_field: metadata.get_field_with_units(name, field)}).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-[{name}]-[{field}].csv',
                           as_attachment=True)


app.layout = create_layout

if __name__ == '__main__':
    app.run_server(debug=True)
