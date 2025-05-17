FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Ensure apt works with PPAs and HTTPS
    curl\
    gnupg \
    software-properties-common \
    # OCR and PDF tools
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    # For PyMuPDF (fitz)
    libmupdf-dev \
    # For psycopg2
    libpq-dev \
    # Build tools
    build-essential \
    gcc \
    python3-dev \
    # Image processing libraries
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    libfreetype6-dev \
    # OpenCV dependencies
    libsm6 \
    libxext6 \
    libxrender-dev \
    libfontconfig1 \
    # Barcode scanning
    libzbar0 \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Tesseract data path environment variable
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Fallback: manually download eng.traineddata in case apt fails to include it
RUN if [ ! -f "$TESSDATA_PREFIX/eng.traineddata" ]; then \
        mkdir -p "$TESSDATA_PREFIX" && \
        curl -L -o "$TESSDATA_PREFIX/eng.traineddata" https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata; \
    fi

# Create app directory
WORKDIR /app

# Copy requirements first (for caching)
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Prepare runtime directories
RUN mkdir -p /app/staticfiles /app/media

# Collect static files (optional, if needed before startup)
RUN python manage.py collectstatic --noinput || true

# Create entrypoint script to run import and then start gunicorn
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Try to import master data if file exists\n\
if [ -f "/app/master_table.xlsx" ]; then\n\
    echo "Importing master data..."\n\
    python manage.py import_master_data /app/master_table.xlsx || echo "Import failed but continuing"\n\
fi\n\
\n\
# Execute the original command\n\
exec "$@"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Use entrypoint script
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "orderCycleProject.wsgi:application"]