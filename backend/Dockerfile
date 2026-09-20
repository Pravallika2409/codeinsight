# CodeInsight AI backend image.
#
# Bundles every external tool the analyzers shell out to (see README
# "Installation" for the equivalent bare-metal setup): cppcheck (C++),
# a JDK for javac (Java), and Node.js for the standalone ESLint install
# used by javascript_analyzer.py. Also used, with a different CMD, for the
# Celery worker service in docker-compose.yml -- same image, same
# dependencies, since the worker runs the identical analysis pipeline.
FROM python:3.12-slim

# --- System tools the analyzers depend on ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    cppcheck \
    openjdk-21-jdk-headless \
    curl \
    gnupg \
    build-essential \
    libpq-dev \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- Python dependencies ---
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# --- Standalone ESLint install used by javascript_analyzer.py ---
COPY tools/js-lint/package.json tools/js-lint/package-lock.json* tools/js-lint/
RUN cd tools/js-lint && npm install --omit=dev

# --- Application code ---
COPY . .

# Runs as a non-root user (rule: "Use non-root users").
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Applies pending Alembic migrations, then starts the API server. The
# Celery worker service overrides this command in docker-compose.yml.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
