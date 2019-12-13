FROM python:3.7-buster

ARG REDIS_SERVER=${REDIS_SERVER}
ARG REDIS_PORT=${REDIS_PORT}
ARG REDIS_PASSWORD=${REDIS_PASSWORD}
ARG PORT=${PORT}

RUN python3 -m pip install --upgrade pip

COPY . /app

WORKDIR /app

RUN python3 -m pip install --no-warn-script-location --no-cache-dir -r requirements.txt

EXPOSE ${PORT}

ENTRYPOINT [ "python3" ]

CMD [ "server_japronto.py" ]