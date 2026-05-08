import asyncio
from app.worker import PushkinAsyncEngine

async def test_real_devices():
    # 1. Список ваших реальных устройств
    devices = [
        {
            "ip": "192.168.88.1",  # Замените на реальный IP
            "port": 22,
            "user": "admin",
            "pw": "your_password",
            "cmds": [
                "show ip interface brief",
                "show version"
            ]
        },
        # Можно добавить второе устройство для проверки параллельности
        {
            "ip": "192.168.88.2",
            "port": 22,
            "user": "admin",
            "pw": "your_password",
            "cmds": ["show inventory"]
        },
        {
            "ip": "100.64.20.1",
            "port": 22,
            "user": "admin",
            "pw": "your_password",
            "cmds": ["show inventory"]
        }
    ]

    # 2. Инициализация движка БЕЗ редиса
    # Мы передаем redis_instance=None, поэтому воркер просто пропустит публикацию метрик
    engine = PushkinAsyncEngine(max_concurrent=10, redis_instance=None)

    print(f"🚀 Starting Pushkin on {len(devices)} real devices...")
    
    # 3. Запуск
    # job_id можно передать любой, так как Redis не используется
    results = await engine.run_mass_config(devices, job_id="real-world-test")

    # 4. Вывод результатов в консоль
    print("\n" + "="*50)
    print("FINAL REPORT")
    print("="*50)

    for res in results:
        status_icon = "✅" if res['status'] == "success" else "❌"
        print(f"{status_icon} Device: {res['id']}")
        print(f"   Status: {res['status']}")
        print(f"   Time:   {res.get('time', 'N/A')}s")
        
        if res['status'] == "success":
            # Печатаем последние 5 строк лога для краткости
            log_lines = res['log'].strip().split('\n')[-5:]
            print("   Last log output:")
            for line in log_lines:
                print(f"      | {line}")
        else:
            print(f"   Error: {res.get('error', 'Unknown error')}")
            if res.get('failed_on'):
                print(f"   Failed on command: {res['failed_on']}")
        print("-" * 50)

if __name__ == "__main__":
    try:
        asyncio.run(test_real_devices())
    except KeyboardInterrupt:
        print("\nStopped by user.")
