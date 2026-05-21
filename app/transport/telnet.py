import asyncio
import telnetlib3
from app.transport.base import BaseTransport


class TelnetTransport(BaseTransport):
    async def connect(self, host, port, user, password, 
                      login_timeout, pass_timeout, blind_login, **kwargs):
        try:
            reader, writer = await asyncio.wait_for(
                telnetlib3.open_connection(host, port, encoding="utf-8"),
                timeout=15,
            )
        except asyncio.TimeoutError:
            raise ConnectionError(f"Telnet connection timed out to {host}:{port} (15s exceeded)")
        except (OSError, ConnectionError) as e:
            raise ConnectionError(f"Failed to establish network connection to {host}:{port}: {e}")
        try:
            if blind_login:
                await self._blind_login(reader, writer, user, password, login_timeout, pass_timeout)
            else:
                await self._login(reader, writer, user, password)
        except Exception as e:
            writer.close()  # Гарантированно закрываем сокет при провале логина
            raise ConnectionError(f"Telnet authentication failed: {e}")
        return reader, writer

    async def _blind_login(self, reader, writer, user, password, login_timeout, pass_timeout):
        await asyncio.sleep(login_timeout)
        writer.write(user + "\r\n")
        await asyncio.sleep(pass_timeout)
        writer.write(password + "\r\n")

    async def _login(self, reader, writer, user, password):
        buf = ""
        deadline = asyncio.get_event_loop().time() + 15
        while asyncio.get_event_loop().time() < deadline:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=10.0)
            except asyncio.TimeoutError:
                raise TimeoutError("Timeout waiting for login prompt")
            if not chunk: 
                raise ConnectionResetError("Device closed connection during login")
            buf += chunk
            low_buf = buf.lower()

            if "incorrect" in low_buf or "bad" in low_buf:
                raise Exception("Incorrect credentials")
            elif "#" in buf or ">" in buf or "$" in buf:
                return

            if "username:" in low_buf or "login:" in low_buf:
                writer.write(user + "\r\n")
                buf = ""
            elif "password:" in low_buf:
                writer.write(password + "\r\n")
                buf = ""
            
        raise TimeoutError("Login deadline exceeded without finding prompt")
    
    def make_payload(self, commands):
        return "\r\n".join(commands) + "\r\n"