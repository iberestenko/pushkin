import asyncio
import asyncssh
from app.transport.base import BaseTransport


class SSHTransport(BaseTransport):

    async def connect(self, host, port, user, password, **kwargs):
        # login_timeout, pass_timeout, blind_login - for telnet only, we just need a signature here
        conn = await asyncio.wait_for(
            asyncssh.connect(
                host, port=port, username=user, password=password,
                known_hosts=None, login_timeout=15,
                client_version="SSH-2.0-PushkinEngine",
            ),
            timeout=20,
        )
        writer, reader, _ = await conn.open_session(encoding="utf-8")
        return reader, writer

    def make_payload(self, commands):
        return "\n".join(commands) + "\n"