import asyncio
import threading
import time
import unittest

from app.services.background import ThreadRuns


class ThreadRunsTest(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_loop_waits_for_the_running_round(self):
        runs = ThreadRuns("test")
        started, finished = threading.Event(), threading.Event()

        def work():
            started.set()
            time.sleep(0.2)
            finished.set()

        async def loop():
            while True:
                await runs.run(work)

        task = asyncio.create_task(loop())
        await asyncio.to_thread(started.wait, 2)
        task.cancel()
        await runs.wait(timeout=2)
        self.assertTrue(finished.is_set())

    async def test_gives_up_after_the_grace_period(self):
        runs = ThreadRuns("test")
        release = threading.Event()
        task = asyncio.create_task(runs.run(lambda: release.wait(5)))
        await asyncio.sleep(0.05)
        task.cancel()
        with self.assertLogs("app.services.background", "WARNING"):
            await runs.wait(timeout=0.1)
        release.set()

    async def test_nothing_to_wait_for(self):
        await ThreadRuns("test").wait(timeout=0.1)
