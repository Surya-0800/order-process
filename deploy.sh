#!/bin/bash
# Simple deployment script for Docker setup

set -e  # Exit on error

echo "Starting deployment process..."

# Check if Docker and Docker Compose are installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories if they don't exist
echo "Creating necessary directories..."
mkdir -p logs
mkdir -p media
mkdir -p staticfiles
mkdir -p nginx

# Check if .env file exists
if [ ! -f .env ]; then
    echo "Creating .env file..."
    cat > .env << EOF
# Django settings
DJANGO_SECRET_KEY=$(openssl rand -hex 32)
DEBUG=False

# Database settings
POSTGRES_DB=orderProcess
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Allowed hosts
ALLOWED_HOSTS=localhost,127.0.0.1,your-domain.com
EOF
    echo "Created .env file with a generated secret key"
else
    echo ".env file already exists"
fi

# Create logs directory for Django logs
mkdir -p logs

# Check if any containers are already running
if docker-compose ps | grep -q "Up"; then
    echo "Stopping existing containers..."
    docker-compose down
fi

# Build and start the containers
echo "Building and starting containers..."
docker-compose build
docker-compose up -d

# Wait for the database to be ready
echo "Waiting for database to be ready..."
sleep 10

# Run migrations
echo "Running database migrations..."
docker-compose exec web python manage.py migrate

# Collect static files
echo "Collecting static files..."
docker-compose exec web python manage.py collectstatic --no-input

# Check if PDF processing dependencies are correctly installed
echo "Checking PDF processing dependencies..."
docker-compose exec web python check_pdf_deps.py

# Show container status
echo "Container status:"
docker-compose ps

# Show logs of the web container
echo "Web container logs:"
docker-compose logs --tail=20 web

echo "Deployment completed successfully!"
echo "Your application should now be running at http://localhost"
echo ""
echo "To create a superuser, run:"
echo "docker-compose exec web python manage.py createsuperuser"