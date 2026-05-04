import json
import os
from typing import List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, Depends
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, validator
from redis import Redis
from rq import Queue

# Import our custom logic
from templates import DEFAULT_TEMPLATES
from worker import pushkin_fire, health_check_worker

app = FastAPI(title="Pushkin NetOps Control Plane")

# Initialize Redis Connection
# In Docker, 'redis' is the hostname defined in docker-compose.yml
redis_conn = Redis(host=os.getenv('REDIS_HOST', 'redis'), port=6379, decode_responses=False)
q = Queue(connection=redis_conn)

# --- MODELS ---

class DeviceRegister(BaseModel):
    ip: str
    username: str
    password: str
    vendor: str = "cisco"
    port: int = Field(default=22, ge=1, le=65535)
    chunk_size: int = 8192
    read_timeout: float = 0.1

class ConfigAction(BaseModel):
    ip: str
    action: str
    params: dict = {}
    send_notify: bool = False
    make_backup: bool = False
    safe_mode: bool = False  # If True, triggers Pre-fire backup

# --- API ENDPOINTS ---

@app.post("/devices/register")
async def register_device(dev: DeviceRegister):
    """Registers a network device passport in Redis storage."""
    redis_conn.hset(f"device:info:{dev.ip}", mapping=dev.dict())
    return {"status": "registered", "ip": dev.ip, "ssh_port": dev.port}

@app.get("/dashboard")
async def get_dashboard():
    """Aggregates data for the frontend monitoring table."""
    devices = []
    # scan_iter is safe for Highload (doesn't block Redis)
    for key in redis_conn.scan_iter("device:info:*"):
        ip = key.decode().split(":")[-1]
        info = redis_conn.hgetall(key)
        status = redis_conn.hgetall(f"device:status:{ip}")
        
        devices.append({
            "ip": ip,
            "vendor": info.get(b'vendor', b'cisco').decode(),
            "port": int(info.get(b'port', 22)),
            "status": {
                "icmp": status.get(b'icmp_up') == b'True',
                "ssh": status.get(b'ssh_up') == b'True',
                "last_check": status.get(b'last_check', b'Never').decode()
            }
        })
    return {"devices": devices}

@app.post("/push-abstract")
async def push_abstract(req: ConfigAction):
    """Translates intent (e.g. create_vlan) into vendor CLI and fires it."""
    # 1. Get device vendor and settings
    dev_info = redis_conn.hgetall(f"device:info:{req.ip}")
    if not dev_info:
        raise HTTPException(status_code=404, detail="Device not registered")
    
    vendor = dev_info.get(b'vendor', b'cisco').decode()
    
    # 2. Find template in DEFAULT_TEMPLATES (or TODO: fetch from Redis overrides)
    tpl_list = DEFAULT_TEMPLATES.get(vendor, {}).get(req.action)
    if not tpl_list:
        raise HTTPException(status_code=400, detail=f"Vendor {vendor} doesn't support {req.action}")

    # 3. Render commands using Jinja2
    from jinja2 import Template
    rendered_cmds = [Template(c).render(**req.params) for c in tpl_list]

    # 4. Enqueue task to Worker
    job = q.enqueue(
        pushkin_fire,
        req.ip,
        rendered_cmds,
        send_notify=req.send_notify,
        make_backup=req.make_backup,
        pre_backup=req.safe_mode
    )
    
    return {
        "status": "queued", 
        "job_id": job.get_id(), 
        "vendor": vendor,
        "commands": rendered_cmds
    }

@app.get("/vlan/allocate")
async def allocate_vlan(path_name: str, start_id: int = 100):
    """Finds and reserves the first free VLAN ID on a specific network path."""
    # Check if path exists in nstat/topology
    path_raw = redis_conn.get(f"topology:path:{path_name}")
    if not path_raw:
        raise HTTPException(status_code=404, detail="Topology path not found")
    
    # Simple atomic reservation loop
    for vlan_id in range(start_id, 4095):
        res_key = f"vlan_res:{path_name}:{vlan_id}"
        # SET NX EX: Only if not exists, expire in 5 mins
        if redis_conn.set(res_key, "reserved", nx=True, ex=300):
            return {
                "vlan_id": vlan_id, 
                "status": "reserved", 
                "path": path_name,
                "expires": "300s"
            }
            
    raise HTTPException(status_code=507, detail="IPAM: No free VLANs available in this range")

@app.get("/health-check/all")
async def trigger_mass_health_check():
    """Triggers background health checks for all registered devices."""
    count = 0
    for key in redis_conn.scan_iter("device:info:*"):
        ip = key.decode().split(":")[-1]
        q.enqueue(health_check_worker, ip)
        count += 1
    return {"status": "triggered", "jobs_count": count}

@app.get("/", response_class=HTMLResponse)
async def index():
    """Serves the Dashboard UI."""
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Pushkin UI file (index.html) is missing.</h1>"

# --- TODO: NSTAT INTEGRATION ---
@app.post("/topology/sync-nstat")
async def sync_nstat(path_name: str, nodes: List[dict]):
    """Endpoint for external nstat (NetBox) integration to push topology."""
    redis_conn.set(f"topology:path:{path_name}", json.dumps(nodes))
    return {"status": "topology_updated", "path": path_name}

