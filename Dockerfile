FROM python:3.12-slim

RUN pip install --no-cache-dir "uv>=0.8,<0.9"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/home/app/.cache/fastembed

RUN useradd --create-home --uid 1000 app
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
COPY .streamlit ./.streamlit
RUN uv sync --locked --no-dev

USER app
RUN mkdir -p "$FASTEMBED_CACHE_PATH"
EXPOSE 8000 8501

CMD ["uvicorn", "github_repo_chat.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
