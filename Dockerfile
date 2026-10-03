FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies (build-essential/curl for healthchecks or native wheels if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Set default port
ENV PORT=8080

# Expose port
EXPOSE $PORT

# Start application via gunicorn
CMD exec gunicorn app:app --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120
