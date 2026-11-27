FROM python:3.15-slim

LABEL org.opencontainers.image.source="https://github.com/Sette/telegram-exec-notifier" \
      org.opencontainers.image.description="Telegram bot that runs Claude, Codex and Kiro and relays their output"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TELEGRAM_NOTIFIER_HOST=0.0.0.0 \
    TELEGRAM_NOTIFIER_PORT=8765

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# The agent CLIs (claude, codex, kiro-cli) are NOT in the image: mount them and your
# home directory at runtime (see docker-compose.yml) and run as your own user.
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import socket; socket.create_connection(('127.0.0.1', 8765), 3).close()"

ENTRYPOINT ["telegram-exec-notifier"]
