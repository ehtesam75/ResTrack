from pathlib import Path
import os
import dj_database_url
import cloudinary
from dotenv import load_dotenv

load_dotenv()

# ======================
# Cloudinary SDK Config (for CloudinaryField.url to use HTTPS)
# ======================
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET'),
    secure=True,
)

# ======================
# Build paths inside the project
# ======================
BASE_DIR = Path(__file__).resolve().parent.parent

# ======================
# Core Security Settings
# ======================
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = ['restrack-system.onrender.com', 'restrack-app.onrender.com', 'restrack-web.vercel.app', 'localhost', '127.0.0.1']

# ======================
# Applications
# ======================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'marks',
    'cloudinary_storage',
    'cloudinary',
]

# ======================
# Middleware
# ======================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# ======================
# URLs
# ======================
ROOT_URLCONF = 'ResTrack.urls'

# ======================
# Templates
# ======================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# ======================
# WSGI
# ======================
WSGI_APPLICATION = 'ResTrack.wsgi.application'

# ======================
# Database
# ======================

DATABASE_URL = os.getenv("DATABASE_URL")
DATABASES = {
    # conn_max_age=0: close DB connection after every request so Neon can
    # sleep between cron hits instead of being kept awake by lingering conns.
    'default': dj_database_url.config(default=DATABASE_URL, conn_max_age=0)
}
if not DATABASE_URL:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }

# Enable connection health checks so stale connections are detected early
# (Django 4.1+). This avoids wasted queries on broken connections.
DATABASES['default']['CONN_HEALTH_CHECKS'] = True

# ======================
# Password Validation
# ======================
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# ======================
# Internationalization
# ======================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Dhaka'
USE_I18N = True
USE_TZ = True

# ======================
# Static Files
# ======================
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# ======================
# Media Files
# ======================
DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage' 
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': os.getenv('CLOUDINARY_CLOUD_NAME'),
    'API_KEY': os.getenv('CLOUDINARY_API_KEY'),
    'API_SECRET': os.getenv('CLOUDINARY_API_SECRET'),
    'SECURE': True,
}
# MEDIA_URL = '/media/'
# MEDIA_ROOT = BASE_DIR / 'media'


# ======================
# Authentication
# ======================
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'


# ======================
# Caching
# ======================
# Use local-memory cache to avoid repeated DB queries for the same data.
# This dramatically reduces DB load for GradeScale lookups, dashboard stats,
# leaderboards, and other frequently accessed data.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'restrack-cache',
        'TIMEOUT': 300,  # 5 minutes default TTL
    }
}

# ======================
# Misc
# ======================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ======================
# Logging
# ======================
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        'marks.notifications': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# ======================
# Web Push Notifications (VAPID)
# ======================
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_ADMIN_EMAIL = os.environ.get("VAPID_ADMIN_EMAIL", "admin@restrack.app")

# ======================
# Cron Job Security
# ======================
CRON_SECRET_TOKEN = os.environ.get("CRON_SECRET_TOKEN", "")
