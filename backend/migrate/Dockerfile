FROM python:3.12-slim

WORKDIR /app

COPY requirements-migrate.txt .
RUN pip install --no-cache-dir -r requirements-migrate.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY shared ./shared

CMD ["alembic", "upgrade", "head"]
