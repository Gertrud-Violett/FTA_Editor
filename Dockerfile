FROM python:3.9-slim

LABEL maintainer="FTA/ETA Editor"
LABEL description="Fault Tree and Event Tree Analysis Editor"
LABEL version="2.2.2"
LABEL updated="2025-11-06"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    graphviz \
    python3-tk \
    x11-apps \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/
COPY docs/ ./docs/

# Create output directory
RUN mkdir -p /app/output

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV DISPLAY=:0

# Default command
CMD ["python", "src/FTA_Editor_UI.py"]
