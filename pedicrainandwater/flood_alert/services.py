"""
Services for fetching data from external APIs.
ดึงข้อมูลจาก Open-Meteo, กรมชลประทาน, GISTDA, กรมอุตุ
"""
import logging
import time
import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('flood_alert')


def _get(url, params=None, headers=None, timeout=15):
    """HTTP GET with timeout and error handling."""
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.Timeout:
        logger.error(f'Timeout fetching: {url}')
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f'Request error for {url}: {e}')
        raise


def fetch_open_meteo_weather(province):
    """
    ดึงข้อมูลพยากรณ์ฝนจาก Open-Meteo (ฟรี ไม่ต้องมี API key)
    Returns list of hourly forecast dicts.
    """
    params = {
        'latitude': province.latitude,
        'longitude': province.longitude,
        'hourly': 'precipitation,temperature_2m,relative_humidity_2m,wind_speed_10m,cloud_cover',
        'forecast_days': 3,
        'timezone': 'Asia/Bangkok',
    }
    data = _get(settings.OPEN_METEO_API, params=params)

    hourly = data.get('hourly', {})
    times = hourly.get('time', [])
    precip = hourly.get('precipitation', [])
    temp = hourly.get('temperature_2m', [])
    humidity = hourly.get('relative_humidity_2m', [])
    wind = hourly.get('wind_speed_10m', [])
    cloud = hourly.get('cloud_cover', [])

    results = []
    for i, t in enumerate(times):
        results.append({
            'forecast_time': t,
            'precipitation_mm': precip[i] if i < len(precip) else 0.0,
            'temperature_c': temp[i] if i < len(temp) else None,
            'humidity_pct': humidity[i] if i < len(humidity) else None,
            'wind_speed_kmh': wind[i] if i < len(wind) else None,
            'cloud_cover_pct': cloud[i] if i < len(cloud) else None,
            'source': 'open_meteo',
        })
    return results


def fetch_rid_dam_data():
    """
    ดึงข้อมูลอ่างเก็บน้ำจากกรมชลประทาน (Public API ไม่ต้อง key)
    Returns list of dam data dicts.
    """
    data = _get(settings.RID_DAM_API)

    # RID API may return list directly or nested
    if isinstance(data, list):
        dams = data
    elif isinstance(data, dict):
        dams = data.get('dams', data.get('data', data.get('result', [])))
    else:
        dams = []

    results = []
    for dam in dams:
        # Normalize various field name conventions the API may use
        results.append({
            'rid_code': str(dam.get('id', dam.get('dam_id', dam.get('code', '')))),
            'dam_name': dam.get('name', dam.get('dam_name', dam.get('dam_name_th', ''))),
            'capacity_mcm': _to_float(dam.get('max_storage', dam.get('capacity', dam.get('max_storage_mcm')))),
            'volume_mcm': _to_float(dam.get('dam_storage', dam.get('storage', dam.get('current_storage')))),
            'storage_percent': _to_float(dam.get('dam_storage_percent', dam.get('percent', dam.get('storage_percent')))),
            'inflow_cms': _to_float(dam.get('inflow', dam.get('inflow_rate', dam.get('inflow_cms')))),
            'outflow_cms': _to_float(dam.get('released', dam.get('outflow', dam.get('outflow_cms')))),
        })
    return results


def fetch_tmd_weather(province):
    """
    ดึงข้อมูลจากกรมอุตุนิยมวิทยา (ต้องมี uid/ukey)
    Falls back to empty list if not configured.
    """
    uid = settings.TMD_API_UID
    ukey = settings.TMD_API_UKEY

    if not uid or not ukey:
        logger.warning('TMD API credentials not configured, skipping.')
        return []

    params = {
        'uid': uid,
        'ukey': ukey,
        'province': province.name_en,
        'format': 'json',
    }
    try:
        data = _get(settings.TMD_API_BASE, params=params)
        # Parse TMD response format
        return _parse_tmd_response(data, province)
    except Exception as e:
        logger.warning(f'TMD fetch failed for {province}: {e}')
        return []


def fetch_gistda_flood(lat, lon, radius_km=50):
    """
    ดึงข้อมูลพื้นที่น้ำท่วมจาก GISTDA (ต้องมี API key)
    Falls back gracefully if not configured.
    """
    api_key = settings.GISTDA_API_KEY
    if not api_key:
        logger.warning('GISTDA API key not configured, skipping.')
        return {'flooded': False, 'flood_area_km2': 0}

    headers = {'Authorization': f'Bearer {api_key}'}
    params = {
        'lat': lat,
        'lon': lon,
        'radius': radius_km,
        'period': '1d',
    }
    try:
        data = _get(settings.GISTDA_FLOOD_API, params=params, headers=headers)
        return {
            'flooded': data.get('has_flood', False),
            'flood_area_km2': data.get('flood_area_km2', 0),
            'flood_level': data.get('level', 'none'),
        }
    except Exception as e:
        logger.warning(f'GISTDA fetch failed: {e}')
        return {'flooded': False, 'flood_area_km2': 0}


def _to_float(val):
    """Safely convert to float."""
    try:
        return float(val) if val is not None else None
    except (ValueError, TypeError):
        return None


def _parse_tmd_response(data, province):
    """Parse TMD API response into standardized format."""
    results = []
    # TMD may return nested structure - handle common patterns
    forecasts = data.get('WeatherForecast', data.get('forecasts', data.get('data', [])))
    if isinstance(forecasts, dict):
        forecasts = [forecasts]
    for f in forecasts[:24]:  # Max 24 hours
        results.append({
            'forecast_time': f.get('time', f.get('datetime', '')),
            'precipitation_mm': _to_float(f.get('rainfall', f.get('rain', 0))) or 0.0,
            'temperature_c': _to_float(f.get('temp', f.get('temperature'))),
            'humidity_pct': _to_float(f.get('humidity', f.get('rh'))),
            'source': 'tmd',
        })
    return results
