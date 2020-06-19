FROM python:3.8

RUN apt-get update && \
    apt-get install -y ffmpeg

RUN pip install --no-cache-dir youtube-dl flask

RUN mkdir /app

EXPOSE 80
WORKDIR /app

COPY example_config.json /config.json
COPY youtube_dl_webui/ /app/youtube_dl_webui/

CMD ["python", "-m", "youtube_dl_webui", "-c", "/config.json"]