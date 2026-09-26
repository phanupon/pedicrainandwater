"""
URL configuration for flood_project.
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('flood_alert.urls')),
]
