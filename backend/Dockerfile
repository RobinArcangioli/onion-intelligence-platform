FROM python:3.12-slim@sha256:4840d514c583a4d3d8cad3940e68dee6f0f6f3635c12fcd0a3d74c21a5b93a54 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

FROM base AS wheel
COPY requirements-build.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-build.lock
COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip wheel --no-deps --no-build-isolation --wheel-dir /wheel .

FROM base AS runtime
COPY requirements-runtime.lock ./
COPY --from=wheel /wheel /wheel
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-runtime.lock \
 && python -m pip install --no-cache-dir --no-deps /wheel/*.whl \
 && python -m pip check \
 && useradd --system --uid 10001 --create-home oip
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
USER oip
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM runtime AS test
USER root
COPY tests ./tests
COPY requirements-test.lock ./
RUN python -m pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements-test.lock \
 && python -m pip check
USER oip
