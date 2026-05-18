import asyncio
import time
from abc import ABC, abstractmethod


class BaseTransport(ABC):

    STOP_WORDS = [
        "invalid input", "error:", "syntax error",
        "incomplete command", "ambiguous command", "access denied"
    ]
    ROLLBACK_COMMANDS = ["\x03", "rollback", "undo", "exit"]

    @abstractmethod
    async def connect(self, host: str, port: int, user: str, password: str, **kwargs):
        """
        Возвращает (reader, writer) — абстракция над транспортом.
        SSH и Telnet реализуют по-своему.
        """
        ...

    @abstractmethod
    def make_payload(self, commands: list[str]) -> str:
        """SSH шлёт '\n', Telnet '\r\n'."""
        ...

    async def run_task(self, device_cfg, job_id, semaphore, redis=None, quiet_period=2.0):
        host      = device_cfg["ip"]
        port      = device_cfg.get("port", 22)
        user      = device_cfg["user"]
        password  = device_cfg["pw"]
        commands  = device_cfg["cmds"]
        connect_params = {
            "login_timeout": device_cfg.get("login_timeout", 1.5),
            "pass_timeout":  device_cfg.get("pass_timeout", 0.7),
            "blind_login":   device_cfg.get("blind_login", True),
        }
        device_id = f"{host}:{port}"
        channel   = f"pushkin:stream:{job_id}:{host}:{port}"

        if redis:
            await redis.set("pushkin:metrics:conn_errors", 0)

        async with semaphore:
            if redis:
                await redis.incr("pushkin:metrics:active_sessions")

            start_time     = time.time()
            full_log       = []
            failed_command = None
            error_detected = False

            async def pub(msg):
                full_log.append(msg)
                if redis:
                    await redis.publish(channel, msg)

            try:
                reader, writer = await self.connect(host, port, user, password, **connect_params)

                # Command Burst
                writer.write(self.make_payload(commands))
                if hasattr(writer, "drain"):
                    await writer.drain()

                # Silence Timeout + Safety Switch
                try:
                    while True:
                        chunk = await asyncio.wait_for(
                            reader.read(65535), timeout=quiet_period
                        )
                        if not chunk:
                            break
                        await pub(chunk)

                        if any(w in chunk.lower() for w in self.STOP_WORDS):
                            error_detected = True
                            buf = "".join(full_log)
                            for cmd in reversed(commands):
                                if cmd in buf:
                                    failed_command = cmd
                                    break
                            break
                except asyncio.TimeoutError:
                    pass

                # Rollback
                if error_detected:
                    if redis:
                        await redis.incr("pushkin:metrics:config_errors")
                    await pub(
                        f"\n[!] STOP-WORD DETECTED. Failed on: '{failed_command}'\n"
                        f"[!] STARTING ROLLBACK...\n"
                    )
                    try:
                        writer.write(self.make_payload(self.ROLLBACK_COMMANDS))
                        if hasattr(writer, "drain"):
                            await writer.drain()
                        while True:
                            final = await asyncio.wait_for(
                                reader.read(65535), timeout=quiet_period
                            )
                            if not final:
                                break
                            await pub(final)
                    except asyncio.TimeoutError:
                        # Устройство просто замолчало после отправки rollback — это успех отката
                        await pub("\n[!] Rollback finished (silence timeout).\n")
                    except Exception as e:
                        return {
                            "id": device_id, "status": f"error_when_rolling_back: {e}",
                            "failed_on": failed_command, "log": "".join(full_log),
                        }

                execution_time = round(time.time() - start_time, 2)
                if not error_detected and redis:
                    await redis.incr("pushkin:metrics:total_processed")

                return {
                    "id":        device_id,
                    "status":    "error_rolled_back" if error_detected else "success",
                    "failed_on": failed_command,
                    "log":       "".join(full_log),
                    "time":      execution_time,
                }

            except Exception as e:
                err_msg = f"\n[!] CONNECTION ERROR: {str(e)}\n"
                if redis:
                    await redis.publish(channel, err_msg)
                    await redis.incr("pushkin:metrics:conn_errors")
                return {
                    "id": device_id, "status": f"connection_error: {err_msg}",
                    "error": str(e), "log": None,
                }

            finally:
                if redis:
                    await redis.decr("pushkin:metrics:active_sessions")