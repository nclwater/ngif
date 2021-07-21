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
from flask_pymongo import PyMongo, ASCENDING, DESCENDING
from dash.dependencies import Input, Output, State
from flask import request
from dash.exceptions import PreventUpdate
import urllib.parse
from datetime import timedelta, datetime
import re
import json


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
        self.df.loc[self.df.Location.isnull(), 'Location'] = self.df.name[self.df.Location.isnull()]

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

    locations = pd.read_csv('locations.csv', index_col='name') \
        if len(metadata.df) > 0 else None
    if locations is not None:
        map_figure = px.scatter_mapbox(
            locations.index,
            lat=locations.lat.tolist(),
            lon=locations.lon.tolist(),
            hover_name="name",
            zoom=16,
            mapbox_style='open-street-map')
        map_figure.update_layout({'margin': {'t': 0, 'b': 0, 'l': 0, 'r': 0}})
    else:
        map_figure = {}

    return html.Div(children=[

        html.Div([html.Img(src=app.get_asset_url('NGIF_logo_web_thumb.jpg'),
                 alt='National Green Infrastructure Facility', width=400)]),

        html.Div([
            dcc.Dropdown(
                id='theme',
                options=[{'label': s, 'value': s} for s in ['Location', 'Project', 'Parameter', 'SuDS/GI type', 'All']],
                value='Location',
            )
        ], style={'display': 'inline-block', 'width': '33%'}),

        html.Div([
            dcc.Dropdown(
                id='name',
                options=[],
                value=None,
            )
        ], style={'display': 'inline-block', 'width': '33%'}),
        html.Div([
            dcc.Dropdown(
                id='field',
            )
        ], style={'display': 'inline-block', 'width': '33%'}),

        dcc.DatePickerRange(
            id='date-picker',
            min_date_allowed=datetime(2000, 1, 1),
            max_date_allowed=end_date + timedelta(days=1),  # https://github.com/plotly/dash-core-components/issues/867
            start_date=start_date,
            end_date=end_date,
            display_format='DD/MM/YYYY',
            minimum_nights=0
        ),
        dcc.Checklist(id='smooth', options=[{'label': 'Smooth', 'value': '-'}]),
        html.P(),
        html.A(html.Button('Update Plot'), id='update'),
        html.A(html.Button('Download Selected Period'), id='download-link'),
        # html.A(html.Button('Download Entire Series'), id='download-all-link'),

        dcc.Loading(dcc.Graph(id='plot', figure={})),

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
                html.Img(src=app.get_asset_url('UKCRIC_logo.jpg'), width=150, alt='UKCRIC', style={'padding-right': 20}),
                html.A(html.Img(src=app.get_asset_url('cc by 4.0.png'), width=150, alt='CC BY 4.0',
                                style={'padding-right': 20}), href='http://doi.org/10.25405/data.ncl.14605569')
            ],
            style={'width': 520, 'margin': 'auto'}),
        html.Div(dcc.Markdown(
            "© UKCRIC National Green Infrastructure Facility. All NGIF data is licenced under a CC BY 4.0 licence. "
            "The NGIF licence can be found [here](http://doi.org/10.25405/data.ncl.14605569). "
            "Details on the CC BY 4.0 licence can be found [here](https://creativecommons.org/licenses/by/4.0/). "
            "Data downloads using the data app are limited to 30 days from the start date selected. "
            "If you would like to access longer term data, please access the NGIF data via the NGIF licence. "
            "Whilst every care is taken to ensure accurate measurements of in-situ conditions are reported, "
            "the NGIF data app records raw sensor value readings and no post-processing has been conducted. "
            "Please contact green.infrastructure@newcastle.ac.uk if you are planning to use our data. "
            "If you have any questions or problems with the data app, please contact the National "
            "Green Infrastructure Facility at mailto:green.infrastructure@newcastle.ac.uk"))

    ], style={'max-width': 800, 'margin': 'auto'})


@app.callback(Output(component_id='table', component_property='data'),
              [Input('update', 'n_clicks')])
def update_table(_):
    metadata.update()
    return metadata.as_table()


@app.callback(Output(component_id='plot', component_property='figure'),
              [Input('update', 'n_clicks')],
              [State(component_id='field', component_property='value'),
               State(component_id='date-picker', component_property='start_date'),
               State(component_id='date-picker', component_property='end_date'),
               State(component_id='smooth', component_property='value')
               ])
def update_plot(_, field, start_date, end_date, smooth):
    if field is None:
        raise PreventUpdate
    name, field = field.split('/')
    return create_plot(name, field, start_date, end_date, smooth)


def create_plot(name, field, start_date, end_date, smooth=False):
    if name is None or field is None:
        raise PreventUpdate

    df = get_data(name, field, start_date, end_date, smooth=smooth)
    if len(df) > 0:
        fig = px.line(df, x=df.columns[0], y=df.columns[1])
        fig.update_layout({'xaxis': {'title': None}, 'yaxis': {'title': df.columns[1]}})
        fig.update_traces(mode='lines+markers')
    else:
        fig = {}
    return fig


def get_data(name, field, start_date=None, end_date=None, smooth=False):
    field_metadata = metadata.get_field_metadata(name, field)
    df = pd.DataFrame(
        list(readings.find(
            {
                'name': field_metadata.db_name,
                field_metadata.db_field: {"$exists": True},
                "time": {
                    "$lt": datetime.fromisoformat(end_date) + timedelta(days=1),
                    "$gte": datetime.fromisoformat(start_date)
                } if start_date is not None else {"$exists": True},
            },
            {field_metadata.db_field: 1, 'time': 1, '_id': 0},
            sort=[('_id', ASCENDING)]))).rename(
        columns={field_metadata.db_field: metadata.get_field_with_units(name, field)})

    if smooth and len(df) > 0:
        values = df.iloc[:, 1].values.astype(float)
        idx = []
        for i, value in enumerate(values):
            idx.append(i)
            if value != 0:
                values[idx] = value / len(idx)
                idx = []
        df.iloc[:, 1] = values

    return df


@app.callback(Output(component_id='field', component_property='options'),
              [Input(component_id='name', component_property='value'),
               Input(component_id='theme', component_property='value')])
def update_fields(name, theme):
    if name is None:
        raise PreventUpdate
    fields = [{'label': row.field, 'value': f'{row["name"]}/{row.field}'}
            for i, row in metadata.df[metadata.df[theme].str.contains(name, regex=False, na=False)].iterrows()]

    return fields


@app.callback(Output(component_id='name', component_property='options'),
              [Input(component_id='theme', component_property='value')])
def update_names(theme):
    if theme is None:
        raise PreventUpdate
    options = set([s.strip() for group in metadata.df[theme].dropna().unique()
                   for s in group.split(';') if s != '\xa0'])
    options = [{'label': s, 'value': s} for s in options]
    options.sort(key=lambda key: [convert(int(c) if c.isdigit() else c.lower())
                                  for c in re.split('([0-9]+)', key['label'])])

    return options


@app.callback(
    dash.dependencies.Output('name', 'value'),
    [dash.dependencies.Input('name', 'options')])
def update_selected_name(available_options):
    if len(available_options) == 0:
        raise PreventUpdate
    return available_options[0]['value']


@app.callback(Output(component_id='smooth', component_property='style'),
              [Input(component_id='field', component_property='value')])
def update_checklist_style(field):
    if field is None:
        raise PreventUpdate

    if field.split('/')[1].lower().startswith('outflow'):
        return {'display': 'block'}
    else:
        return {'display': 'none'}


@app.callback(Output(component_id='smooth', component_property='value'),
              [Input(component_id='smooth', component_property='style')])
def update_checklist_value(style):
    if style['display'] == 'none':
        return []
    else:
        raise PreventUpdate


@app.callback(
    dash.dependencies.Output('field', 'value'),
    [dash.dependencies.Input('field', 'options')])
def update_selected_field(available_options):
    if len(available_options) == 0:
        raise PreventUpdate
    return available_options[0]['value']


# @app.callback(Output('download-all-link', 'href'),
#               [
#                   Input(component_id='field', component_property='value'),
#                   Input(component_id='smooth', component_property='value')
#                ])
# def update_href(field, smooth):
#     return urllib.parse.quote(f'/download-all/{field}' + ('/smooth' if smooth else ''))


@app.callback(Output('download-link', 'href'),
              [
                  Input(component_id='field', component_property='value'),
                  Input(component_id='date-picker', component_property='start_date'),
                  Input(component_id='date-picker', component_property='end_date'),
                  Input(component_id='smooth', component_property='value')
               ])
def update_href(field, start_date, end_date, smooth):
    return urllib.parse.quote(f'/download/{field}/{start_date}/{end_date}' + ('/smooth' if smooth else ''))


# @app.server.route('/download-all/<name>/<field>')
# @app.server.route('/download-all/<name>/<field>/smooth')
# def download_all(name, field):
#     import io
#     smooth = request.path.endswith('/smooth')
#     csv = io.StringIO()
#     get_data(name, field, smooth=smooth).to_csv(csv, index=False)
#
#     mem = io.BytesIO()
#     mem.write(csv.getvalue().encode('utf-8'))
#     mem.seek(0)
#
#     return flask.send_file(mem,
#                            mimetype='text/csv',
#                            attachment_filename=f'ngif-[{name}]-[{field}{" (smoothed)" if smooth else ""}].csv',
#                            as_attachment=True)


@app.server.route('/download-metadata')
def download_metadata():
    import io
    csv = io.StringIO()
    pd.DataFrame(metadata.as_table()).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(mem,
                           mimetype='text/csv',
                           attachment_filename=f'ngif-metadata.csv',
                           as_attachment=True)


@app.server.route('/download/<name>/<field>/<start_date>/<end_date>')
@app.server.route('/download/<name>/<field>/<start_date>/<end_date>/smooth')
def download(name, field, start_date, end_date):
    import io
    duration = datetime.strptime(end_date, '%Y-%m-%d') - datetime.strptime(start_date, '%Y-%m-%d')
    if duration > timedelta(days=30):
        mem = io.BytesIO()
        mem.write('Requested period too long, must be less than 30 days. To download full series go to http://doi.org/10.25405/data.ncl.14605569'.encode('utf-8'))
        mem.seek(0)
        return flask.send_file(
            mem,
            mimetype='text',
            attachment_filename=f'error.txt',
            as_attachment=True)

    smooth = request.path.endswith('/smooth')
    csv = io.StringIO()
    get_data(name, field, start_date, end_date, smooth=smooth).to_csv(csv, index=False)

    mem = io.BytesIO()
    mem.write(csv.getvalue().encode('utf-8'))
    mem.seek(0)

    return flask.send_file(
        mem,
        mimetype='text/csv',
        attachment_filename=f'ngif-[{name}]-[{field}{" (smoothed)" if smooth else ""}]-[{start_date}]-[{end_date}].csv',
        as_attachment=True)


@app.server.route('/upload/eml', methods=['POST'])
def upload():
    uploaded_data = request.get_json()

    if len(uploaded_data) == 0:
        return json.dumps({'uploaded': False}), 200, {'ContentType': 'application/json'}

    units = {}
    data = []

    for row in uploaded_data:
        data_row = {'time': row['time'], 'unitID': row['unitID']}
        for k, v in row.items():
            if k not in ['customer', 'unitID', 'time']:
                data_row[k] = v[0]
                units[k + '.units'] = v[-1]
        data.append(data_row)

    data = pd.DataFrame(data)
    data['time'] = pd.to_datetime(data.time)

    for name in data.unitID.unique():

        name_data = data[data.unitID == name].drop(columns='unitID')

        last_entry = readings.find_one(
            {'name': name}, {'time': 1},
            sort=[('_id', DESCENDING)]
        )

        if last_entry is not None:
            last_time = pd.to_datetime(last_entry['time'])
            name_data = name_data[name_data.time > last_time]
            if len(name_data) == 0:
                continue

        updated_time = {}
        latest_value = {}

        for col in name_data.columns:
            if col != 'time' and name_data[col].notnull().any():
                records = name_data[[col, 'time']].dropna()
                last_record = records.loc[[records['time'].idxmax()]].to_dict('records')[0]
                updated_time[col + '.last_updated'] = last_record['time']
                latest_value[col + '.last_value'] = last_record[col]

        mongo.db.sensors.update_one({'name': name}, {'$set': {**units, **updated_time, **latest_value}}, upsert=True)

        readings.insert_many({'name': name, 'uploaded_by': request.remote_addr,
                              **{k: v for k, v in row.items() if pd.notna(v)}}
                             for row in name_data.to_dict('records'))

    return json.dumps({'uploaded': True}), 200, {'ContentType': 'application/json'}


app.layout = create_layout

if __name__ == '__main__':
    app.run_server(debug=True)
