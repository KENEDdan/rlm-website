# Multi-stage build: tailwind CSS -> python deps -> slim non-root runtime.

ARG PYTHON_IMAGE=python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df

# ---------------------------------------------------------------- 1. CSS (Tailwind standalone CLI, no Node)
FROM ${PYTHON_IMAGE} AS css
ARG TAILWIND_VERSION=v3.4.17
ARG TAILWIND_SHA256=7d24f7fa191d2193b78cd5f5a42a6093e14409521908529f42d80b11fde1f1d4
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /usr/local/bin/tailwindcss \
      "https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-linux-x64" \
    && echo "${TAILWIND_SHA256}  /usr/local/bin/tailwindcss" | sha256sum -c - \
    && chmod +x /usr/local/bin/tailwindcss
WORKDIR /src
# Templates and Python files are scanned for class names (see tailwind.config.js "content").
COPY . .
RUN mkdir -p /out && tailwindcss -c tailwind.config.js -i static/css/input.css -o /out/site.css --minify

# ---------------------------------------------------------------- 2. Python dependencies
FROM ${PYTHON_IMAGE} AS deps
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements/base.txt /tmp/base.txt
RUN pip install --require-hashes -r /tmp/base.txt

FROM deps AS deps-dev
COPY requirements/dev.txt /tmp/dev.txt
RUN pip install --require-hashes -r /tmp/dev.txt

# ---------------------------------------------------------------- 3. Runtime base
FROM ${PYTHON_IMAGE} AS runtime-base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    MEDIA_ROOT=/app/data/media
RUN apt-get update \
    && apt-get install -y --no-install-recommends libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app
WORKDIR /app

# ---------------------------------------------------------------- 4. Development image (dev deps, code mounted)
FROM runtime-base AS dev
COPY --from=deps-dev /opt/venv /opt/venv
COPY --from=css /usr/local/bin/tailwindcss /usr/local/bin/tailwindcss
COPY --chown=app:app . /app
RUN mkdir -p /app/data/media /app/data/private /app/staticfiles && chown -R app:app /app/data /app/staticfiles
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# ---------------------------------------------------------------- 5. Production image
FROM runtime-base AS prod
COPY --from=deps /opt/venv /opt/venv
COPY --chown=root:root . /app
COPY --from=css --chown=root:root /out/site.css /app/static/css/site.css
# collectstatic needs settings to import; throwaway values are used ONLY in this build step.
# pip is then removed: it is not needed at runtime (smaller attack surface, see docs/SECURITY_AUDIT.md).
# collectstatic honours FILE_UPLOAD_PERMISSIONS (0640, root-owned), so static files are made world-readable
# (still root-owned and read-only) or the non-root app user cannot serve them.
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only-not-a-secret \
    DATABASE_URL=sqlite:////tmp/build.sqlite3 \
    FIELD_ENCRYPTION_KEYS=AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA= \
    BLIND_INDEX_KEY=build-only \
    python manage.py collectstatic --noinput \
    && chmod -R a+rX,go-w /app/staticfiles \
    && python -m compileall -q /app \
    && /opt/venv/bin/python -m pip uninstall -y -q pip \
    && /usr/local/bin/python -m pip uninstall -y -q pip \
    && mkdir -p /app/data/media /app/data/private \
    && chown -R app:app /app/data \
    && chmod +x /app/docker/entrypoint.sh
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "/app/docker/healthcheck.py"]
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "/app/docker/gunicorn.conf.py"]
