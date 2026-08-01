FROM python:3.10-slim-bookworm

# Unbuffered stdout/stderr so `podman logs` shows miner output as it happens
# instead of in block-sized bursts.
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

COPY ./requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ./TwitchChannelPointsMiner ./TwitchChannelPointsMiner

ENTRYPOINT [ "python", "run.py" ]
