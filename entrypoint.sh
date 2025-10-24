#!/bin/bash

# Wait for PostgreSQL to be ready
if [ "$DATABASE" = "postgres" ]
then
    echo "Waiting for PostgreSQL..."
    
    while ! nc -z $DB_HOST $DB_PORT; do
      sleep 0.1
    done
    
    echo "PostgreSQL started"
fi

# Apply database migrations
echo "Running migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Add crontab jobs
echo "Adding crontab jobs..."
python manage.py crontab add

# Show registered cron jobs (for verification)
echo "Registered cron jobs:"
python manage.py crontab show

# Start cron daemon in background
echo "Starting cron daemon..."
service cron start

# Start Gunicorn
echo "Starting Gunicorn..."
exec gunicorn orderCycleProject.wsgi:application --bind 0.0.0.0:8000