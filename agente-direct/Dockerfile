FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agente_direct ./agente_direct
COPY conhecimento ./conhecimento
EXPOSE 8000
CMD ["uvicorn", "agente_direct.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
