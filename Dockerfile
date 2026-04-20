FROM python:3.14-alpine@sha256:dd4d2bd5b53d9b25a51da13addf2be586beebd5387e289e798e4083d94ca837a AS build

COPY Pipfile .
COPY Pipfile.lock .

# generate the requirements file
RUN python3 -m pip install pipenv && \
    pipenv requirements > requirements.txt

FROM python:3.14-alpine@sha256:dd4d2bd5b53d9b25a51da13addf2be586beebd5387e289e798e4083d94ca837a AS base
ENV PYTHONUNBUFFERED=true

ARG APP_ROOT=/usr/local/bin/randhaj
ARG APP_VERSION

RUN adduser -u 1101 -D randhaj
RUN mkdir -pv ${APP_ROOT}
RUN chown -R 1101:1101 ${APP_ROOT}

WORKDIR ${APP_ROOT}

COPY --from=build requirements.txt .
RUN apk update && \
    apk add git && \
    python3 -m pip install -r requirements.txt && \
    apk del git && \
    apk cache clean

COPY --chown=1101:1101 api api
COPY --chown=1101:1101 resources resources
COPY --chown=1101:1101 main.py main.py

USER randhaj

ENV RANDHAJ_IMAGE_DIR="/var/assets"
ENV APP_VERSION=${APP_VERSION}

CMD [ "/usr/bin/env", "python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0" ]
