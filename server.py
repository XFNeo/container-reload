#!/usr/bin/env python3
from flask import Flask, request
from flask_httpauth import HTTPTokenAuth
import docker
import configparser
import os
from pipeline_engine import *

config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())
config.optionxform = lambda e: e
config.read_dict({'env': os.environ})
config.read('config.ini')

docker_client = docker.DockerClient(**dict(config.items('docker')))
logging.basicConfig(level=logging.getLevelName(config.get('logging', 'level')))

app = Flask(__name__)
auth = HTTPTokenAuth(header=config.get('auth', 'header'))


@auth.verify_token
def verify_token(token):
    return token == config.get('auth', 'api_key')

@app.route('/', methods=['POST'])
@auth.login_required
def reload_image():
    new_image = request.get_json()['image']
    app.logger.info('Got new image: %s', new_image)
    try:
        execute_pipeline(
            Context(
                client=docker_client,
                skip_pipeline=False,
                log=logging.getLogger("pipeline"),
                params={}
            ),
            CompareNewDockerImageWithExistingImages(new_image),
            PullDockerImage(new_image),
            CollectRunningContainers(config.get('filter', 'label')),
            RunDockerContainer(
                image=new_image,
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
    except Exception as e:
        app.logger.exception(e)
        return str(e), 500
    return "OK", 200


if __name__ == '__main__':
    from waitress import serve
    serve(app, host='0.0.0.0', port=8181)
