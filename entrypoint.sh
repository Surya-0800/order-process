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
python manage.py migrate

# Collect static files
python manage.py collectstatic --no-input

# Start Gunicorn
exec gunicorn orderCycleProject.wsgi:application --bind 0.0.0.0:8000