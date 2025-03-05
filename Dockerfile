# Use slim-bullseye instead of slim for better stability with ffmpeg
FROM python:3.12-slim-bullseye AS builder

# Install build dependencies and ffmpeg with all required libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.12-slim-bullseye

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Install ffmpeg and required libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set up environment
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Create necessary directories and copy application files
COPY bot.py .
COPY commands ./commands
COPY utils ./utils

# Run as non-root user for security
RUN useradd -m appuser && \
    chown -R appuser:appuser /app
USER appuser

CMD ["python3", "bot.py"]