FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# OpenShift corre el contenedor con un UID arbitrario del namespace.
# El directorio debe ser escribible por cualquier UID del grupo root (GID 0).
RUN mkdir -p uploads/evidencias \
    && chmod -R g+rwx /app \
    && chown -R 1001:0 /app

USER 1001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
