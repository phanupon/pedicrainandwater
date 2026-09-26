"""
Flood prediction engine.
ระบบทำนายน้ำท่วมโดยใช้ Rule-Based + Weighted Scoring
"""
import logging
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger('flood_alert')

# Risk thresholds
RAIN_THRESHOLDS = {
    'CRITICAL': 60.0,   # ≥60mm/hr = เสี่ยงมากที่สุด
    'HIGH': 35.0,       # ≥35mm/hr = เสี่ยงสูง
    'MODERATE': 15.0,   # ≥15mm/hr = เสี่ยงปานกลาง
    'LOW': 5.0,         # ≥5mm/hr = เฝ้าระวัง
}

DAM_THRESHOLDS = {
    'CRITICAL': 95.0,
    'HIGH': 90.0,
    'MODERATE': 75.0,
    'LOW': 60.0,
}

# Risk weights
WEIGHT_RAIN = 0.55
WEIGHT_DAM = 0.30
WEIGHT_HISTORY = 0.15


def calculate_rain_score(precipitation_mm: float) -> float:
    """แปลงปริมาณฝน → คะแนน 0-100."""
    if precipitation_mm >= RAIN_THRESHOLDS['CRITICAL']:
        return 100.0
    elif precipitation_mm >= RAIN_THRESHOLDS['HIGH']:
        return 75.0 + 25.0 * (precipitation_mm - RAIN_THRESHOLDS['HIGH']) / (RAIN_THRESHOLDS['CRITICAL'] - RAIN_THRESHOLDS['HIGH'])
    elif precipitation_mm >= RAIN_THRESHOLDS['MODERATE']:
        return 45.0 + 30.0 * (precipitation_mm - RAIN_THRESHOLDS['MODERATE']) / (RAIN_THRESHOLDS['HIGH'] - RAIN_THRESHOLDS['MODERATE'])
    elif precipitation_mm >= RAIN_THRESHOLDS['LOW']:
        return 15.0 + 30.0 * (precipitation_mm - RAIN_THRESHOLDS['LOW']) / (RAIN_THRESHOLDS['MODERATE'] - RAIN_THRESHOLDS['LOW'])
    else:
        return max(0.0, precipitation_mm / RAIN_THRESHOLDS['LOW'] * 15.0)


def calculate_dam_score(storage_percent: float) -> float:
    """แปลง % น้ำในอ่าง → คะแนน 0-100."""
    if storage_percent is None:
        return 30.0  # default moderate uncertainty
    if storage_percent >= DAM_THRESHOLDS['CRITICAL']:
        return 100.0
    elif storage_percent >= DAM_THRESHOLDS['HIGH']:
        return 80.0 + 20.0 * (storage_percent - DAM_THRESHOLDS['HIGH']) / (DAM_THRESHOLDS['CRITICAL'] - DAM_THRESHOLDS['HIGH'])
    elif storage_percent >= DAM_THRESHOLDS['MODERATE']:
        return 50.0 + 30.0 * (storage_percent - DAM_THRESHOLDS['MODERATE']) / (DAM_THRESHOLDS['HIGH'] - DAM_THRESHOLDS['MODERATE'])
    elif storage_percent >= DAM_THRESHOLDS['LOW']:
        return 20.0 + 30.0 * (storage_percent - DAM_THRESHOLDS['LOW']) / (DAM_THRESHOLDS['MODERATE'] - DAM_THRESHOLDS['LOW'])
    else:
        return max(0.0, storage_percent / DAM_THRESHOLDS['LOW'] * 20.0)


def calculate_history_score(province) -> float:
    """
    คำนวณคะแนนจากประวัติน้ำท่วม (เดือนที่มีความเสี่ยงสูง).
    ฤดูฝนไทย: พ.ค. - ต.ค.
    """
    from django.utils import timezone
    month = timezone.now().month
    high_risk_months = {8: 90, 9: 100, 10: 90, 11: 70, 7: 60, 6: 40, 5: 30}
    return float(high_risk_months.get(month, 10))


def score_to_risk_level(score: float) -> str:
    """แปลงคะแนนรวม → ระดับความเสี่ยง."""
    if score >= 80:
        return 'CRITICAL'
    elif score >= 60:
        return 'HIGH'
    elif score >= 40:
        return 'MODERATE'
    elif score >= 20:
        return 'LOW'
    else:
        return 'SAFE'


def score_to_probability(score: float) -> float:
    """แปลงคะแนน → ความน่าจะเป็น (%)."""
    # Sigmoid-like mapping
    import math
    return round(100 / (1 + math.exp(-0.08 * (score - 50))), 1)


def predict_flood_for_province(province, weather_queryset, dam_queryset):
    """
    ทำนายน้ำท่วมสำหรับจังหวัดหนึ่ง.

    Args:
        province: Province model instance
        weather_queryset: QuerySet ของ WeatherData (24-48 ชม. ข้างหน้า)
        dam_queryset: QuerySet ของ DamData (ล่าสุด)

    Returns:
        dict with prediction fields
    """
    # 1. Rain score from max forecast precipitation
    if weather_queryset.exists():
        max_rain = max((w.precipitation_mm for w in weather_queryset), default=0.0)
        total_rain_24h = sum(w.precipitation_mm for w in weather_queryset[:24])
    else:
        max_rain = 0.0
        total_rain_24h = 0.0

    rain_score = calculate_rain_score(max_rain)

    # 2. Dam score - use nearest/most relevant dam
    dam_fill_pct = None
    if dam_queryset.exists():
        # Take max storage % among relevant dams as worst case
        dam_fill_pct = max(
            (d.storage_percent for d in dam_queryset if d.storage_percent is not None),
            default=None
        )
    dam_score = calculate_dam_score(dam_fill_pct)

    # 3. History/seasonal score
    history_score = calculate_history_score(province)

    # 4. Weighted total
    total_score = (
        WEIGHT_RAIN * rain_score +
        WEIGHT_DAM * dam_score +
        WEIGHT_HISTORY * history_score
    )

    risk_level = score_to_risk_level(total_score)
    probability = score_to_probability(total_score)

    # Build notes
    notes_parts = []
    if max_rain > 0:
        notes_parts.append(f'ฝนสูงสุด {max_rain:.1f} มม./ชม.')
    if total_rain_24h > 0:
        notes_parts.append(f'ฝนสะสม 24 ชม. {total_rain_24h:.1f} มม.')
    if dam_fill_pct is not None:
        notes_parts.append(f'น้ำในอ่าง {dam_fill_pct:.1f}%')
    notes = ' | '.join(notes_parts)

    return {
        'risk_level': risk_level,
        'flood_probability': probability,
        'expected_rain_mm': total_rain_24h,
        'dam_fill_pct': dam_fill_pct,
        'score_rain': round(rain_score, 2),
        'score_dam': round(dam_score, 2),
        'score_history': round(history_score, 2),
        'notes': notes,
        'valid_for_time': timezone.now() + timedelta(hours=6),
    }


def generate_alert_message(province, prediction_data: dict) -> dict | None:
    """
    สร้างข้อความแจ้งเตือนจากผลการทำนาย.
    Returns alert dict or None if no alert needed.
    """
    risk = prediction_data['risk_level']
    prob = prediction_data['flood_probability']
    rain = prediction_data['expected_rain_mm']
    dam = prediction_data.get('dam_fill_pct')

    if risk == 'SAFE':
        return None

    if risk == 'CRITICAL':
        alert_type = 'FLOOD_CRITICAL'
        title = f'🚨 เตือนภัยวิกฤต: น้ำท่วมในจังหวัด{province.name_th}'
        message = (
            f'⚠️ ความเสี่ยงน้ำท่วมระดับ "วิกฤต" ในจังหวัด{province.name_th}\n'
            f'📊 ความน่าจะเป็น: {prob}%\n'
            f'🌧️ ฝนสะสม 24 ชม. ที่คาดการณ์: {rain:.1f} มม.\n'
        )
        if dam:
            message += f'🏞️ ระดับน้ำในอ่างเก็บน้ำ: {dam:.1f}%\n'
        message += '⚡ โปรดอพยพออกจากพื้นที่เสี่ยงทันที!'

    elif risk == 'HIGH':
        alert_type = 'FLOOD_RISK'
        title = f'⚠️ เสี่ยงน้ำท่วมสูง: จังหวัด{province.name_th}'
        message = (
            f'ความเสี่ยงน้ำท่วมระดับ "สูง" ในจังหวัด{province.name_th}\n'
            f'ความน่าจะเป็น: {prob}%\n'
            f'ฝนที่คาดการณ์ 24 ชม.: {rain:.1f} มม.\n'
            '⚡ โปรดติดตามสถานการณ์อย่างใกล้ชิดและเตรียมความพร้อม'
        )

    elif risk == 'MODERATE':
        alert_type = 'FLOOD_RISK'
        title = f'🟠 เฝ้าระวังน้ำท่วม: จังหวัด{province.name_th}'
        message = (
            f'มีความเสี่ยงน้ำท่วมปานกลางในจังหวัด{province.name_th}\n'
            f'ความน่าจะเป็น: {prob}%\n'
            f'ฝนที่คาดการณ์ 24 ชม.: {rain:.1f} มม.'
        )

    else:  # LOW
        alert_type = 'HEAVY_RAIN'
        title = f'🟡 เฝ้าระวังฝนหนัก: จังหวัด{province.name_th}'
        message = (
            f'อาจมีฝนตกหนักในจังหวัด{province.name_th}\n'
            f'ความน่าจะเป็นน้ำท่วม: {prob}%\n'
            f'ฝนที่คาดการณ์ 24 ชม.: {rain:.1f} มม.'
        )

    return {
        'alert_type': alert_type,
        'title': title,
        'message': message,
    }
