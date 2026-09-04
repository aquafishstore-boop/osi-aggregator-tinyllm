FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY prompts ./prompts

RUN pip install --no-cache-dir -e .

RUN mkdir -p /data/snapshots /data/reports

VOLUME ["/data"]

CMD ["python", "-m", "osi_sandbox.worker"]