import logging
import unittest

from pipeline_engine import Context, PipelineEngine

logging.basicConfig(level=logging.INFO)
context = Context(client=None, request_id="test_request_id", log=logging.getLogger(), skip_pipeline=False, params={})
pipeline_engine = PipelineEngine()


class TestEngine(unittest.TestCase):

    def test_pipeline_success(self):
        ran_tasks = []
        future = pipeline_engine.schedule(context, SimpleTask(ran_tasks), SimpleTask(ran_tasks))
        future.result()
        self.assertEqual(2, len(ran_tasks))

    def test_pipeline_fail_and_rollback(self):
        ran_tasks = []
        future = pipeline_engine.schedule(context, SimpleTask(ran_tasks), SimpleTask(ran_tasks, is_broken=True))
        self.assertRaises(Exception, future.result)
        self.assertEqual(0, len(ran_tasks))


class SimpleTask:
    def __init__(self, steps, is_broken=False):
        self.is_broken = is_broken
        self.steps = steps

    def execute(self, ctx):
        self.steps.append("task")
        if self.is_broken:
            raise Exception("Broken")
        return ctx

    def unexecute(self, ctx):
        self.steps.pop()
        return ctx

    def __str__(self):
        return f"TestTask, is_broken={self.is_broken}"


if __name__ == '__main__':
    unittest.main()
