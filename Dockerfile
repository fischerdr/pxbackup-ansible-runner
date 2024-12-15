FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git \
    ansible \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY migrations/ migrations/

# Create necessary directories
RUN mkdir -p instance playbooks runner

# Set environment variables
ENV FLASK_APP=app
ENV FLASK_ENV=development
ENV PYTHONPATH=/app

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "app:create_app()"]
