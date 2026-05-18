from app.transport.ssh import SSHTransport
from app.transport.telnet import TelnetTransport

TRANSPORTS = {
    "ssh":    SSHTransport,
    "telnet": TelnetTransport,
}

def get_transport(proto: str = "ssh"):
    cls = TRANSPORTS.get(proto)
    if cls is None:
        raise ValueError(f"Unknown protocol: '{proto}'. Available: {list(TRANSPORTS)}")
    return cls()