"""
Django models for flood alert system.
ฐานข้อมูล SQLite สำหรับระบบแจ้งเตือนน้ำท่วม
"""
from django.db import models
from django.utils import timezone


class Province(models.Model):
    """จังหวัด"""
    name_th = models.CharField(max_length=100, verbose_name='ชื่อจังหวัด (ไทย)')
    name_en = models.CharField(max_length=100, verbose_name='Province Name (EN)')
    latitude = models.FloatField(verbose_name='ละติจูด')
    longitude = models.FloatField(verbose_name='ลองจิจูด')
    region = models.CharField(max_length=50, verbose_name='ภูมิภาค', default='')

    class Meta:
        verbose_name = 'จังหวัด'
        verbose_name_plural = 'จังหวัด'
        ordering = ['name_th']

    def __str__(self):
        return self.name_th


class WeatherData(models.Model):
    """ข้อมูลสภาพอากาศจาก Open-Meteo"""
    SOURCE_CHOICES = [
        ('open_meteo', 'Open-Meteo'),
        ('tmd', 'กรมอุตุนิยมวิทยา'),
        ('manual', 'ป้อนเอง'),
    ]

    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='weather_data')
    timestamp = models.DateTimeField(verbose_name='เวลาที่บันทึก', default=timezone.now)
    forecast_time = models.DateTimeField(verbose_name='เวลาพยากรณ์')
    precipitation_mm = models.FloatField(verbose_name='ปริมาณฝน (มม./ชม.)', default=0.0)
    temperature_c = models.FloatField(verbose_name='อุณหภูมิ (°C)', null=True, blank=True)
    humidity_pct = models.FloatField(verbose_name='ความชื้นสัมพัทธ์ (%)', null=True, blank=True)
    wind_speed_kmh = models.FloatField(verbose_name='ความเร็วลม (กม./ชม.)', null=True, blank=True)
    cloud_cover_pct = models.FloatField(verbose_name='เมฆปกคลุม (%)', null=True, blank=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='open_meteo')

    class Meta:
        verbose_name = 'ข้อมูลสภาพอากาศ'
        verbose_name_plural = 'ข้อมูลสภาพอากาศ'
        ordering = ['-forecast_time']
        indexes = [
            models.Index(fields=['province', 'forecast_time']),
            models.Index(fields=['forecast_time']),
        ]

    def __str__(self):
        return f'{self.province} | {self.forecast_time} | {self.precipitation_mm}mm'


class DamData(models.Model):
    """ข้อมูลอ่างเก็บน้ำจากกรมชลประทาน"""
    rid_code = models.CharField(max_length=20, verbose_name='รหัสเขื่อน (RID)')
    dam_name = models.CharField(max_length=200, verbose_name='ชื่อเขื่อน')
    province = models.ForeignKey(
        Province, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='dams', verbose_name='จังหวัด'
    )
    capacity_mcm = models.FloatField(verbose_name='ความจุ (ล้าน ม³)', null=True, blank=True)
    volume_mcm = models.FloatField(verbose_name='ปริมาณน้ำ (ล้าน ม³)', null=True, blank=True)
    storage_percent = models.FloatField(verbose_name='% การเก็บกักน้ำ', null=True, blank=True)
    inflow_cms = models.FloatField(verbose_name='น้ำไหลเข้า (ม³/วินาที)', null=True, blank=True)
    outflow_cms = models.FloatField(verbose_name='น้ำระบาย (ม³/วินาที)', null=True, blank=True)
    timestamp = models.DateTimeField(verbose_name='เวลาที่บันทึก', default=timezone.now)

    class Meta:
        verbose_name = 'ข้อมูลอ่างเก็บน้ำ'
        verbose_name_plural = 'ข้อมูลอ่างเก็บน้ำ'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['rid_code', 'timestamp']),
        ]

    def __str__(self):
        return f'{self.dam_name} ({self.storage_percent:.1f}%)'


class FloodPrediction(models.Model):
    """ผลการทำนายน้ำท่วม"""
    RISK_LEVELS = [
        ('SAFE', '🟢 ปลอดภัย'),
        ('LOW', '🟡 เฝ้าระวัง'),
        ('MODERATE', '🟠 เสี่ยงปานกลาง'),
        ('HIGH', '🔴 เสี่ยงสูง'),
        ('CRITICAL', '🚨 วิกฤต'),
    ]

    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='predictions')
    predicted_at = models.DateTimeField(verbose_name='เวลาทำนาย', default=timezone.now)
    valid_for_time = models.DateTimeField(verbose_name='เวลาที่ใช้ได้ถึง')
    risk_level = models.CharField(max_length=10, choices=RISK_LEVELS, verbose_name='ระดับความเสี่ยง')
    flood_probability = models.FloatField(verbose_name='ความน่าจะเป็น (%)', default=0.0)
    expected_rain_mm = models.FloatField(verbose_name='ฝนที่คาดการณ์ (มม.)', default=0.0)
    dam_fill_pct = models.FloatField(verbose_name='% น้ำในอ่าง', null=True, blank=True)
    notes = models.TextField(verbose_name='หมายเหตุ', blank=True, default='')
    # Factors
    score_rain = models.FloatField(verbose_name='คะแนนฝน (0-100)', default=0.0)
    score_dam = models.FloatField(verbose_name='คะแนนอ่าง (0-100)', default=0.0)
    score_history = models.FloatField(verbose_name='คะแนนประวัติ (0-100)', default=0.0)

    class Meta:
        verbose_name = 'ผลการทำนายน้ำท่วม'
        verbose_name_plural = 'ผลการทำนายน้ำท่วม'
        ordering = ['-predicted_at']
        indexes = [
            models.Index(fields=['province', 'predicted_at']),
            models.Index(fields=['risk_level']),
        ]

    def __str__(self):
        return f'{self.province} | {self.get_risk_level_display()} | {self.predicted_at:%d/%m/%Y %H:%M}'


class Alert(models.Model):
    """การแจ้งเตือน"""
    ALERT_TYPES = [
        ('HEAVY_RAIN', '🌧️ ฝนตกหนัก'),
        ('FLOOD_RISK', '⚠️ เสี่ยงน้ำท่วม'),
        ('FLOOD_CRITICAL', '🚨 น้ำท่วมวิกฤต'),
        ('DAM_FULL', '🏞️ อ่างเก็บน้ำเต็ม'),
        ('DAM_WARNING', '⚠️ อ่างเก็บน้ำเกือบเต็ม'),
    ]

    province = models.ForeignKey(Province, on_delete=models.CASCADE, related_name='alerts')
    prediction = models.ForeignKey(
        FloodPrediction, on_delete=models.SET_NULL, null=True, blank=True
    )
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPES)
    title = models.CharField(max_length=300, verbose_name='หัวข้อการแจ้งเตือน')
    message = models.TextField(verbose_name='ข้อความแจ้งเตือน')
    is_active = models.BooleanField(default=True, verbose_name='ยังใช้งาน')
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True, verbose_name='เวลารับทราบ')

    class Meta:
        verbose_name = 'การแจ้งเตือน'
        verbose_name_plural = 'การแจ้งเตือน'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_alert_type_display()} | {self.province} | {self.created_at:%d/%m/%Y %H:%M}'


class DataFetchLog(models.Model):
    """ประวัติการดึงข้อมูล"""
    SOURCE_CHOICES = [
        ('open_meteo', 'Open-Meteo'),
        ('rid_dam', 'RID อ่างเก็บน้ำ'),
        ('gistda', 'GISTDA'),
        ('tmd', 'กรมอุตุ'),
    ]
    STATUS_CHOICES = [
        ('success', '✅ สำเร็จ'),
        ('error', '❌ ผิดพลาด'),
        ('partial', '⚠️ บางส่วน'),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    records_fetched = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    fetched_at = models.DateTimeField(auto_now_add=True)
    duration_ms = models.IntegerField(default=0, verbose_name='ระยะเวลา (มิลลิวินาที)')

    class Meta:
        verbose_name = 'ประวัติการดึงข้อมูล'
        verbose_name_plural = 'ประวัติการดึงข้อมูล'
        ordering = ['-fetched_at']

    def __str__(self):
        return f'{self.get_source_display()} | {self.get_status_display()} | {self.fetched_at:%d/%m/%Y %H:%M}'
