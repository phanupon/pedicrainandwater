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
    ดึงข้อมูลอ่างเก็บน้ำจาก ThaiWater (35 เขื่อนขนาดใหญ่)
    Returns list of dam data dicts.
    """
    try:
        url = 'https://api-v3.thaiwater.net/api/v1/thaiwater30/public/thailand_main'
        data = _get(url)
        dams = data.get('dam', {}).get('data', {}).get('data', [])
        
        results = []
        for d in dams:
            dam_info = d.get('dam', {})
            results.append({
                'rid_code': str(dam_info.get('id', '')),
                'dam_name': dam_info.get('dam_name', {}).get('th', ''),
                'capacity_mcm': _to_float(dam_info.get('normal_storage')),
                'volume_mcm': _to_float(d.get('dam_storage')),
                'storage_percent': _to_float(d.get('dam_storage_percent')),
                'inflow_cms': _to_float(d.get('dam_inflow')),
                'outflow_cms': _to_float(d.get('dam_released')),
            })
        return results
    except Exception as e:
        logger.warning(f'ThaiWater dam fetch failed: {e}')
        return []


def fetch_tmd_weather(province):
    """
    ดึงข้อมูลพยากรณ์อากาศจากกรมอุตุนิยมวิทยา NWP API
    ใช้ OAuth Bearer Token ใน Authorization Header
    Docs: http://data.tmd.go.th/nwpapi/doc
    """
    token = settings.TMD_TOKEN
    if not token:
        logger.warning('TMD_TOKEN not configured, skipping TMD fetch.')
        return []

    headers = {
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json',
    }
    params = {
        'lat': province.latitude,
        'lon': province.longitude,
        'fields': 'tc,rh,rain,ws10m,wd10m,psfc',  # อุณหภูมิ,ความชื้น,ฝน,ลม
        'duration': 24,  # 24 ชั่วโมง
    }

    try:
        data = _get(settings.TMD_NWP_API_BASE, params=params, headers=headers)
        return _parse_tmd_nwp_response(data)
    except Exception as e:
        logger.warning(f'TMD NWP fetch failed for {province}: {e}')
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


def _parse_tmd_nwp_response(data: dict) -> list:
    """
    แปลง JSON จาก TMD NWP API เป็น list รูปแบบมาตรฐาน

    TMD NWP API Response format:
    {
      "fcst_datetime": [...],
      "tc": [...],      # อุณหภูมิ (°C)
      "rh": [...],      # ความชื้นสัมพัทธ์ (%)
      "rain": [...],    # ฝนสะสม (mm)
      "ws10m": [...],   # ความเร็วลม (m/s)
    }
    """
    results = []

    # Handle both possible response structures
    forecast = data.get('WeatherForecast', data.get('data', data))
    if isinstance(forecast, dict):
        # Flat array format
        times = forecast.get('fcst_datetime', [])
        rain = forecast.get('rain', [])
        tc = forecast.get('tc', [])
        rh = forecast.get('rh', [])
        ws = forecast.get('ws10m', [])

        for i, t in enumerate(times):
            ws_ms = _to_float(ws[i] if i < len(ws) else None)
            results.append({
                'forecast_time': t,
                'precipitation_mm': _to_float(rain[i] if i < len(rain) else 0) or 0.0,
                'temperature_c': _to_float(tc[i] if i < len(tc) else None),
                'humidity_pct': _to_float(rh[i] if i < len(rh) else None),
                'wind_speed_kmh': round(ws_ms * 3.6, 1) if ws_ms else None,  # m/s → km/h
                'source': 'tmd',
            })
    elif isinstance(forecast, list):
        # List of objects format
        for item in forecast:
            ws_ms = _to_float(item.get('ws10m'))
            results.append({
                'forecast_time': item.get('fcst_datetime', item.get('time', '')),
                'precipitation_mm': _to_float(item.get('rain', 0)) or 0.0,
                'temperature_c': _to_float(item.get('tc')),
                'humidity_pct': _to_float(item.get('rh')),
                'wind_speed_kmh': round(ws_ms * 3.6, 1) if ws_ms else None,
                'source': 'tmd',
            })

    logger.debug(f'TMD NWP parsed {len(results)} hourly records')
    return results

def fetch_thaiwater_rain():
    """
    ดึงข้อมูลฝนสะสม 24 ชม. ล่าสุดจากสถานี ThaiWater ทั่วประเทศ
    จัดกลุ่มโดยหาค่าเฉลี่ยฝนหรือค่าสูงสุดของแต่ละจังหวัด
    Returns a dict mapping province_name_th to max rain_24h_mm
    """
    try:
        data = _get(settings.THAIWATER_RAIN_API)
        stations = data.get('data', [])
        
        # Aggregate max rain per province
        province_rain = {}
        for st in stations:
            # API structure: st['geocode']['province_name']['th']
            geocode = st.get('geocode', {})
            province_name = geocode.get('province_name', {}).get('th')
            rain_24h = _to_float(st.get('rain_24h'))
            
            if province_name and rain_24h is not None:
                # Remove "จังหวัด" if present in the name to match our DB
                province_name = province_name.replace('จังหวัด', '').strip()
                
                # Keep max rain for the province
                if province_name not in province_rain or rain_24h > province_rain[province_name]:
                    province_rain[province_name] = rain_24h
                    
        return province_rain
    except Exception as e:
        logger.warning(f'ThaiWater fetch failed: {e}')
        return {}


def fetch_thaiwater_waterlevel():
    """
    ดึงข้อมูลระดับน้ำจากสถานีโทรมาตร (ThaiWater)
    Returns list of dicts with station water level data
    """
    try:
        url = 'https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load'
        data = _get(url)
        stations = data.get('waterlevel_data', {}).get('data', [])
        
        results = []
        for st in stations:
            station_info = st.get('station', {})
            geocode = st.get('geocode', {})
            basin = st.get('basin', {})
            
            diff_wl = _to_float(st.get('diff_wl_bank'))
            is_overflow = st.get('diff_wl_bank_text') == 'ล้นตลิ่ง (ม.)'
            if is_overflow and diff_wl is not None:
                # If overflow, it means it's above the bank
                pass
            elif diff_wl is not None:
                # If not overflow, usually means it's below bank (negative or just positive distance to bank)
                # API usually gives positive number for distance below bank too, but text says 'ต่ำกว่าตลิ่ง (ม.)'
                if 'ต่ำกว่า' in (st.get('diff_wl_bank_text') or ''):
                    diff_wl = -diff_wl
            
            results.append({
                'id': st.get('id'),
                'station_name': station_info.get('tele_station_name', {}).get('th', ''),
                'province': geocode.get('province_name', {}).get('th', ''),
                'basin': basin.get('basin_name', {}).get('th', ''),
                'waterlevel_msl': _to_float(st.get('waterlevel_msl')),
                'storage_percent': _to_float(st.get('storage_percent')),
                'diff_wl_bank': diff_wl,
                'situation_level': st.get('situation_level'),
            })
        return results
    except Exception as e:
        logger.warning(f'ThaiWater waterlevel fetch failed: {e}')
        return []
