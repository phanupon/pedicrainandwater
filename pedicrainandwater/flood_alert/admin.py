"""
Django admin configuration for flood alert system.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import Province, WeatherData, DamData, FloodPrediction, Alert, DataFetchLog

RISK_COLORS = {
    'SAFE': '#22c55e', 'LOW': '#eab308',
    'MODERATE': '#f97316', 'HIGH': '#ef4444', 'CRITICAL': '#7c3aed',
}


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ['name_th', 'name_en', 'region', 'latitude', 'longitude']
    search_fields = ['name_th', 'name_en']
    list_filter = ['region']


@admin.register(WeatherData)
class WeatherDataAdmin(admin.ModelAdmin):
    list_display = ['province', 'forecast_time', 'precipitation_mm', 'temperature_c', 'humidity_pct', 'source']
    list_filter = ['province', 'source']
    ordering = ['-forecast_time']
    date_hierarchy = 'forecast_time'


@admin.register(DamData)
class DamDataAdmin(admin.ModelAdmin):
    list_display = ['dam_name', 'rid_code', 'storage_percent_display', 'inflow_cms', 'outflow_cms', 'timestamp']
    list_filter = ['province']
    ordering = ['-timestamp']

    def storage_percent_display(self, obj):
        pct = obj.storage_percent
        if pct is None:
            return '-'
        color = '#ef4444' if pct >= 90 else '#f97316' if pct >= 75 else '#22c55e'
        return format_html(
            '<span style="color:{}; font-weight:bold;">{:.1f}%</span>',
            color, pct
        )
    storage_percent_display.short_description = '% น้ำ'


@admin.register(FloodPrediction)
class FloodPredictionAdmin(admin.ModelAdmin):
    list_display = ['province', 'risk_level_display', 'flood_probability', 'expected_rain_mm', 'dam_fill_pct', 'predicted_at']
    list_filter = ['risk_level', 'province']
    ordering = ['-predicted_at']

    def risk_level_display(self, obj):
        color = RISK_COLORS.get(obj.risk_level, '#6b7280')
        return format_html(
            '<span style="background:{}; color:white; padding:2px 8px; border-radius:4px;">{}</span>',
            color, obj.get_risk_level_display()
        )
    risk_level_display.short_description = 'ระดับความเสี่ยง'


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ['province', 'alert_type', 'title', 'is_active', 'created_at']
    list_filter = ['alert_type', 'is_active', 'province']
    ordering = ['-created_at']
    actions = ['mark_acknowledged']

    def mark_acknowledged(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_active=False, acknowledged_at=timezone.now())
    mark_acknowledged.short_description = 'รับทราบการแจ้งเตือน'


@admin.register(DataFetchLog)
class DataFetchLogAdmin(admin.ModelAdmin):
    list_display = ['source', 'status', 'records_fetched', 'duration_ms', 'fetched_at']
    list_filter = ['source', 'status']
    ordering = ['-fetched_at']
    readonly_fields = ['fetched_at']
