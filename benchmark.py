import asyncio
import time
import argparse
from app.worker import PushkinAsyncEngine
import redis.asyncio as redis

async def run_benchmark(total_devices, concurrent_limit, quiet_period):
    # Подключаемся к Redis для сброса метрик перед тестом
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    # await r.flushdb() # Чистим старые метрики
    await r.delete("pushkin:metrics:total_processed")
    await r.delete("pushkin:metrics:config_errors")
    await r.delete("pushkin:metrics:conn_errors")
    await r.set("pushkin:metrics:active_sessions", 0)
    
    engine = PushkinAsyncEngine(max_concurrent=concurrent_limit, redis_instance=r)
    
    # Формируем список устройств (все шлем на наш локальный мок)
    devices = [
        {
            "ip": "127.0.0.1",
            "port": 2222,
            "user": "admin",
            "pw": "admin",
            "cmds": [
                "conf t", 
                f"description BENCHMARK_TEST_{i}", 
                "interface Gi0/1", 
                "ip address 1.1.1.1 255.255.255.0", 
                "end"
            ]
        } for i in range(total_devices)
    ]

    print(f"🚀 PUSHKIN BENCHMARK STARTED")
    print(f"---------------------------------")
    print(f"Total devices:    {total_devices}")
    print(f"Max concurrent:   {concurrent_limit}")
    print(f"Silence timeout:  {quiet_period}s")
    print(f"---------------------------------")

    start_time = time.perf_counter()

    # Запуск основного процесса
    # Мы передаем job_id 'benchmark', чтобы стриминг шел в один канал
    results = await engine.run_mass_config(devices, job_id="benchmark")

    end_time = time.perf_counter()
    total_duration = end_time - start_time

    # Анализ результатов
    success = len([r for r in results if r.get('status') == 'success'])
    errors = total_devices - success
    tps = total_devices / total_duration # Устройств в секунду

    print(f"\n✅ BENCHMARK FINISHED")
    print(f"Total time:       {total_duration:.2f} seconds")
    print(f"Average speed:    {tps:.2f} devices/sec")
    print(f"Success:          {success}")
    print(f"Errors:           {errors}")
    
    if total_duration > 0:
        forecast_150k = (150000 / tps) / 60
        print(f"Forecast for 150k: {forecast_150k:.2f} minutes")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pushkin Load Tester")
    parser.add_argument("--total", type=int, default=1000, help="Total devices to test")
    parser.add_argument("--concurrent", type=int, default=500, help="Simultaneous sessions")
    parser.add_argument("--quiet", type=float, default=2.0, help="Silence timeout")
    
    args = parser.parse_args()
    
    try:
        asyncio.run(run_benchmark(args.total, args.concurrent, args.quiet))
    except KeyboardInterrupt:
        print("\n[!] Benchmark interrupted.")

