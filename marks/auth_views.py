from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .forms import TeacherSignupForm, LoginForm, StudentAccountForm
from .models import TeacherProfile, StudentProfile


def home(request):
    """Landing page for the application"""
    # If user is already logged in, redirect to dashboard
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'marks/home.html')


def teacher_signup(request):
    """Handle teacher registration"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TeacherSignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.first_name}! Your teacher account has been created successfully.')
            return redirect('dashboard')
        else:
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{error}')
    else:
        form = TeacherSignupForm()
    
    return render(request, 'marks/signup.html', {'form': form})


def user_login(request):
    """Handle user login (both teacher and student)"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            
            # Check user type for welcome message
            if hasattr(user, 'teacher_profile'):
                messages.success(request, f'Welcome back, {user.first_name or user.username}!')
            else:
                messages.success(request, f'Welcome back, {user.username}!')
            
            # Redirect to next URL if provided, otherwise dashboard
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Invalid username or password.')
    else:
        form = LoginForm()
    
    return render(request, 'marks/login.html', {'form': form})


def user_logout(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('home')


def is_teacher(user):
    """Check if user is a teacher"""
    return hasattr(user, 'teacher_profile')


def is_student(user):
    """Check if user is a student"""
    return hasattr(user, 'student_profile')


def get_user_type(user):
    """Get the type of user"""
    if hasattr(user, 'teacher_profile'):
        return 'teacher'
    elif hasattr(user, 'student_profile'):
        return 'student'
    return 'unknown'
