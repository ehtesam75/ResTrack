#!/usr/bin/env bash
# Exit on error
set -o errexit

echo "Starting ResTrack build process..."

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "Running database migrations..."
python manage.py migrate

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --no-input

# Optional: Create admin user if needed (uncomment if required)
# echo "Creating admin user..."
# python manage.py create_admin

# Optional: Setup grades system (uncomment if required)
# echo "Setting up grading system..."
# python manage.py setup_grades

echo "Build completed successfully!"
echo "ResTrack is ready to deploy!"