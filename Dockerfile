FROM python:3.8.6-slim

RUN mkdir /src

WORKDIR /src

COPY requirements.txt ./

RUN pip install -r requirements.txt

RUN pip install gunicorn

COPY app.py ./
COPY ngif-sensor-fields.csv ./
COPY locations.csv ./
COPY assets ./assets

CMD gunicorn  --timeout 600 --workers 3 app:server
