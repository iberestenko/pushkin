import re
from app.brains import render_pushkin_template

def parse_config_file(file_path, vendor="cisco"):
    tasks = []
    current_ip = None
    
    # Регулярка для аргументов (поддерживает кавычки)
    arg_regex = r'(\w+)=("(?:\\"|[^"])*"|\S+)'

    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            # 1. Проверяем, является ли строка IP-адресом (простой паттерн)
            if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', line):
                current_ip = line
                continue

            # 2. Если есть текущий IP и строка содержит двоеточие (это команда)
            if current_ip and ":" in line:
                # Разбиваем на: название шаблона и аргументы
                template_raw, args_raw = line.split(":", 1)
                
                template_name = template_raw.strip().replace(" ", "_")
                
                # Парсим аргументы
                arg_pairs = re.findall(arg_regex, args_raw)
                params = {k: v.strip('"') for k, v in arg_pairs}

                # Рендерим команды
                commands = render_pushkin_template(vendor, template_name, params)
                
                if commands:
                    tasks.append({
                        "ip": current_ip,
                        "port": 22,
                        "user": "admin",
                        "pw": "password",
                        "cmds": commands
                    })
                else:
                    print(f"⚠️  Шаблон '{template_name}' не найден для вендора {vendor}")

    return tasks

# --- ПРОВЕРКА ---
if __name__ == "__main__":
    all_tasks = parse_config_file("jobs-cisco.txt", vendor="cisco")
    
    for task in all_tasks:
        print(f"Device: {task['ip']}")
        print(f"Commands: {task['cmds']}\n")
