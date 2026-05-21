import asyncio
import asyncssh
from app.transport.base import BaseTransport


class SSHTransport(BaseTransport):

    async def connect(self, host, port, user, password, **kwargs):
        conn = None
        try:
            # 1. Заворачиваем установку SSH-сессии и авторизацию
            conn = await asyncio.wait_for(
                asyncssh.connect(
                    host, port=port, username=user, password=password,
                    known_hosts=None, login_timeout=15,
                    client_version="SSH-2.0-PushkinEngine",
                ),
                timeout=20,
            )
            
            # 2. Открываем интерактивную сессию (псевдо-терминал shell)
            # Примечание: open_session возвращает (reader, writer, stderr)
            writer, reader, _ = await conn.open_session(encoding="utf-8")
            
            # Важно: сохраняем ссылку на conn внутри writer или reader, 
            # чтобы при закрытии сокета в BaseTransport закрывалось и всё SSH-соединение.
            writer._conn = conn 
            
            return reader, writer

        except asyncio.TimeoutError:
            if conn:
                conn.close()
            raise ConnectionError(f"SSH connection or session timed out to {host}:{port}")
            
        except (asyncssh.Error, OSError) as e:
            if conn:
                conn.close()
            raise ConnectionError(f"SSH authentication or network failed for {host}:{port}: {e}")
