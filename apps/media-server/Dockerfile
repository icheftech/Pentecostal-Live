# Build from the REPO ROOT so services/ffmpeg is in the context:
#   docker build -f apps/media-server/Dockerfile -t pentecostal-live-media-server .
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv

COPY services/ffmpeg ./services/ffmpeg
COPY apps/media-server/requirements.txt ./apps/media-server/requirements.txt
RUN pip install --no-cache-dir -r apps/media-server/requirements.txt ./services/ffmpeg

COPY apps/media-server/media_server ./apps/media-server/media_server

WORKDIR /srv/apps/media-server
ENV PENTECOSTAL_LIVE_HLS_ROOT=/var/pentecostal-live/hls
RUN mkdir -p /var/pentecostal-live/hls

EXPOSE 8001
CMD ["uvicorn", "media_server.main:app", "--host", "0.0.0.0", "--port", "8001"]
