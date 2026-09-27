#!/bin/bash
set -e

echo "🌊 FloodGuard Thailand - Starting..."

# Run database migrations (flood_alert + all apps)
echo "📦 Running migrations..."
python manage.py migrate --noinput

# Seed provinces if not already seeded
echo "🗺️ Seeding Thai provinces..."
python manage.py seed_provinces

# Setup Celery Beat schedules via shell
echo "⏰ Setting up periodic tasks..."
python manage.py shell << 'PYEOF'
from django_celery_beat.models import PeriodicTask, IntervalSchedule, CrontabSchedule

# Create interval schedules
every_hour, _ = IntervalSchedule.objects.get_or_create(every=60, period=IntervalSchedule.MINUTES)
every_3h, _ = IntervalSchedule.objects.get_or_create(every=180, period=IntervalSchedule.MINUTES)
every_30min, _ = IntervalSchedule.objects.get_or_create(every=30, period=IntervalSchedule.MINUTES)

# Daily cleanup at 02:00 Bangkok
daily_2am, _ = CrontabSchedule.objects.get_or_create(
    minute='0', hour='2',
    day_of_week='*', day_of_month='*', month_of_year='*',
    timezone='Asia/Bangkok'
)

# Register periodic tasks
PeriodicTask.objects.update_or_create(
    name='fetch-weather',
    defaults={'task': 'flood_alert.fetch_weather_all_provinces', 'interval': every_hour, 'enabled': True}
)
PeriodicTask.objects.update_or_create(
    name='fetch-dam',
    defaults={'task': 'flood_alert.fetch_dam_data', 'interval': every_3h, 'enabled': True}
)
PeriodicTask.objects.update_or_create(
    name='fetch-thaiwater-rain',
    defaults={'task': 'flood_alert.fetch_thaiwater_rain', 'interval': every_hour, 'enabled': True}
)
PeriodicTask.objects.update_or_create(
    name='run-predictions',
    defaults={'task': 'flood_alert.run_flood_predictions', 'interval': every_30min, 'enabled': True}
)
PeriodicTask.objects.update_or_create(
    name='daily-cleanup',
    defaults={'task': 'flood_alert.cleanup_old_data', 'crontab': daily_2am, 'enabled': True}
)

print('✅ Periodic tasks registered successfully')
PYEOF

echo "✅ FloodGuard ready! Starting server..."
exec "$@"
