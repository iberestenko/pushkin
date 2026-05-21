import asyncio
import time
from abc import ABC, abstractmethod


class BaseTransport(ABC):

    STOP_WORDS = [
        "invalid input", "error:", "syntax error",
        "incomplete command", "ambiguous command", "access denied", "not found"
    ]
    ROLLBACK_COMMANDS = ["\x03", "rollback", "undo", "exit"]

    @abstractmethod
    async def connect(self, host: str, port: int, user: str, password: str, **kwargs):
        """Возвращает (reader, writer) — абстракция над транспортом."""
        ...

    @abstractmethod
    def make_payload(self, commands: list[str]) -> str:
        """SSH шлёт '\n', Telnet '\r\n'."""
        ...

    async def _wait_for_prompt(self, reader, full_log, timeout=5.0):
        """Служебный метод ожидания приглашения командной строки (Prompt)."""
        try:
            while True:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=timeout)
                if not chunk:
                    break
                full_log.append(chunk)
                if any(p in chunk for p in (">", "#")):
                    break
        except asyncio.TimeoutError:
            pass

    async def run_task(self, device_cfg, job_id, semaphore, redis=None, quiet_period=2.0):
        host      = device_cfg["ip"]
        port      = device_cfg.get("port", 22)
        user      = device_cfg["user"]
        password  = device_cfg["pw"]
        commands  = device_cfg["cmds"]
        
        # Новый параметр конфигурации: "burst" или "step" (по умолчанию "step")
        mode      = device_cfg.get("mode", "step") 
        
        connect_params = {
            "login_timeout": device_cfg.get("login_timeout", 1.5),
            "pass_timeout":  device_cfg.get("pass_timeout", 0.7),
            "blind_login":   device_cfg.get("blind_login", False),
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

                # ======================================================================
                # РЕЖИМ 1: COMMAND BURST (Быстрая отправка) / FAST (отправка без ответа)
                # ======================================================================
                if mode == "burst" or mode == "fast":
                    await pub(f"\n[Pushkin] Running in BURST/FAST mode (Fast sending, no rollback/No output)...\n")
                    
                    send_start = time.time()
                    
                    chunk_size  = device_cfg.get("chunk_size", 0)
                    chunk_delay = device_cfg.get("chunk_delay", 0.05)  # 50 мс по умолчанию

                    if chunk_size > 0 and len(commands) > chunk_size:
                        # Опция включена: нарезаем пачку на куски
                        await pub(f"[Pushkin] Chunking enabled: sending by {chunk_size} commands with {chunk_delay}s delay\n")
                        
                        for i in range(0, len(commands), chunk_size):
                            current_chunk = commands[i : i + chunk_size]
                            writer.write(self.make_payload(current_chunk))
                            await writer.drain()
                            
                            # Делаем паузу между кусками, кроме самого последнего
                            if i + chunk_size < len(commands):
                                await asyncio.sleep(chunk_delay)
                    else:
                        # Опция отключена: шлем всё одним махом
                        writer.write(self.make_payload(commands))
                        await writer.drain()

                    send_time = round((time.time() - send_start) * 1000, 3) # в миллисекундах
                    await pub(f"\n[Pushkin] Pure send time: {send_time} ms\n")

                    # ЕСЛИ РЕЖИМ FAST_BURST — уходим МГНОВЕННО, не читая ответы
                    if mode == "fast":
                        await pub("\n[Pushkin] Fast Burst mode: Closing connection immediately without reading response.\n")
                        writer.close() # Запускаем плавное закрытие сокета
                        if hasattr(writer, "wait_closed"):
                            await writer.wait_closed() # Ждем, чтобы буфер гарантированно ушел в систему
                        return {
                            "id":        device_id,
                            "status":    "fast_fired",
                            "failed_on": None,
                            "log":       "".join(full_log),
                            "time":      round(time.time() - start_time, 2),
                        }

                    try:
                        while True:
                            chunk = await asyncio.wait_for(reader.read(65535), timeout=quiet_period)
                            if not chunk:
                                break
                            await pub(chunk)
                    except asyncio.TimeoutError:
                        await pub("\n[Pushkin] Burst execution finished (silence timeout).\n")

                # ==========================================
                # РЕЖИМ 2: STEP-BY-STEP (Контроль и откат)
                # ==========================================
                else:
                    await pub(f"\n[Pushkin] Running in STEP mode (Netmiko style with rollback)... \n")

                    send_start = time.time()

                    for cmd in commands:
                        await pub(f"\n[Pushkin] Executing: {cmd}\n")

                        writer.write(self.make_payload([cmd]))
                        await writer.drain()

                        cmd_buffer_list = []
                        await self._wait_for_prompt(reader, cmd_buffer_list, timeout=quiet_period)
                        
                        # Переносим прочитанное в общий лог и склеиваем для проверки на стоп-слова
                        cmd_buffer = "".join(cmd_buffer_list)
                        await pub(cmd_buffer)

                        if any(w in cmd_buffer.lower() for w in self.STOP_WORDS):
                            error_detected = True
                            failed_command = cmd
                            break  # Немедленно прерываем цикл, не шлем следующие команды

                    send_time = round((time.time() - send_start) * 1000, 3) # в миллисекундах
                    await pub(f"\n[Pushkin] Pure send time: {send_time} ms\n")

                # ==========================================
                # ЛОГИКА ОТКАТА (Только для пошагового режима)
                # ==========================================
                if mode == "step" and error_detected:
                    if redis:
                        await redis.incr("pushkin:metrics:config_errors")
                    await pub(
                        f"\n[!] STOP-WORD DETECTED. Failed on: '{failed_command}'\n"
                        f"[!] STARTING ROLLBACK...\n"
                    )
                    try:
                        for rollback_cmd in self.ROLLBACK_COMMANDS:
                            await pub(f"\n[!] Sending rollback command: {rollback_cmd}\n")
                            writer.write(self.make_payload([rollback_cmd]))
                            await writer.drain()
                            
                            # Ждем prompt для текущей команды отката
                            await self._wait_for_prompt(reader, full_log, timeout=1.0)
                    except asyncio.TimeoutError:
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
