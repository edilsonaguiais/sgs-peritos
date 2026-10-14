FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY agente_direct ./agente_direct
COPY modelos ./modelos
COPY exemplos ./exemplos
EXPOSE 8000
CMD ["python", "-m", "agente_direct", "iniciar"]
