FROM python:3.10-alpine

COPY requirements.txt /app/
RUN /usr/local/bin/python3 -m pip install --upgrade pip && \
    /usr/local/bin/pip3 install -r /app/requirements.txt

COPY pipeline_engine.py /app/
COPY server.py /app/
COPY reload_tasks.py /app/
COPY config.ini /app/

WORKDIR /app

EXPOSE 8181

CMD ["python3", "server.py"]