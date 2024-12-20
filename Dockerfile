FROM fedora:39

LABEL maintainer="Codeium Engineering Team"
LABEL description="Production image for pxbkup-clstradmin - PX-Backup Cluster Administration Service"

# Install system dependencies
RUN dnf update -y && \
    dnf install -y \
    python3.9 \
    python3-pip \
    python3-devel \
    gcc \
    git \
    ansible \
    postgresql-devel \
    openssl-devel \
    libffi-devel \
    && dnf clean all \
    && rm -rf /var/cache/dnf/*

# Create non-root user
RUN useradd -m -s /bin/bash pxbackup

# Create directories
RUN mkdir -p /app /app/instance /app/playbooks /runner \
    && chown -R pxbackup:pxbackup /app /runner

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY migrations/ migrations/
COPY alembic.ini .

# Set proper permissions
RUN chown -R pxbackup:pxbackup /app

# Switch to non-root user
USER pxbackup

# Set Python path and environment
ENV PYTHONPATH=/app
ENV FLASK_APP=app
ENV FLASK_ENV=production
ENV PROMETHEUS_MULTIPROC_DIR=/tmp
ENV APP_NAME=pxbkup-clstradmin

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Use gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--threads", "2", "--worker-class", "gthread", "--worker-tmp-dir", "/dev/shm", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]
