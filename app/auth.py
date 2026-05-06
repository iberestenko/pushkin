import os
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

# --- КОНФИГУРАЦИЯ (В продакшене вынеси в переменные окружения) ---
SECRET_KEY = os.getenv("SECRET_KEY", "SUPER_SECRET_PUSHKIN_KEY_CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Настройка контекста для хеширования паролей (bcrypt)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Указываем FastAPI, где искать токен в запросах
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверяет, совпадает ли введенный пароль с хешем в базе"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Создает безопасный хеш пароля"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    """Генерирует JWT токен с временем жизни"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

# --- ЛОГИКА АВТОРИЗАЦИИ ---

def authenticate_user(username, password):
    """
    Эмуляция проверки пользователя. 
    В реальном проекте здесь должен быть запрос к БД или LDAP.
    """
    # Для теста: логин "admin", пароль "admin"
    # Хеш получен через get_password_hash("admin")
    test_user_db = {
        "admin": {
            "username": "admin",
            "hashed_password": "$2b$12$14TkRzhw8UMnHqnVjP3ze.v1HCDlzYaomCWKbWnsO3u9zrBjUv2XS"
        }
    }
    
    user = test_user_db.get(username)
    if not user:
        return False
    if not verify_password(password, user["hashed_password"]):
        return False
    
    # Возвращаем объект пользователя (простой класс или словарь)
    from pydantic import BaseModel
    class User(BaseModel):
        username: str
    return User(username=username)

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    Dependency, которая защищает эндпоинты. 
    Если токен невалиден или просрочен — вернет 401 ошибку.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # Декодируем JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
        
    return username

