import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://reciapp:reciapp@db:5432/reciapp")
SECRET_KEY: str = os.getenv("SECRET_KEY", "")
ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")

if not SECRET_KEY:
    raise ValueError("La variable de entorno SECRET_KEY no está definida")
