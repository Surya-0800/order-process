FROM python:3.11:alpine

# Install system dependencies
RUN apt-get update && apt-get install -y \
    poppler-utils \
    tesseract-ocr \
    libgl1-mesa-glx \
    libsm6 \
    libxext6 \
    libxrender-dev

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy project files
COPY . .

# Expose port
EXPOSE 8000

# Command to run
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "orderCycleProject.wsgi"]