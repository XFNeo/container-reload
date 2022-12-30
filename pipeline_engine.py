import logging
import time
from dataclasses import dataclass
from docker import DockerClient


def execute_pipeline(ctx, *steps):
    rollback = []
    try:
        for i, step in enumerate(steps):
            if ctx.skip_pipeline: return
            ctx.log.info(f"Execute step {i+1}/{len(steps)}: {step}, context:{ctx}")
            rollback.insert(0, step)
            ctx = step.execute(ctx)
        ctx.log.info("Pipeline successfully finished.")
    except Exception as e:
        ctx.log.info(f"Error execute pipeline on step {i+1}: {rollback[0]}: {e}")
        for step in rollback:
            ctx.log.info(f"Unexecute task: {step}")
            try:
                ctx = step.unexecute(ctx)
            except Exception as ex:
                ctx.log.info(f"Error during rollback: {ex}")

        raise Exception("Failed to deploy new image, see log for more information.")

@dataclass
class Context:
    client: DockerClient
    log: logging.Logger
    skip_pipeline: bool
    params: dict[str, any]

class CompareNewDockerImageWithExistingImages:
    def __init__(self, image):
        self.image = image

    def execute(self, ctx):
        images = ctx.client.images.list(name=self.image.split("@")[0])
        for image in images:
            if self.image in image.attrs['RepoDigests']:
                ctx.log.info("The image is already present in the local repository. The pipeline will be skipped.")
                ctx.skip_pipeline = True
        return ctx
    def unexecute(self, ctx):
        return ctx

    def __str__(self):
        return f"CompareNewDockerImageWithExistingImages"

class PullDockerImage:
    def __init__(self, image):
        self.image = image

    def execute(self, ctx):
        ctx.log.info(f"Pull image: {self.image}")
        ctx.client.images.pull(self.image)
        return ctx
    def unexecute(self, ctx):
        ctx.log.info(f"Remove image: {self.image}" )
        ctx.client.images.remove(image=self.image)
        return ctx

    def __str__(self):
        return f"PullDockerImage"

class CollectRunningContainers:
    def __init__(self, label):
        self.label = label

    def execute(self, ctx):
        ctx.log.info(f"Collect running containers with label: {self.label}")
        container_list = ctx.client.containers.list(all=True, filters={"label": [self.label]})
        ctx.log.info(f'Found {len(container_list)} running container(s): {container_list}')
        ctx.params["running_containers"] = container_list
        return ctx
    def unexecute(self, ctx):
        return ctx

    def __str__(self):
        return f"CollectRunningContainers"

class RunDockerContainer:
    def __init__(self, **kvargs):
        self.kvargs = kvargs

    def execute(self, ctx):
        ctx.params["new_container"] = ctx.client.containers.create(**self.kvargs)
        ctx.log.info(f"New container has been created. Starting: {ctx.params['new_container']}")
        ctx.params["new_container"].start()
        ctx.log.info(f"Container successfully started.")
        return ctx
    def unexecute(self, ctx):
        if ctx.params.get("new_container") is None:
            return
        container = ctx.params["new_container"]
        ctx.log.info(f"Delete container: {container}")
        container.remove(force=True)
        return ctx

    def __str__(self):
        return f"RunDockerContainer"

class WaitContainerReadiness:

    def __init__(self, check_command, check_interval, retries):
        self.check_command = check_command
        self.check_interval = check_interval
        self.retries = retries

    def execute(self, ctx):
        ctx.log.info("Check container readiness probe...")
        for i in range(self.retries):
            time.sleep(self.check_interval)
            exit_code, output = ctx.params["new_container"].exec_run(cmd=self.check_command)
            if exit_code == 0:
                ctx.log.info("Readiness probe passed")
                return ctx
        raise TimeoutError(f"Container readiness probe failed within {self.check_interval * self.retries}sec")

    def unexecute(self, ctx):
        return ctx

    def __str__(self):
        return f"WaitContainerReadiness"

class RemoveOldContainers:

    def execute(self, ctx):
        for container in ctx.params["running_containers"]:
            ctx.log.info(f"Remove old container with id: {container.id}")
            container.remove(force=True)
        return ctx

    def unexecute(self, ctx):
        return ctx

    def __str__(self):
        return f"RemoveOldContainers"

class RemoveOldImages:
    def __init__(self, image):
        self.image = image

    def execute(self, ctx):
        try:
            images = ctx.client.images.list(name=self.image.split("@")[0])
            for image in images:
                if self.image not in image.attrs['RepoDigests']:
                    ctx.log.info(f"Remove old image with id: {image.id}")
                    ctx.client.images.remove(image.id)
        except Exception as e:
            ctx.log.info(f"Error during rollback of step RemoveOldImages: {e}")
        return ctx

    def unexecute(self, ctx):
        return ctx

    def __str__(self):
        return f"RemoveOldImages"