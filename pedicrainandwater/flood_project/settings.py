"""
Django settings for flood_project.
ระบบทำนายและแจ้งเตือนน้ำท่วม-ฝนหนัก
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('SECRET_KEY', 'django-insecure-flood-alert-dev-key-change-in-production')

DEBUG = os.environ.get('DEBUG', 'True') == 'True'

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost 127.0.0.1 0.0.0.0').split()

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'django_celery_beat',
    'flood_alert',
]

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

ROOT_URLCONF = 'flood_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'flood_project.wsgi.application'
ASGI_APPLICATION = 'flood_project.asgi.application'

# Database - SQLite
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db' / 'flood_alert.db',
    }
}

# Channel Layers (Redis for WebSocket)
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels_redis.core.RedisChannelLayer',
        'CONFIG': {
            'hosts': [(
                os.environ.get('REDIS_HOST', 'redis'),
                int(os.environ.get('REDIS_PORT', 6379))
            )],
        },
    },
}

# Celery Configuration
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://redis:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://redis:6379/0')
CELERY_TIMEZONE = 'Asia/Bangkok'
CELERY_BEAT_SCHEDULER = 'django_celery_beat.schedulers:DatabaseScheduler'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ===== API Keys =====
# กรมอุตุนิยมวิทยา (TMD)
TMD_API_UID = os.environ.get('TMD_API_UID', '')
TMD_API_UKEY = os.environ.get('TMD_API_UKEY', '')
TMD_API_BASE = 'https://data.tmd.go.th/api/WeatherToday/V1/'

# GISTDA Flood API
GISTDA_API_KEY = os.environ.get('GISTDA_API_KEY', '')
GISTDA_FLOOD_API = 'https://api-gateway.gistda.or.th/v2/flood'

# กรมชลประทาน (RID) - Public API (no key needed)
RID_DAM_API = 'https://app.rid.go.th/reservoir/api/dam/public'

# Open-Meteo (Free, no key needed)
OPEN_METEO_API = 'https://api.open-meteo.com/v1/forecast'

# ===== Alert Thresholds =====
RAIN_HEAVY_THRESHOLD_MM = 35.0   # ≥35mm/hr = ฝนหนักมาก
RAIN_MODERATE_THRESHOLD_MM = 10.0  # ≥10mm/hr = ฝนปานกลาง
DAM_CRITICAL_PERCENT = 90.0      # อ่างเก็บน้ำ >90% = วิกฤต
DAM_WARNING_PERCENT = 75.0       # อ่างเก็บน้ำ >75% = เฝ้าระวัง

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'flood_alert': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
