import json

# --- THE PUSHKIN DICTIONARY ---
# This dictionary maps "Abstract Actions" to specific CLI commands.
# We use Jinja2 syntax ({{ variable }}) for dynamic parameter injection.

DEFAULT_TEMPLATES = {
    "cisco": {
        "create_vlan": [
            "vlan {{ vlan_id }}",
            "name {{ vlan_name }}",
            "exit"
        ],
        "delete_vlan": [
            "no vlan {{ vlan_id }}"
        ],
        "tag_port": [
            "interface {{ port }}",
            "switchport trunk allowed vlan add {{ vlan_id }}"
        ],
        "untag_port": [
            "interface {{ port }}",
            "switchport mode access",
            "switchport access vlan {{ vlan_id }}",
            "no shutdown"
        ],
        "set_description": [
            "interface {{ port }}",
            "description PUSHKIN_PROVISIONED_{{ vlan_name }}"
        ],
        "set_snmp": [
            "snmp-server community {{ community }} {{ mode|default('RO') }}",
            "snmp-server contact Network_Team",
            "exit"
        ]
    },
    "huawei": {
        "create_vlan": [
            "vlan {{ vlan_id }}",
            "description {{ vlan_name }}",
            "quit"
        ],
        "delete_vlan": [
            "undo vlan {{ vlan_id }}"
        ],
        "tag_port": [
            "interface {{ port }}",
            "port link-type trunk",
            "port trunk allow-pass vlan {{ vlan_id }}"
        ],
        "untag_port": [
            "interface {{ port }}",
            "port link-type access",
            "port default vlan {{ vlan_id }}"
        ],
        "set_snmp": [
            "snmp-agent community {{ 'read' if mode == 'ro' else 'write' }} {{ community }}"
            "snmp-agent sys-info version all",
            "exit"
        ]
    },
    "eltex": {
        "config_mode": [
            "configure terminal"
        ],
        "create_vlan": [
            "vlan database",
            "vlan {{ vlan_id }}",
            "exit",
            "interface vlan {{ vlan_id }}",
            "name {{ vlan_name }}",
            "exit",
        ],
        "save_config": [
            "end",
            "write memory"
        ],
        "set_snmp": [
            "snmp-server server",
            "snmp-server community {{ community }} {{ mode|upper|default('RO') }}",
            "exit"
        ]
    },
    "dlink-old": {
        "set_snmp": [
            "enable snmp",
            "create snmp community {{ community }} view Default {{ mode|default('read_only') }}",
            "save"
        ]
    },
    #TODO: make proper snmp mode for all vendors
    "mikrotik": {
        "create_vlan": [
            "/interface vlan add name={{ vlan_name }} vlan-id={{ vlan_id }} interface=bridge"
        ],
        "set_snmp": [
            "/snmp community set [find name=public] name={{ community }} read-access={{ 'yes' if mode == 'ro' else 'no' }}",
            "/snmp set enabled=yes"
        ]
    }
}

# --- TODO: CORE TERMINATION SCENARIOS ---
# These are place-holders for the high-level logic we discussed for Core devices.
# Implementation will depend on the specific ISP architecture.

CORE_SERVICE_TODO = {
    "l3_gateway": [
        "interface Vlan {{ vlan_id }}",
        "ip address {{ gateway_ip }} {{ subnet_mask }}",
        "no shutdown"
    ],
    "vrf_isolation": [
        "interface Vlan {{ vlan_id }}",
        "vrf forwarding {{ vrf_name }}",
        "ip address {{ gateway_ip }} {{ subnet_mask }}"
    ],
    "dhcp_relay": [
        "interface Vlan {{ vlan_id }}",
        "ip helper-address {{ dhcp_server_ip }}"
    ],
    "vxlan_overlay": [
        "nve 1",
        "member vni {{ vni_id }} associate-vrf"
    ]
}

# --- NSTAT (NETBOX) MAPPING TODO ---
# When you connect Pushkin to your nstat source, use this structure
# to map nstat object attributes to Pushkin variables.

NSTAT_MAPPING = {
    "device_role_mapping": {
        "Access": "access_template",
        "Aggregation": "agg_template",
        "Core": "core_template"
    },
    "interface_mapping": {
        "Trunk": "tag_port",
        "Access": "untag_port"
    }
}

def get_template(vendor, action):
    """
    Helper to fetch template from local dict. 
    In the future, this will check Redis for custom user-defined overrides.
    """
    return DEFAULT_TEMPLATES.get(vendor.lower(), {}).get(action.lower())

