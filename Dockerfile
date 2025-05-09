FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Tesseract OCR and language data
    tesseract-ocr \
    tesseract-ocr-eng \
    # Poppler tools for pdf2image
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
    # For barcode scanning
    libzbar0 \
    # Clean up to reduce image size
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/4.00/tessdata

# Create and set working directory
WORKDIR /app

# Copy requirements file to leverage Docker caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the project files
COPY . /app/

# Create necessary directories if they don't exist
RUN mkdir -p /app/staticfiles /app/media

# Collect static files
RUN python manage.py collectstatic --noinput

# Run gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "orderCycleProject.wsgi:application"]