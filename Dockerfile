FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Ensure apt works with PPAs and HTTPS
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

# Run Gunicorn server bound to all interfaces
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "orderCycleProject.wsgi:application"]
