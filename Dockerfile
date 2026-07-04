FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VERSION=1.8.5
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
ENV POETRY_VIRTUALENVS_PATH=/opt/poetry-venvs
ENV POETRY_CACHE_DIR=/opt/poetry-cache

WORKDIR /app

RUN python -m pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir "poetry==$POETRY_VERSION"

COPY pyproject.toml poetry.lock README.md ./

RUN mkdir -p despamizer \
    && touch despamizer/__init__.py \
    && poetry install --only main --no-root --no-interaction --no-ansi

CMD ["poetry", "run", "python", "-m", "despamizer"]
