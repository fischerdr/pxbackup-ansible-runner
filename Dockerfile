FROM python:3.11-slim

WORKDIR /app

# Install system dependencies and build tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    git=1:2.39.5-0+deb12u1 \
    ansible=7.7.0+dfsg-3+deb12u1 \
    gcc=4:12.2.0-3 \
    python3-dev=3.11.2-1+b1 \
    build-essential=12.9 \
    libffi-dev=3.4.4-1 \
    libssl-dev=3.0.15-1~deb12u1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/

# Create necessary directories
RUN mkdir -p instance playbooks runner

# Set environment variables
ENV FLASK_APP=app
ENV FLASK_ENV=development
ENV PYTHONPATH=/app

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "app:create_app()"]
