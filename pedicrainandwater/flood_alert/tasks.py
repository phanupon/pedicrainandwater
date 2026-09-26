"""
Celery tasks for periodic data fetching and flood prediction.
งานอัตโนมัติ: ดึงข้อมูล + ทำนาย + แจ้งเตือน
"""
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import Province, WeatherData, DamData, FloodPrediction, Alert, DataFetchLog
from .services import fetch_open_meteo_weather, fetch_rid_dam_data, fetch_tmd_weather
from .predictor import predict_flood_for_province, generate_alert_message

logger = logging.getLogger('flood_alert')


@shared_task(name='flood_alert.fetch_weather_all_provinces')
def fetch_weather_all_provinces():
    """ดึงข้อมูลพยากรณ์อากาศสำหรับทุกจังหวัด (ทุก 1 ชม.)"""
    provinces = Province.objects.all()
    total_records = 0
    start_time = time.time()

    for province in provinces:
        try:
            records = fetch_open_meteo_weather(province)
            # Save only future forecasts, avoid duplicates
            future_cutoff = timezone.now() - timedelta(hours=1)
            for rec in records:
                ft_str = rec['forecast_time']
                if isinstance(ft_str, str):
                    ft = parse_datetime(ft_str)
                    if ft and ft.tzinfo is None:
                        ft = ft.replace(tzinfo=ZoneInfo('Asia/Bangkok'))
                else:
                    ft = ft_str

                if ft and ft >= future_cutoff:
                    WeatherData.objects.update_or_create(
                        province=province,
                        forecast_time=ft,
                        defaults={
                            'precipitation_mm': rec.get('precipitation_mm', 0.0) or 0.0,
                            'temperature_c': rec.get('temperature_c'),
                            'humidity_pct': rec.get('humidity_pct'),
                            'wind_speed_kmh': rec.get('wind_speed_kmh'),
                            'cloud_cover_pct': rec.get('cloud_cover_pct'),
                            'source': rec.get('source', 'open_meteo'),
                        }
                    )
                    total_records += 1

        except Exception as e:
            logger.error(f'Weather fetch failed for {province}: {e}')

    duration_ms = int((time.time() - start_time) * 1000)
    DataFetchLog.objects.create(
        source='open_meteo',
        status='success' if total_records > 0 else 'error',
        records_fetched=total_records,
        duration_ms=duration_ms,
    )
    logger.info(f'Weather fetch complete: {total_records} records in {duration_ms}ms')
    return total_records


@shared_task(name='flood_alert.fetch_dam_data')
def fetch_dam_data():
    """ดึงข้อมูลอ่างเก็บน้ำจากกรมชลประทาน (ทุก 3 ชม.)"""
    start_time = time.time()
    try:
        dams = fetch_rid_dam_data()
        total = 0
        for dam in dams:
            if not dam.get('rid_code'):
                continue
            DamData.objects.create(
                rid_code=dam['rid_code'],
                dam_name=dam.get('dam_name', ''),
                capacity_mcm=dam.get('capacity_mcm'),
                volume_mcm=dam.get('volume_mcm'),
                storage_percent=dam.get('storage_percent'),
                inflow_cms=dam.get('inflow_cms'),
                outflow_cms=dam.get('outflow_cms'),
            )
            total += 1

        duration_ms = int((time.time() - start_time) * 1000)
        DataFetchLog.objects.create(
            source='rid_dam',
            status='success',
            records_fetched=total,
            duration_ms=duration_ms,
        )
        logger.info(f'Dam data fetch complete: {total} records')
        return total

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        DataFetchLog.objects.create(
            source='rid_dam',
            status='error',
            error_message=str(e),
            duration_ms=duration_ms,
        )
        logger.error(f'Dam fetch failed: {e}')
        return 0


@shared_task(name='flood_alert.run_flood_predictions')
def run_flood_predictions():
    """
    ประมวลผลทำนายน้ำท่วมสำหรับทุกจังหวัด (ทุก 30 นาที).
    สร้าง FloodPrediction และ Alert ใหม่ถ้าจำเป็น
    """
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    channel_layer = get_channel_layer()
    provinces = Province.objects.all()
    predictions_made = 0

    now = timezone.now()
    forecast_window_start = now
    forecast_window_end = now + timedelta(hours=24)

    for province in provinces:
        try:
            # Get relevant weather data
            weather_qs = WeatherData.objects.filter(
                province=province,
                forecast_time__gte=forecast_window_start,
                forecast_time__lte=forecast_window_end,
            ).order_by('forecast_time')

            # Get latest dam data (any dam, for broader context)
            dam_qs = DamData.objects.filter(
                timestamp__gte=now - timedelta(hours=12)
            ).order_by('-timestamp')[:20]

            # Run prediction
            pred_data = predict_flood_for_province(province, weather_qs, dam_qs)

            # Save prediction
            prediction = FloodPrediction.objects.create(
                province=province,
                valid_for_time=pred_data['valid_for_time'],
                risk_level=pred_data['risk_level'],
                flood_probability=pred_data['flood_probability'],
                expected_rain_mm=pred_data['expected_rain_mm'],
                dam_fill_pct=pred_data['dam_fill_pct'],
                score_rain=pred_data['score_rain'],
                score_dam=pred_data['score_dam'],
                score_history=pred_data['score_history'],
                notes=pred_data['notes'],
            )
            predictions_made += 1

            # Generate and save alert if needed
            alert_data = generate_alert_message(province, pred_data)
            if alert_data:
                # Avoid duplicate alerts within 2 hours
                recent_alert = Alert.objects.filter(
                    province=province,
                    alert_type=alert_data['alert_type'],
                    created_at__gte=now - timedelta(hours=2),
                    is_active=True,
                ).exists()

                if not recent_alert:
                    alert = Alert.objects.create(
                        province=province,
                        prediction=prediction,
                        **alert_data,
                    )
                    logger.info(f'Alert created: {alert}')

                    # Push via WebSocket
                    if channel_layer:
                        try:
                            async_to_sync(channel_layer.group_send)(
                                'alerts',
                                {
                                    'type': 'send_alert',
                                    'alert': {
                                        'id': alert.id,
                                        'province': province.name_th,
                                        'alert_type': alert_data['alert_type'],
                                        'title': alert_data['title'],
                                        'message': alert_data['message'],
                                        'risk_level': pred_data['risk_level'],
                                        'probability': pred_data['flood_probability'],
                                        'timestamp': now.isoformat(),
                                    }
                                }
                            )
                        except Exception as ws_err:
                            logger.warning(f'WebSocket push failed: {ws_err}')

        except Exception as e:
            logger.error(f'Prediction failed for {province}: {e}', exc_info=True)

    logger.info(f'Flood predictions complete: {predictions_made} provinces processed')
    return predictions_made


@shared_task(name='flood_alert.cleanup_old_data')
def cleanup_old_data():
    """ลบข้อมูลเก่าที่ไม่จำเป็น (ทุกวัน)"""
    cutoff = timezone.now() - timedelta(days=30)
    deleted_weather, _ = WeatherData.objects.filter(forecast_time__lt=cutoff).delete()
    deleted_dam, _ = DamData.objects.filter(timestamp__lt=cutoff).delete()
    deleted_logs, _ = DataFetchLog.objects.filter(fetched_at__lt=cutoff).delete()

    # Keep predictions for 90 days
    pred_cutoff = timezone.now() - timedelta(days=90)
    deleted_preds, _ = FloodPrediction.objects.filter(predicted_at__lt=pred_cutoff).delete()

    logger.info(
        f'Cleanup: {deleted_weather} weather, {deleted_dam} dam, '
        f'{deleted_logs} logs, {deleted_preds} predictions deleted'
    )
    return {
        'weather': deleted_weather,
        'dam': deleted_dam,
        'logs': deleted_logs,
        'predictions': deleted_preds,
    }
