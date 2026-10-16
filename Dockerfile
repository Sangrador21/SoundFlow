FROM python:3.12-slim AS catalog
ARG SOUNDFLOW_NODE_ID=S1
WORKDIR /catalog
COPY music/ /source-music/
COPY deploy/catalogs/ /catalog/deploy/catalogs/
COPY tools/build_catalog.py /catalog/tools/build_catalog.py
RUN python tools/build_catalog.py --node "$SOUNDFLOW_NODE_ID" --source /source-music --output /selected \
    && mv "/selected/$SOUNDFLOW_NODE_ID" /node-music

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 SOUNDFLOW_MUSIC_DIR=/app/music
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home soundflow
COPY backend/requirements.txt backend/constraints.txt /app/backend/
RUN pip install --no-cache-dir -r backend/requirements.txt -c backend/constraints.txt
COPY backend/ /app/backend/
COPY --from=catalog /node-music/ /app/music/
RUN chown -R soundflow:soundflow /app
USER soundflow
EXPOSE 10000
CMD ["gunicorn", "--chdir", "backend", "--config", "/app/backend/gunicorn.conf.py", "wsgi:app"]
