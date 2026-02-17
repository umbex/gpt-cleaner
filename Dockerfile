FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY static /app/static
COPY rules /app/rules

ENV DATA_DIR=/app/data
ENV RULES_DIR=/app/rules
ENV DB_PATH=/app/data/app.db
ENV LOGGING_ENABLED=true
ENV AVAILABLE_MODELS=gpt-4o-mini,gpt-5.2,gpt-5.3

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
