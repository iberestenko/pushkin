import re
import shlex
from app.brains import render_pushkin_template

def parse_config_file(file_path, vendor="cisco"):
    tasks = []
    # Словарь для хранения команд по каждому устройству: { ip: [cmd1, cmd2, ...] }
    device_commands = {}
    current_host = None

    # Регулярка для IP или DNS-имени (начинается с буквы/цифры, может содержать точки и дефисы)
    # Исключает строки с двоеточием (чтобы не спутать с командой)
    host_regex = r'^([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])(\.([a-zA-Z0-9]|[a-zA-Z0-9][a-zA-Z0-9\-]{0,61}[a-zA-Z0-9]))*$'

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line: continue

            # 1. Проверяем, является ли строка Хостом (IP или DNS)
            # Условие: регулярка совпала И в строке нет двоеточия (команды)
            if re.match(host_regex, line) and ":" not in line:
                current_host = line
                if current_host not in device_commands:
                    device_commands[current_host] = []
                continue

            # 2. Обработка команды для текущего хоста
            if current_host and ":" in line:
                template_raw, args_raw = line.split(":", 1)
                template_name = template_raw.strip().replace(" ", "_")
                
                try:
                    # Разбираем аргументы через shlex (умные кавычки)
                    lexer = shlex.shlex(args_raw, posix=True)
                    lexer.whitespace_split = True
                    raw_args_list = list(lexer)
                    
                    params = {}
                    for item in raw_args_list:
                        if "=" in item:
                            k, v = item.split("=", 1)
                            params[k] = v
                    
                    # Рендерим шаблон
                    rendered = render_pushkin_template(vendor, template_name, params)
                    if rendered:
                        # Добавляем список команд к текущему устройству
                        device_commands[current_host].extend(rendered)
                
                except Exception as e:
                    print(f"❌ Ошибка в строке '{line}': {e}")

    # Формируем финальный список задач для Пушкина
    for host, cmds in device_commands.items():
        if cmds:
            tasks.append({
                "ip": host,
                "port": 22,
                "user": "admin",
                "pw": "password",
                "cmds": cmds
            })
    
    return tasks

if __name__ == "__main__":
    all_tasks = parse_config_file("jobs-cisco.txt", vendor="cisco")
    for task in all_tasks:
        print(f"HOST: {task['ip']}")
        print(f"CMDS: {task['cmds']}\n")
