from jinja2 import Template
from .templates import get_template

def render_pushkin_template(vendor, action, params):
    # Получаем список команд из твоего templates.py
    commands_list = get_template(vendor, action)
    if not commands_list:
        return []
        
    rendered_commands = []
    for cmd in commands_list:
        # Рендерим каждую строку, подставляя переменные (vlan_id, port и т.д.)
        t = Template(cmd)
        rendered_commands.append(t.render(**params))
        
    return rendered_commands
