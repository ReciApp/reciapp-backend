import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-only-for-unit-tests")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
