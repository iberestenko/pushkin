import asyncio
from app.transport import get_transport


class PushkinAsyncEngine:

    def __init__(self, max_concurrent=500, redis_instance=None):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.redis = redis_instance

    async def run_pushkin_task(self, device_cfg, job_id, quiet_period=2.0):
        transport = get_transport(device_cfg.get("proto", "ssh"))
        return await transport.run_task(
            device_cfg, job_id, self.semaphore, self.redis, quiet_period
        )

    async def run_mass_config(self, device_list, job_id):
        tasks = [self.run_pushkin_task(d, job_id) for d in device_list]
        # return await asyncio.gather(*tasks)
        results = []
        for task in tasks:
            results.append(await task)
        return results