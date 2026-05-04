import paramiko
import select
import time
import json
import os
import socket
from datetime import datetime
from redis import Redis
from rq import get_current_job

# Initialize Redis connection
redis_conn = Redis(host=os.getenv('REDIS_HOST', 'redis'), port=6379, decode_responses=False)

# --- CUSTOM EXCEPTIONS ---
class DeviceLockedError(Exception):
    """Raised when a device is already being configured by another worker."""
    pass

class NetworkUnreachableError(Exception):
    """Raised for connection timeouts or SSH drops."""
    pass

# --- UTILS ---
def send_telegram_alert(message):
    """Helper to send alerts to the NOC Telegram channel."""
    token = os.getenv("TG_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not token or not chat_id:
        return
    import requests
    url = f"https://telegram.org{token}/sendMessage"
    try:
        requests.post(url, json={"chat_id": chat_id, "text": f"🚀 *Pushkin Alert*\n{message}", "parse_mode": "Markdown"}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def save_config(ip, config_text, prefix="POST"):
    """Saves the configuration to the backups folder."""
    os.makedirs(f"backups/{ip}", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backups/{ip}/{prefix}_{timestamp}.txt"
    with open(filename, "w") as f:
        f.write(config_text)
    return filename

# --- MAIN TASK ---
def pushkin_fire(device_ip, commands, chunk_size=8192, read_timeout=0.1, send_notify=False, make_backup=False, pre_backup=False):
    """
    Core engine: Fires a burst of commands into the SSH channel.
    """
    job = get_current_job()
    lock_key = f"lock:device:{device_ip}"

    # 1. ATOMIC LOCK: Prevent multiple workers from hitting the same IP
    if not redis_conn.set(lock_key, "busy", nx=True, ex=60):
        print(f"--- [LOCK] {device_ip} is busy. Retrying later...")
        raise DeviceLockedError(f"Target {device_ip} is locked")

    # 2. FETCH CREDENTIALS
    info_raw = redis_conn.hgetall(f"device:info:{device_ip}")
    if not info_raw:
        redis_conn.delete(lock_key)
        return {"status": "error", "reason": "No credentials in Redis"}
    
    info = {k.decode(): v.decode() for k, v in info_raw.items()}
    ssh_port = int(info.get('port', 22))

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        # 3. CONNECT
        client.connect(
            hostname=device_ip,
            port=ssh_port,
            username=info['username'],
            password=info['password'],
            timeout=10,
            look_for_keys=False
        )
        
        chan = client.invoke_shell()
        chan.setblocking(0)  # Non-blocking mode for select.select()

        # 4. PRE-FIRE BACKUP (Optional)
        if pre_backup:
            chan.send("terminal length 0\nshow running-config\n")
            # Wait for data using select
            pre_config = ""
            while True:
                r, _, _ = select.select([chan], [], [], 0.5)
                if r:
                    data = chan.recv(65535).decode('utf-8', errors='ignore')
                    if not data: break
                    pre_config += data
                else: break
            save_config(device_ip, pre_config, prefix="PRE")

        # 5. HIGH-SPEED BURST (The "Pushkin" Way)
        payload = "\n".join(commands) + "\n"
        payload_bytes = payload.encode('utf-8')
        
        offset = 0
        while offset < len(payload_bytes):
            # Check if socket is ready to write
            _, writable, _ = select.select([], [chan], [], 5.0)
            if writable:
                sent = chan.send(payload_bytes[offset:offset+chunk_size])
                offset += sent
            else:
                raise NetworkUnreachableError("Write timeout - device not accepting data")

        # 6. READ AUDIT LOG (And optional post-backup)
        if make_backup:
            chan.send("terminal length 0\nshow running-config\n")

        output = ""
        while True:
            readable, _, _ = select.select([chan], [], [], read_timeout)
            if readable:
                try:
                    data = chan.recv(65535).decode('utf-8', errors='ignore')
                    if not data: break
                    output += data
                except: break
            else:
                break # 0.1s of silence = done

        # 7. SUCCESS CALLBACKS
        if send_notify:
            send_telegram_alert(f"✅ *{device_ip}* configured successfully.\nCommands: {len(commands)}")

        return {"status": "success", "ip": device_ip, "log_sample": output[:500]}

    except paramiko.AuthenticationException:
        # FATAL: Don't retry on wrong passwords to avoid lockout
        return {"status": "failed", "reason": "Auth Error"}
    
    except (socket.timeout, paramiko.SSHException, NetworkUnreachableError) as e:
        # RETRY: Network glitch or device rebooting
        raise NetworkUnreachableError(f"Network error: {str(e)}")

    finally:
        client.close()
        redis_conn.delete(lock_key) # Always release the lock

def health_check_worker(device_ip):
    """Background health check: Ping + SSH Handshake."""
    import subprocess
    # 1. ICMP Check
    ping = subprocess.run(["ping", "-c", "1", "-W", "1", device_ip], stdout=subprocess.DEVNULL)
    status = {"last_check": datetime.now().isoformat(), "icmp_up": ping.returncode == 0, "ssh_up": False}
    
    # 2. SSH Check (if ICMP is up)
    if status["icmp_up"]:
        # Logic to try paramiko.connect() without commands
        pass

    redis_conn.hset(f"device:status:{device_ip}", mapping=status)

