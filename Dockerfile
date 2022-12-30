FROM python:3.11-alpine

RUN /usr/local/bin/pip3 install flask flask_httpauth docker waitress

COPY pipeline_engine.py /app/
COPY server.py /app/
COPY config.ini /app/

WORKDIR /app

EXPOSE 8181

CMD ["python3", "server.py"]