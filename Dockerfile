ARG BUN_VERSION=1.3.14
ARG PYTHON_VERSION=3.13-slim

FROM oven/bun:${BUN_VERSION} AS bun
FROM python:${PYTHON_VERSION}
ARG OMP_VERSION=18.6.0
ENV BUN_INSTALL=/opt/bun \
    PATH=/opt/venv/bin:/opt/bun/bin:${PATH} \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
COPY --from=bun /usr/local/bin/bun /usr/local/bin/bun
COPY --from=bun /usr/local/bin/bunx /usr/local/bin/bunx
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*
RUN bun add --global "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" \
    && omp --version
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN python -m pip install --no-cache-dir uv \
    && uv sync --frozen --no-dev --no-install-project
RUN useradd --create-home --uid 1000 agent \
    && mkdir -p /work/current /shared /home/agent/.omp \
    && chown -R agent:agent /work /shared /home/agent
COPY --chown=agent:agent agent_service /app/agent_service
COPY --chown=agent:agent functions /app/functions
COPY --chown=agent:agent settings.py /app/settings.py
USER agent
CMD ["uvicorn", "agent_service.worker_api:app", "--host", "0.0.0.0", "--port", "8000"]
