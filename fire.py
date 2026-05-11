import asyncio
import re
import shlex
import time
import getpass
import os
import argparse  # Добавили для обработки аргументов
from app.brains import render_pushkin_template
from app.worker import PushkinAsyncEngine

# --- НАСТРОЙКИ ПО УМОЛЧАНИЮ ---
USER = getpass.getuser()
PASS = getpass.getpass("Enter your password:")
MAX_CONCURRENT = 50 


def parse_jobs(file_path, vendor):
    """Парсит файл и группирует команды по хостам."""
    device_commands = {}
    current_host = current_port = device_id = None
    host_regex = r'^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*(\s[0-9]+)?$'
    # TODO: set port via name:port
    try:
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line: continue

                if re.match(host_regex, line) and ":" not in line:
                    if ' ' in line:
                        split = line.split(' ', 1)
                        current_host = split[0]
                        current_port = split[1]
                        device_id = f"{current_host}:{current_port}"
                    else:
                        current_host = line
                        device_id = f"{current_host}:22"
                    if device_id not in device_commands:
                        device_commands[device_id] = []
                    continue

                if device_id and ":" in line:
                    template_raw, args_raw = line.split(":", 1)
                    template_name = template_raw.strip().replace(" ", "_")
                    
                    try:
                        lexer = shlex.shlex(args_raw, posix=True)
                        lexer.whitespace_split = True
                        params = {item.split("=", 1)[0]: item.split("=", 1)[1] 
                                 for item in list(lexer) if "=" in item}
                        
                        rendered = render_pushkin_template(vendor, template_name, params)
                        if rendered:
                            device_commands[device_id].extend(rendered)
                    except Exception as e:
                        print(f"❌ Ошибка парсинга '{line}': {e}")
    except FileNotFoundError:
        print(f"❌ Файл '{file_path}' не найден.")
        return []

    return [
        {"ip": device_id.split(':', 1)[0], "port": device_id.split(':', 1)[1], "user": USER, "pw": PASS, "cmds": cmds}
        for device_id, cmds in device_commands.items() if cmds
    ]

async def fire(file_path, vendor, dry_run=False):
    print(f"📖 Reading jobs from: {file_path} (Vendor: {vendor})")
    tasks = parse_jobs(file_path, vendor)
    
    if not tasks:
        return
    
    if dry_run:
        print("\n")
        for task in tasks:
            print(f"👾 HOST: {task['ip']}:{task['port']}")
            print(f"📝 CMDS: {task['cmds']}\n")
    else:
        print(f"🎯 Ready to fire at {len(tasks)} devices...")
        engine = PushkinAsyncEngine(max_concurrent=MAX_CONCURRENT, redis_instance=None)
        
        start_time = time.perf_counter()
        results = await engine.run_mass_config(tasks, job_id="manual-fire")
        duration = time.perf_counter() - start_time

        print(f"\n🚀 FIRE FINISHED in {duration:.2f}s")
        
        success_count = sum(1 for res in results if res['status'] == "success")
        for res in results:
            status = "✅" if res['status'] == "success" else "❌"
            print(f"{status} {res['id']} - {res['status']}")

        print("\n📝 Logs:")
        for res in results:
            print(f"Log of {res['id']}:\n{res['log']}")

        print(f"\nTotal: {len(tasks)} | Success: {success_count} | Failed: {len(tasks)-success_count}")

if __name__ == "__main__":
    # Настройка парсера аргументов командной строки
    parser = argparse.ArgumentParser(description="Pushkin Engine: CLI Fire Tool")
    
    # Позиционные аргументы (обязательные)
    parser.add_argument("commands_file", help="Path to the jobs.txt file")
    parser.add_argument("vendor", help="Vendor name (cisco, huawei, eltex, mikrotik, ...)")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without sending them")
    
    args = parser.parse_args()

    try:
        asyncio.run(fire(args.commands_file, args.vendor, args.dry_run))
    except KeyboardInterrupt:
        print("\n[!] Stopped by user.")
