import uuid
import asyncio
from typing import List
from datetime import timedelta

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

import redis.asyncio as redis
from worker import PushkinAsyncEngine  # Импорт нашего движка
from auth import (
    authenticate_user, create_access_token, get_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES, SECRET_KEY, ALGORITHM
)

app = FastAPI(title="Pushkin Engine API")

# Настройки Redis
REDIS_HOST = "redis_db" # Имя сервиса в docker-compose
redis_client = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

# Инициализация движка (лимит 500 одновременных сессий)
engine = PushkinAsyncEngine(max_concurrent=500, redis_instance=redis_client)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- МАРШРУТЫ АВТОРИЗАЦИИ ---

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}

# --- ОСНОВНОЙ API ---

@app.post("/push", status_code=status.HTTP_202_ACCEPTED)
async def start_mass_config(
    device_list: List[dict], 
    background_tasks: BackgroundTasks,
    job_id: str = None,  # Добавляем необязательный параметр
    current_user: str = Depends(get_current_user)
):
    """
    Принимает список устройств и команд. 
    Мгновенно возвращает job_id и запускает процесс в фоне.
    """
    final_job_id = job_id or str(uuid.uuid4())
    
    # Сохраняем начальный статус в Redis
    await redis_client.set(f"pushkin:job:{final_job_id}", "running", ex=86400)

    # Фоновая функция для выполнения задач и сохранения результата
    async def run_and_save():
        results = await engine.run_mass_config(device_list, job_id=final_job_id)
        # Сохраняем финальный JSON с результатами
        import json
        await redis_client.set(
            f"pushkin:job:{final_job_id}:results", 
            json.dumps(results), 
            ex=86400
        )
        await redis_client.set(f"pushkin:job:{final_job_id}", "completed", ex=86400)

    background_tasks.add_task(run_and_save)
    
    return {
        "job_id": final_job_id,
        "status": "accepted",
        "message": f"Processing {len(device_list)} devices",
        "started_by": current_user
    }

@app.get("/status/{job_id}")
async def get_job_status(job_id: str, current_user: str = Depends(get_current_user)):
    """Получение текущего статуса и результатов задачи"""
    job_status = await redis_client.get(f"pushkin:job:{job_id}")
    if not job_status:
        raise HTTPException(status_code=404, detail="Job not found")
    
    results = await redis_client.get(f"pushkin:job:{job_id}:results")
    
    import json
    return {
        "job_id": job_id,
        "status": job_status,
        "data": json.loads(results) if results else None
    }

# --- WEBSOCKET LIVE STREAM ---

@app.websocket("/ws/stream/{job_id}/{host}/{port}")
async def websocket_endpoint(websocket: WebSocket, job_id: str, host: str, port: int):
    """Трансляция логов конкретного устройства в реальном времени"""
    await websocket.accept()
    
    channel_name = f"pushkin:stream:{job_id}:{host}:{port}"
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel_name)
    
    try:
        async for message in pubsub.listen():
            if message['type'] == 'message':
                await websocket.send_text(message['data'])
    except WebSocketDisconnect:
        print(f"Client disconnected from stream {channel_name}")
    finally:
        await pubsub.unsubscribe(channel_name)

# --- СТАТИКА (ИНТЕРФЕЙС ТЕРМИНАЛА) ---

@app.get("/", response_class=HTMLResponse)
async def get_terminal():
    with open("index.html", "r") as f:
        return f.read()

