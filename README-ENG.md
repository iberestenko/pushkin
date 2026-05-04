# 🚀 Pushkin NetOps Engine

**Pushkin** is a high-performance, asynchronous network automation daemon designed for ISPs, Data Centers, and large-scale Enterprises. It moves away from slow, line-by-line configuration models to a high-speed **"Fire-and-Forget"** approach with **Eventual Consistency**.

[![Python](https://shields.io)](https://python.org)
[![FastAPI](https://shields.io)](https://tiangolo.com)
[![Redis](https://shields.io)](https://redis.io)
[![License](https://shields.io)](LICENSE)

## 🎯 The Core Philosophy: "Shoot First, Verify Later"
Traditional tools like Ansible or Netmiko wait for a device prompt (`prompt#`) after every single command. In a High-Latency or Highload environment, this is a bottleneck.

**Pushkin** changes the game:
1. **The Burst:** It "fires" a full payload of commands into the SSH channel instantly using non-blocking `select`.
2. **The Verification:** It doesn't wait for SSH output to confirm success. Instead, it triggers a background **Reconciliation Loop** via SNMP or Telemetry to verify the state.
3. **The Rollback:** If a pipeline fails, Pushkin uses pre-fire backups to restore the network state automatically.

## 🛠 Features

- **High-Speed Execution**: Non-blocking SSH firing with adaptive buffering.
- **Vendor Abstraction**: Multi-vendor support via **Jinja2 templates** stored in Redis.
- **VLAN Orchestration**: Automatic discovery, atomic booking, and "provisioning" across device chains.
- **Reliability**: 
    - **Dry Run**: Pre-deployment syntax and connectivity validation.
    - **Distributed Locks**: Redis-based locking prevents multiple workers from hitting the same IP.
    - **Smart Retries**: Tiered error handling (Network glitch vs. Auth failure).
- **Security**: RBAC (Role-Based Access Control) and local credential storage.
- **Monitoring**: Real-time Tailwind CSS Dashboard and Telegram notifications.

## 🏗 Architecture

- **API (FastAPI)**: Receives "Intents" (e.g., "Create VLAN 100 on Path A").
- **Broker (Redis)**: Manages task queues, device passports, and real-time locks.
- **Worker (Python/Paramiko)**: Independent processes that execute the actual SSH sessions.
- **nstat (Coming Soon)**: Integration with NetBox/nstat for source-of-truth topology.

## 🚀 Getting Started

### Prerequisites
- Docker & Docker Compose
- A Telegram Bot Token (optional for alerts)

### Quick Start
1. **Clone the repo:**
   ```bash
   git clone https://github.com
   cd pushkin
   ```

2. **Configure your environment:**
   Create a `.env` file based on the provided template:
   ```text
   TG_TOKEN=123456:ABC-DEF
   TG_CHAT_ID=987654321
   ```

3. **Launch the engine:**
   ```bash
   docker-compose up -d --build
   ```

4. **Access the UI:**
   Open `http://localhost:8000` to see the Pushkin Dashboard.

## 🛡 FAQ for Network Engineers

**Q: What if the SSH session drops mid-payload?**  
A: Pushkin captures the audit log via `select`. If the session drops, the task is marked as `failed`. Since we perform a **Pre-fire Backup**, you can trigger a 1-click restore to the original state.

**Q: Won't this overwhelm the CPU of older switches?**  
A: No. We use an adjustable `chunk_size` and `read_timeout`. You can define "Slow Profiles" in Redis for older devices to ensure they aren't flooded.

**Q: Is it safe for production?**  
A: Yes. With **Atomic Reservations** (SET NX) in Redis, Pushkin ensures no two workers ever fight over the same VLAN ID or the same Device VTY line.

## 🤝 Roadmap
- [ ] Full nstat (NetBox) API integration for auto-topology.
- [ ] L3 Gateway (SVI) auto-provisioning with IPAM.
- [ ] Streaming Telemetry support (gNMI) for sub-second verification.

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.

---
**Pushkin** — Speed of thought for your network.

