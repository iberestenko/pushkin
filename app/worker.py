import asyncio
import asyncssh
import time

class PushkinAsyncEngine:
    # Список стоп-слов для "предохранителя"
    STOP_WORDS = [
        "invalid input", "error:", "syntax error", 
        "incomplete command", "ambiguous command", "access denied"
    ]
    
    # Команды для экстренного прерывания и отката
    ROLLBACK_COMMANDS = ["\x03", "rollback", "undo", "exit"]

    def __init__(self, max_concurrent=500, redis_instance=None):
        # Семафор ограничивает количество ОДНОВРЕМЕННЫХ SSH-сессий
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.redis = redis_instance

    async def run_pushkin_task(self, device_cfg, job_id, quiet_period=2.0):
        """
        Индивидуальная корутина для одного устройства.
        """
        host = device_cfg['ip']
        port = device_cfg.get('port', 22)
        user = device_cfg['user']
        password = device_cfg['pw']
        commands = device_cfg['cmds']
        
        device_id = f"{host}:{port}"
        channel_name = f"pushkin:stream:{job_id}:{host}:{port}"
        
        if self.redis: await self.redis.set("pushkin:metrics:conn_errors", 0)
        async with self.semaphore:
            if self.redis: await self.redis.incr("pushkin:metrics:active_sessions")
            start_time = time.time()
            full_log = []
            failed_command = None
            error_detected = False
            conn_timeout = 15.0
            
            try:
                # 1. Подключение
                conn = await asyncio.wait_for(
                    asyncssh.connect(
                        host, port=port, username=user, password=password, 
                        known_hosts=None,
                        client_version='SSH-2.0-PushkinEngine',
                    ),
                    timeout=conn_timeout
                )

                async with conn:
                    
                    writer, reader, _ = await conn.open_session()
                    
                    # 2. ОТПРАВКА: Залп всех команд разом
                    payload = '\n'.join(commands) + '\n'
                    writer.write(payload)
                    await writer.drain()

                    # 3. ЧТЕНИЕ С МОНИТОРИНГОМ (Live Stream + Safety Switch)
                    try:
                        while True:
                            # Ждем данные (quiet_period — наш таймаут тишины)
                            chunk = await asyncio.wait_for(
                                reader.read(65535), 
                                timeout=quiet_period
                            )
                            if not chunk: break
                            
                            full_log.append(chunk)
                            
                            # Отправляем кусок лога в Redis для Live Stream трансляции
                            if self.redis:
                                await self.redis.publish(channel_name, chunk)
                            
                            # Проверка на ошибки
                            chunk_lower = chunk.lower()
                            if any(word in chunk_lower for word in self.STOP_WORDS):
                                error_detected = True
                                
                                # Определяем, на какой команде споткнулись
                                current_buffer = "".join(full_log)
                                for cmd in reversed(commands):
                                    if cmd in current_buffer:
                                        failed_command = cmd
                                        break
                                break # Выход из цикла чтения при ошибке
                                
                    except asyncio.TimeoutError:
                        # Тишина в эфире — нормальное завершение для Burst-метода
                        pass

                    # 4. ЛОГИКА ROLLBACK (если нашли ошибку)
                    if error_detected:
                        if self.redis: await self.redis.incr("pushkin:metrics:config_errors")
                        msg = f"\n[!] STOP-WORD DETECTED. Failed on: '{failed_command}'\n[!] STARTING ROLLBACK...\n"
                        full_log.append(msg)
                        if self.redis: await self.redis.publish(channel_name, msg)
                        
                        # Шлем команды отката
                        try:
                            writer.write('\n'.join(self.ROLLBACK_COMMANDS) + '\n')
                            await writer.drain()
                        except Exception as e:
                            return {
                                "id": device_id,
                                "status": f"error_when_rolling_back: {str(e)}",
                                "failed_on": failed_command,
                                "log": "".join(full_log),
                            }

                        try:
                            while True:
                                # Дочитываем финальный ответ после отката
                                final = await asyncio.wait_for(reader.read(65535), timeout=quiet_period)
                                full_log.append(final)
                                if self.redis: await self.redis.publish(channel_name, final)
                                if not final:
                                    break
                        except asyncio.TimeoutError:
                            pass

                execution_time = round(time.time() - start_time, 2)
                if not error_detected and self.redis:
                    await self.redis.incr("pushkin:metrics:total_processed")
                return {
                    "id": device_id,
                    "status": "error_rolled_back" if error_detected else "success",
                    "failed_on": failed_command,
                    "log": "".join(full_log),
                    "time": execution_time
                }

            except (asyncio.TimeoutError, Exception) as e:
                if isinstance(e, asyncio.TimeoutError):
                    err_msg = f"\n[!] CONNECTION ERROR: Connection timed out after {conn_timeout} seconds\n"
                    error_text = "TimeoutError"
                else:
                    err_msg = f"\n[!] CONNECTION ERROR: {str(e)}\n"
                    error_text = str(e)
                if self.redis: await self.redis.publish(channel_name, err_msg)
                if self.redis: await self.redis.incr("pushkin:metrics:conn_errors")
                return {
                    "id": device_id,
                    "status": f"connection_error: {err_msg}",
                    "error": error_text,
                    "log": None
                }
            finally:
                if self.redis: await self.redis.decr("pushkin:metrics:active_sessions")

    async def run_mass_config(self, device_list, job_id):
        """
        Запускает пачку устройств и собирает результаты.
        """
        tasks = [
            self.run_pushkin_task(d, job_id) 
            for d in device_list
        ]
        # Собираем всё через gather (выполнится за время самого долгого устройства)
        return await asyncio.gather(*tasks)

