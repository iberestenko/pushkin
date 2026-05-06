import asyncio
import asyncssh
import random
import argparse

class MockSwitch(asyncssh.SSHServer):
    def connection_made(self, conn):
        print(f"[*] TCP connection established: {conn.get_extra_info('peername')}")

    def begin_auth(self, username):
        print(f"[*] Auth attempt for user: {username}")
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return True

async def handle_client(process):
    """
    ВАЖНО: AsyncSSH передает один аргумент - объект SSHServerProcess
    """
    print("[*] SSH Session started, entering handle_client")
    
    try:
        process.stdout.write("\r\nWelcome to Pushkin Mock Switch\r\n")
        process.stdout.write("switch> ")
        
        # Основной цикл
        async for line in process.stdin:
            cmd = line.strip()
            if not cmd: continue
            
            print(f"  [Command received]: {cmd}")
            
            # Имитируем работу
            await asyncio.sleep(0.1)
            
            if cmd == "conf t":
                process.stdout.write("switch(config)# ")
            elif cmd == "end" or cmd == "exit":
                process.stdout.write("switch# ")
            # Эмуляция таблицы интерфейсов (Cisco-style)
            elif cmd == "show ip interface brief":
                table = (
                    "\r\nInterface              IP-Address      OK? Method Status                Protocol\r\n"
                    "GigabitEthernet0/0     192.168.1.1     YES NVRAM  up                    up      \r\n"
                    "GigabitEthernet0/1     unassigned      YES unset  up                    up      \r\n"
                    "GigabitEthernet0/2     10.0.0.5        YES manual up                    down    \r\n"
                    "GigabitEthernet0/3     unassigned      YES unset  administratively down down    \r\n"
                    "Loopback0              1.1.1.1         YES manual up                    up      \r\n"
                    "Loopback100            10.100.100.1    YES manual up                    up      \r\n"
                )
                process.stdout.write(table)
                process.stdout.write("switch# ")
            else:
                process.stdout.write(f"OK: {cmd}\r\n")
                process.stdout.write("switch# ")

    except Exception as e:
        print(f"[!] CRASH in handle_client: {e}")
    finally:
        print("[*] Closing session")
        process.exit(0)

async def run_server(port):
    server_key = asyncssh.generate_private_key('ssh-rsa')
    
    # Прямая передача класса и функции
    await asyncssh.create_server(
        MockSwitch, 
        host='', 
        port=port, 
        server_host_keys=[server_key],
        process_factory=handle_client
    )
    print(f"[+] Mock Switch listening on port {port}")

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run_server(22)) # В контейнере всегда 22
    loop.run_forever()

