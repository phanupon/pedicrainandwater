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
from django.core.cache import cache

from .models import Province, WeatherData, DamData, FloodPrediction, Alert, DataFetchLog, ObservedRain
from .services import fetch_thaiwater_waterlevel

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

    # Get latest observed rain for each province
    # Group by province_id and get the max timestamp
    latest_rain_subquery = ObservedRain.objects.values('province_id').annotate(max_time=Max('timestamp'))
    # A simpler way since dataset is small:
    observed_rains = {}
    for obs in ObservedRain.objects.filter(timestamp__gte=now - timedelta(hours=24)).order_by('province_id', '-timestamp'):
        if obs.province_id not in observed_rains:
            observed_rains[obs.province_id] = obs.rain_24h_mm

    for prov in provinces:
        pred = FloodPrediction.objects.filter(province=prov).order_by('-predicted_at').first()
        if pred:
            latest_preds.append({
                'province': prov,
                'prediction': pred,
                'color': RISK_COLORS.get(pred.risk_level, '#6b7280'),
                'observed_rain': observed_rains.get(prov.id, 0.0)
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

    # Critical Dams (Top 6 most full)
    recent_dams = DamData.objects.filter(
        timestamp__gte=now - timedelta(hours=24)
    ).order_by('-storage_percent', '-timestamp')
    
    seen_dams = set()
    critical_dams = []
    for d in recent_dams:
        if d.rid_code not in seen_dams:
            seen_dams.add(d.rid_code)
            critical_dams.append(d)
    critical_dams = critical_dams[:6]

    # System status
    last_fetch = DataFetchLog.objects.order_by('-fetched_at').first()

    # ThaiWater Water Level Data (Cached for 15 mins)
    waterlevel_data = cache.get('thaiwater_waterlevel')
    if not waterlevel_data:
        waterlevel_data = fetch_thaiwater_waterlevel()
        if waterlevel_data:
            cache.set('thaiwater_waterlevel', waterlevel_data, 60 * 15)

    wl_overflow = []
    wl_over_capacity = []
    wl_bkk_chao_phraya = []

    if waterlevel_data:
        # 1. สถานีที่น้ำล้นตลิ่งมากที่สุด
        overflow_stations = [s for s in waterlevel_data if s['diff_wl_bank'] is not None and s['diff_wl_bank'] > 0]
        wl_overflow = sorted(overflow_stations, key=lambda x: x['diff_wl_bank'], reverse=True)[:5]

        # 2. สถานีระดับน้ำที่เกินความจุลำน้ำสูงสุด (>100%)
        overcap_stations = [s for s in waterlevel_data if s['storage_percent'] is not None and s['storage_percent'] > 100]
        wl_over_capacity = sorted(overcap_stations, key=lambda x: x['storage_percent'], reverse=True)[:5]

        # 3. สถานีในกรุงเทพฯ และลุ่มเจ้าพระยาตอนล่าง
        bkk_cp_stations = [s for s in waterlevel_data if s['province'] == 'กรุงเทพมหานคร' or 'เจ้าพระยา' in s['basin']]
        # Sort by situation level or diff_wl_bank
        wl_bkk_chao_phraya = sorted(bkk_cp_stations, key=lambda x: (x['situation_level'] or 0), reverse=True)[:5]

    context = {
        'latest_preds': latest_preds,
        'active_alerts': active_alerts,
        'risk_counts': risk_counts,
        'critical_dams': critical_dams,
        'wl_overflow': wl_overflow,
        'wl_over_capacity': wl_over_capacity,
        'wl_bkk_chao_phraya': wl_bkk_chao_phraya,
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
    from django.conf import settings as django_settings

    fetch_logs = DataFetchLog.objects.order_by('-fetched_at')[:50]
    total_weather = WeatherData.objects.count()
    total_dams = DamData.objects.values('rid_code').distinct().count()
    total_predictions = FloodPrediction.objects.count()
    total_alerts = Alert.objects.count()

    # ตรวจสอบว่า API key ถูกตั้งค่าจริงหรือไม่
    api_status = {
        'tmd_configured': bool(getattr(django_settings, 'TMD_TOKEN', '')),
        'gistda_configured': bool(getattr(django_settings, 'GISTDA_API_KEY', '')),
    }

    context = {
        'fetch_logs': fetch_logs,
        'stats': {
            'weather': total_weather,
            'dams': total_dams,
            'predictions': total_predictions,
            'alerts': total_alerts,
        },
        'api_status': api_status,
    }
    return render(request, 'flood_alert/system_status.html', context)


def data_explorer(request, data_type):
    """
    หน้าแสดงข้อมูลดิบ (Explorer) สำหรับกดดูจาก stat cards
    data_type: 'weather', 'dams', 'predictions', 'alerts'
    """
    context = {'data_type': data_type, 'title': ''}
    
    if data_type == 'weather':
        context['title'] = 'ข้อมูลพยากรณ์อากาศล่าสุด'
        # Top 100 recent forecasts
        data = WeatherData.objects.select_related('province').order_by('-forecast_time')[:100]
        context['data_list'] = data
        
    elif data_type == 'dams':
        context['title'] = 'ข้อมูลเขื่อนและอ่างเก็บน้ำ'
        # Latest dams
        data = DamData.objects.order_by('-timestamp')[:50]
        context['data_list'] = data
        
    elif data_type == 'predictions':
        context['title'] = 'ผลการทำนายน้ำท่วมล่าสุด'
        data = FloodPrediction.objects.select_related('province').order_by('-predicted_at')[:100]
        context['data_list'] = data
        
    elif data_type == 'alerts':
        context['title'] = 'ประวัติการแจ้งเตือน'
        data = Alert.objects.select_related('province').order_by('-created_at')[:100]
        context['data_list'] = data
        
    else:
        # Invalid type
        pass

    return render(request, 'flood_alert/data_explorer.html', context)

def bkk_roads(request):
    """
    หน้าแสดงข้อมูล หลีกเลี่ยงถนนน้ำท่วม กทม.
    """
    # Mock data for flooded roads in Bangkok
    flooded_roads = [
        {
            'id': 1,
            'name': 'ถนนรัชดาภิเษก',
            'district': 'จตุจักร',
            'location_desc': 'หน้าศาลอาญา - แยกรัชโยธิน',
            'water_level': '20-30 ซม.',
            'status': 'รถเล็กผ่านไม่ได้',
            'trend': 'ทรงตัว',
            'last_update': '10 นาทีที่แล้ว',
            'lat': 13.820,
            'lng': 100.575
        },
        {
            'id': 2,
            'name': 'ถนนแจ้งวัฒนะ',
            'district': 'หลักสี่',
            'location_desc': 'หน้าศูนย์ราชการ',
            'water_level': '15-20 ซม.',
            'status': 'ชะลอตัว',
            'trend': 'ลดลง',
            'last_update': '15 นาทีที่แล้ว',
            'lat': 13.885,
            'lng': 100.565
        },
        {
            'id': 3,
            'name': 'ถนนวิภาวดีรังสิต',
            'district': 'ดอนเมือง',
            'location_desc': 'ฐานทัพอากาศ - อนุสรณ์สถาน',
            'water_level': '10-15 ซม.',
            'status': 'วิ่งได้เฉพาะเลนขวา',
            'trend': 'เพิ่มขึ้น',
            'last_update': '5 นาทีที่แล้ว',
            'lat': 13.935,
            'lng': 100.615
        }
    ]
    
    context = {
        'flooded_roads': flooded_roads,
    }
    return render(request, 'flood_alert/bkk_roads.html', context)


def monitoring_map(request):
    """หน้าเฝ้าระวัง: แผนที่ทั้งประเทศแสดงจุดตามความเสี่ยง"""
    now = timezone.now()

    provinces = Province.objects.all().order_by('name_th')

    # Get latest observed rain
    observed_rains = {}
    for obs in ObservedRain.objects.filter(timestamp__gte=now - timedelta(hours=24)).order_by('province_id', '-timestamp'):
        if obs.province_id not in observed_rains:
            observed_rains[obs.province_id] = obs.rain_24h_mm

    # Build province data with predictions
    province_markers = []
    risk_counts = {level: 0 for level in ['SAFE', 'LOW', 'MODERATE', 'HIGH', 'CRITICAL']}

    for prov in provinces:
        pred = FloodPrediction.objects.filter(province=prov).order_by('-predicted_at').first()
        if pred:
            risk_counts[pred.risk_level] += 1
            province_markers.append({
                'id': prov.id,
                'name_th': prov.name_th,
                'name_en': prov.name_en,
                'lat': prov.latitude,
                'lng': prov.longitude,
                'region': prov.region,
                'risk_level': pred.risk_level,
                'risk_display': pred.get_risk_level_display(),
                'flood_probability': pred.flood_probability,
                'expected_rain_mm': float(pred.expected_rain_mm),
                'dam_fill_pct': float(pred.dam_fill_pct) if pred.dam_fill_pct else 0,
                'color': RISK_COLORS.get(pred.risk_level, '#6b7280'),
                'observed_rain': float(observed_rains.get(prov.id, 0.0)),
            })

    # Dam data for sidebar
    recent_dams = DamData.objects.filter(
        timestamp__gte=now - timedelta(hours=24)
    ).order_by('-storage_percent', '-timestamp')

    seen_dams = set()
    top_dams = []
    for d in recent_dams:
        if d.rid_code not in seen_dams:
            seen_dams.add(d.rid_code)
            top_dams.append(d)
    top_dams = top_dams[:10]

    # Active alerts
    active_alerts = Alert.objects.filter(
        is_active=True,
        created_at__gte=now - timedelta(hours=24)
    ).select_related('province').order_by('-created_at')[:10]

    context = {
        'province_markers_json': json.dumps(province_markers, ensure_ascii=False),
        'province_markers': province_markers,
        'risk_counts': risk_counts,
        'total_provinces': provinces.count(),
        'top_dams': top_dams,
        'active_alerts': active_alerts,
        'now': now,
    }
    return render(request, 'flood_alert/monitoring_map.html', context)


def satellite_map(request):
    """หน้าข้อมูลดาวเทียมและเรดาร์ (GISTDA / RainViewer)"""
    from django.conf import settings as django_settings
    gistda_key = getattr(django_settings, 'GISTDA_API_KEY', '')
    return render(request, 'flood_alert/satellite_map.html', {'gistda_key': gistda_key})


