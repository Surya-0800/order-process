#!/bin/bash
set -e

echo "Starting migration to /mnt/data volume..."

# Ensure we're in the right directory
if [ ! -f "docker-compose.yml" ]; then
    echo "Error: docker-compose.yml not found in current directory"
    exit 1
fi

# Stop all containers
echo "Stopping containers..."
docker-compose down

# Create destination directories on data volume
echo "Creating directories on /mnt/data..."
sudo mkdir -p /mnt/data/postgresql
sudo mkdir -p /mnt/data/media
sudo mkdir -p /mnt/data/static

# Find and copy PostgreSQL data
echo "Copying PostgreSQL data..."
POSTGRES_VOLUME=$(docker volume inspect order-process_postgres_data -f '{{ .Mountpoint }}')
if [ -d "$POSTGRES_VOLUME" ]; then
    sudo cp -ar "$POSTGRES_VOLUME"/* /mnt/data/postgresql/
    echo "PostgreSQL data copied successfully"
else
    echo "Warning: PostgreSQL volume not found at $POSTGRES_VOLUME"
fi

# Copy media files if they exist
echo "Copying media files..."
MEDIA_VOLUME=$(docker volume inspect order-process_media_volume -f '{{ .Mountpoint }}' 2>/dev/null || echo "")
if [ -n "$MEDIA_VOLUME" ] && [ -d "$MEDIA_VOLUME" ]; then
    sudo cp -ar "$MEDIA_VOLUME"/* /mnt/data/media/
    echo "Media files copied successfully"
fi

# Copy static files if they exist
echo "Copying static files..."
STATIC_VOLUME=$(docker volume inspect order-process_static_volume -f '{{ .Mountpoint }}' 2>/dev/null || echo "")
if [ -n "$STATIC_VOLUME" ] && [ -d "$STATIC_VOLUME" ]; then
    sudo cp -ar "$STATIC_VOLUME"/* /mnt/data/static/
    echo "Static files copied successfully"
fi

# Set proper ownership (postgres user is typically UID 999 in postgres:14 image)
echo "Setting proper permissions..."
sudo chown -R 999:999 /mnt/data/postgresql
sudo chown -R 1000:1000 /mnt/data/media
sudo chown -R 1000:1000 /mnt/data/static

# Backup original docker-compose.yml
echo "Backing up docker-compose.yml..."
cp docker-compose.yml docker-compose.yml.backup