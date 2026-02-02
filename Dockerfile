FROM python:3.14-alpine@sha256:31da4cb527055e4e3d7e9e006dffe9329f84ebea79eaca0a1f1c27ce61e40ca5 AS build

COPY Pipfile .
COPY Pipfile.lock .

# generate the requirements file
RUN python3 -m pip install pipenv && \
    pipenv requirements > requirements.txt

FROM python:3.14-alpine@sha256:31da4cb527055e4e3d7e9e006dffe9329f84ebea79eaca0a1f1c27ce61e40ca5 AS base
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
