# Quick Setup Script for Student Marks Tracking System
# Run this script to set up the entire application from scratch

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Student Marks Tracking System - Setup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Navigate to project directory
Set-Location D:\Code-repos\ResTrack

Write-Host "Step 1: Running migrations..." -ForegroundColor Yellow
python manage.py migrate

Write-Host "`nStep 2: Setting up grade scales..." -ForegroundColor Yellow
python manage.py setup_grades

Write-Host "`nStep 3: Creating admin user..." -ForegroundColor Yellow
python manage.py create_admin

Write-Host "`nStep 4: Loading sample data..." -ForegroundColor Yellow
python manage.py load_sample_data

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Setup Complete!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To start the server, run:" -ForegroundColor Cyan
Write-Host "  python manage.py runserver" -ForegroundColor White
Write-Host ""
Write-Host "Then visit:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8000/" -ForegroundColor White
Write-Host ""
Write-Host "Admin Panel:" -ForegroundColor Cyan
Write-Host "  http://127.0.0.1:8000/admin/" -ForegroundColor White
Write-Host "  Username: admin" -ForegroundColor White
Write-Host "  Password: admin" -ForegroundColor White
Write-Host ""
