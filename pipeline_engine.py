import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import flask_log_request_id
from docker import DockerClient


class PipelineEngine:
    def __init__(self):
        self._executor = ThreadPoolExecutor(max_workers=1)

    def schedule(self, ctx, *steps):
        return self._executor.submit(self._pipeline, ctx, *steps)

    def _pipeline(self, ctx, *steps):
        def get_request_id():
            return ctx.request_id
        flask_log_request_id.request_id.current_request_id.register_fetcher(get_request_id)
        rollback = []
        try:
            for i, step in enumerate(steps):
                if ctx.skip_pipeline:
                    return
                ctx.log.info(f"Execute step {i + 1}/{len(steps)}: {step}")
                rollback.insert(0, step)
                ctx = step.execute(ctx)
            ctx.log.info("Pipeline successfully finished.")
        except Exception as e:
            ctx.log.error(f"Error execute pipeline on step {i + 1}: {rollback[0]}: {e}")
            for step in rollback:
                ctx.log.info(f"Unexecute task: {step}")
                try:
                    ctx = step.unexecute(ctx)
                except Exception as ex:
                    ctx.log.error(f"Error during rollback: {ex}")
            raise Exception("Failed to deploy new image, see log for more information.")
        finally:
            flask_log_request_id.request_id.current_request_id.ctx_fetchers.remove(get_request_id)


@dataclass
class Context:
    client: DockerClient
    request_id: str
    log: logging.Logger
    skip_pipeline: bool
    params: dict[str, any]
