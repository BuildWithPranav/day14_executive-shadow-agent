FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md /app/
COPY app /app/app
COPY data /app/data

RUN pip install --no-cache-dir uv \
    && uv pip install --system -e .

EXPOSE 8000

CMD ["python", "-m", "app.main"]
