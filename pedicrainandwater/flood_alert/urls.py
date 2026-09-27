"""
URL patterns for flood_alert app.
"""
from django.urls import path
from . import views

app_name = 'flood_alert'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('province/<int:province_id>/', views.province_detail, name='province_detail'),
    path('status/', views.system_status, name='system_status'),
    path('explore/<str:data_type>/', views.data_explorer, name='data_explorer'),
    path('bkk-roads/', views.bkk_roads, name='bkk_roads'),
    # JSON API endpoints
    path('api/alerts/', views.api_alerts, name='api_alerts'),
    path('api/predictions/', views.api_predictions, name='api_predictions'),
    path('api/weather/<int:province_id>/', views.api_weather, name='api_weather'),
    path('api/dams/', views.api_dam_status, name='api_dam_status'),
]
