#!/usr/bin/env python3
import configparser
import logging
import os
from uuid import uuid4

import docker
from flask import Flask, request
from flask_httpauth import HTTPTokenAuth
from flask_log_request_id import RequestID, RequestIDLogFilter
from flask_log_request_id.request_id import flask_ctx_get_request_id
from pipeline_engine import PipelineEngine, Context
from reload_tasks import CompareNewDockerImageWithExistingImages, PullDockerImage, CollectRunningContainers, \
    RunDockerContainer, WaitContainerReadiness, RemoveOldContainers, RemoveOldImages

config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
config.optionxform = lambda e: e
config.read('config.ini')
config.read_dict({'env': os.environ})

docker_client = docker.DockerClient(**dict(config.items('docker')))
logging.basicConfig(level=logging.getLevelName(config.get('logging', 'level')))

app = Flask(__name__)
auth = HTTPTokenAuth(header=config.get('auth', 'header'))
RequestID(app)

handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)-8s [%(name)s] %(request_id)s - %(message)s"))
handler.addFilter(RequestIDLogFilter())
logging.getLogger().handlers = [handler]

pipeline_engine = PipelineEngine()


@auth.verify_token
def verify_token(token):
    method = request.method
    url = request.url
    address = request.remote_addr
    real_ip = request.headers.get('X-Real-IP', request.headers.get("X-Forwarded-For", "None"))
    app.logger.info(f"Request {method} {url} from IP:{address}, real IP:{real_ip}")
    success_auth = token == config.get('auth', 'api_key')
    if not success_auth:
        app.logger.info(f"API key is not valid, apikey = {token}")
    return success_auth


@app.route('/', methods=['POST'])
@auth.login_required
def reload_image():
    new_image = request.get_json()['image']
    if not new_image.startswith(config.get('filter', 'image_name')):
        app.logger.warning(f'Invalid image name {new_image}')
        return "Invalid image name", 400
    app.logger.info('Got new image: %s', new_image)

    future = pipeline_engine.schedule(
        Context(
            client=docker_client,
            request_id=flask_ctx_get_request_id(),
            log=logging.getLogger('pipeline'),
            skip_pipeline=False,
            params={}
        ),
        CompareNewDockerImageWithExistingImages(new_image),
        PullDockerImage(new_image),
        CollectRunningContainers(config.get('filter', 'label')),
        RunDockerContainer(
            image=new_image,
            name=f"{config.get('container options', 'name_prefix')}-{str(uuid4())[:8]}",
            detach=True,
            environment=dict(config.items('container environments')),
            labels=dict(config.items('container labels')),
            restart_policy=dict(config.items('container restart policy')),
            network=config.get('container options', 'network'),
            mem_limit=config.get('container options', 'mem_limit'),
            # nano_cpus=config.getint('container options', 'nano_cpus')
        ),
        WaitContainerReadiness(
            check_command=config.get('container healthcheck', 'check_command'),
            check_interval=config.getint('container healthcheck', 'check_interval'),
            retries=config.getint('container healthcheck', 'retries')
        ),
        RemoveOldContainers(),
        RemoveOldImages(new_image)
    )
    try:
        future.result()
        return "OK", 200
    except Exception as e:
        return str(e), 500


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=8181)
