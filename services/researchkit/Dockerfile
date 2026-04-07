FROM python:3.11-slim AS base

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

COPY . .

EXPOSE 3020

CMD ["uvicorn", "researchkit.main:app", "--host", "0.0.0.0", "--port", "3020"]
