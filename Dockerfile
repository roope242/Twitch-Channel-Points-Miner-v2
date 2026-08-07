# Overridable so the suite can be run against another interpreter without
# editing this file: `--build-arg PYTHON_VERSION=3.13`. The default is what
# ships, and the CI container leg builds the default.
ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim-bookworm AS base

# Unbuffered stdout/stderr so `podman logs` shows miner output as it happens
# instead of in block-sized bursts.
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

COPY ./requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# The test stage adds pytest and the suite on top of the runtime's exact
# interpreter and resolved dependencies, so a failure here is a failure the
# published image would have. It is deliberately not the last stage: the
# last stage is what a bare `docker build .` produces, and that has to stay
# the runtime image for deploy-docker.yml. Build this one with
# `--target test`.
FROM base AS test

COPY ./requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY ./TwitchChannelPointsMiner ./TwitchChannelPointsMiner
COPY ./tests ./tests
COPY ./conftest.py ./

# `python -m pytest`, not the `pytest` console script -- the module form is
# what puts /usr/src/app on sys.path, and the package is not pip-installed
# here. This is the mismatch that made CI collect zero tests in #27.
ENTRYPOINT []
CMD ["python", "-m", "pytest", "tests/", "-v"]

FROM base AS runtime

COPY ./TwitchChannelPointsMiner ./TwitchChannelPointsMiner

ENTRYPOINT [ "python", "run.py" ]
