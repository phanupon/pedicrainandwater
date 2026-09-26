"""
Django views for flood alert dashboard.
"""
import json
import logging
from datetime import timedelta

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.utils import timezone
from django.db.models import Avg, Max, Count

from .models import Province, WeatherData, DamData, FloodPrediction, Alert, DataFetchLog

logger = logging.getLogger('flood_alert')

RISK_COLORS = {
    'SAFE': '#22c55e',
    'LOW': '#eab308',
    'MODERATE': '#f97316',
    'HIGH': '#ef4444',
    'CRITICAL': '#7c3aed',
}


def dashboard(request):
    """หน้าหลัก: แผงควบคุมระบบแจ้งเตือนน้ำท่วม"""
    now = timezone.now()

    # Latest predictions per province
    latest_preds = []
    provinces = Province.objects.all().order_by('name_th')

    for prov in provinces:
        pred = FloodPrediction.objects.filter(province=prov).order_by('-predicted_at').first()
        if pred:
            latest_preds.append({
                'province': prov,
                'prediction': pred,
                'color': RISK_COLORS.get(pred.risk_level, '#6b7280'),
            })

    # Active alerts (last 24h)
    active_alerts = Alert.objects.filter(
        is_active=True,
        created_at__gte=now - timedelta(hours=24)
    ).select_related('province').order_by('-created_at')[:20]

    # Risk summary
    risk_counts = {level: 0 for level in ['SAFE', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL']}
    for item in latest_preds:
        risk_counts[item['prediction'].risk_level] += 1

    # System status
    last_fetch = DataFetchLog.objects.order_by('-fetched_at').first()

    context = {
        'latest_preds': latest_preds,
        'active_alerts': active_alerts,
        'risk_counts': risk_counts,
        'total_provinces': provinces.count(),
        'last_fetch': last_fetch,
        'now': now,
    }
    return render(request, 'flood_alert/dashboard.html', context)


def province_detail(request, province_id):
    """รายละเอียดจังหวัด: ข้อมูลพยากรณ์และประวัติ"""
    province = get_object_or_404(Province, pk=province_id)
    now = timezone.now()

    # Weather forecast next 48h
    forecasts = WeatherData.objects.filter(
        province=province,
        forecast_time__gte=now,
        forecast_time__lte=now + timedelta(hours=48),
    ).order_by('forecast_time')

    # Last 5 predictions
    predictions = FloodPrediction.objects.filter(province=province).order_by('-predicted_at')[:10]

    # Latest dam data (any dam for context)
    latest_dam = DamData.objects.order_by('-timestamp').first()

    # Alert history for this province
    alerts = Alert.objects.filter(province=province).order_by('-created_at')[:10]

    # Prepare chart data
    chart_times = [f.forecast_time.strftime('%d/%m %H:%M') for f in forecasts]
    chart_rain = [f.precipitation_mm for f in forecasts]
    chart_humidity = [f.humidity_pct or 0 for f in forecasts]

    context = {
        'province': province,
        'forecasts': forecasts[:24],
        'predictions': predictions,
        'latest_dam': latest_dam,
        'alerts': alerts,
        'chart_times': json.dumps(chart_times),
        'chart_rain': json.dumps(chart_rain),
        'chart_humidity': json.dumps(chart_humidity),
        'latest_pred': predictions.first(),
        'risk_color': RISK_COLORS.get(predictions.first().risk_level if predictions else 'SAFE', '#22c55e'),
    }
    return render(request, 'flood_alert/province_detail.html', context)


@require_GET
def api_alerts(request):
    """API endpoint: รายการแจ้งเตือนล่าสุด (JSON)"""
    now = timezone.now()
    alerts = Alert.objects.filter(
        is_active=True,
        created_at__gte=now - timedelta(hours=24),
    ).select_related('province').order_by('-created_at')[:50]

    data = [{
        'id': a.id,
        'province_id': a.province_id,
        'province': a.province.name_th,
        'alert_type': a.alert_type,
        'title': a.title,
        'message': a.message,
        'created_at': a.created_at.isoformat(),
    } for a in alerts]
    return JsonResponse({'alerts': data, 'count': len(data)})


@require_GET
def api_predictions(request):
    """API endpoint: ผลทำนายล่าสุดแต่ละจังหวัด (JSON)"""
    provinces = Province.objects.all()
    results = []
    for prov in provinces:
        pred = FloodPrediction.objects.filter(province=prov).order_by('-predicted_at').first()
        if pred:
            results.append({
                'province_id': prov.id,
                'province_th': prov.name_th,
                'province_en': prov.name_en,
                'latitude': prov.latitude,
                'longitude': prov.longitude,
                'risk_level': pred.risk_level,
                'flood_probability': pred.flood_probability,
                'expected_rain_mm': pred.expected_rain_mm,
                'dam_fill_pct': pred.dam_fill_pct,
                'predicted_at': pred.predicted_at.isoformat(),
                'color': RISK_COLORS.get(pred.risk_level, '#6b7280'),
            })
    return JsonResponse({'predictions': results})


@require_GET
def api_weather(request, province_id):
    """API endpoint: ข้อมูลพยากรณ์อากาศรายชั่วโมง (JSON)"""
    province = get_object_or_404(Province, pk=province_id)
    now = timezone.now()
    forecasts = WeatherData.objects.filter(
        province=province,
        forecast_time__gte=now,
        forecast_time__lte=now + timedelta(hours=72),
    ).order_by('forecast_time')

    data = [{
        'time': f.forecast_time.isoformat(),
        'precipitation_mm': f.precipitation_mm,
        'temperature_c': f.temperature_c,
        'humidity_pct': f.humidity_pct,
        'wind_speed_kmh': f.wind_speed_kmh,
        'cloud_cover_pct': f.cloud_cover_pct,
    } for f in forecasts]
    return JsonResponse({'province': province.name_th, 'forecasts': data})


@require_GET
def api_dam_status(request):
    """API endpoint: สถานะอ่างเก็บน้ำล่าสุด (JSON)"""
    now = timezone.now()
    dams = DamData.objects.filter(
        timestamp__gte=now - timedelta(hours=6)
    ).order_by('dam_name', '-timestamp')

    seen = set()
    data = []
    for d in dams:
        if d.rid_code not in seen:
            seen.add(d.rid_code)
            data.append({
                'rid_code': d.rid_code,
                'dam_name': d.dam_name,
                'storage_percent': d.storage_percent,
                'volume_mcm': d.volume_mcm,
                'inflow_cms': d.inflow_cms,
                'outflow_cms': d.outflow_cms,
                'timestamp': d.timestamp.isoformat(),
            })
    return JsonResponse({'dams': data, 'count': len(data)})


def system_status(request):
    """หน้าแสดงสถานะระบบ"""
    fetch_logs = DataFetchLog.objects.order_by('-fetched_at')[:50]
    total_weather = WeatherData.objects.count()
    total_dams = DamData.objects.values('rid_code').distinct().count()
    total_predictions = FloodPrediction.objects.count()
    total_alerts = Alert.objects.count()

    context = {
        'fetch_logs': fetch_logs,
        'stats': {
            'weather': total_weather,
            'dams': total_dams,
            'predictions': total_predictions,
            'alerts': total_alerts,
        }
    }
    return render(request, 'flood_alert/system_status.html', context)
