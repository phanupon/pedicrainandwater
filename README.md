# 🌊 FloodGuard Thailand

ระบบทำนายและแจ้งเตือน **น้ำท่วม** และ **ฝนตกหนัก** สำหรับประเทศไทย บนสภาพแวดล้อม Docker

---

## 🏗️ สถาปัตยกรรม

```
┌────────────────────────────────────────────────────────┐
│                  Docker Compose                        │
│                                                        │
│  ┌──────────┐   ┌──────────────┐   ┌───────────────┐  │
│  │  Redis   │   │  Django Web  │   │ Celery Worker │  │
│  │  :6379   │◄──│  (Daphne)    │   │ (4 workers)   │  │
│  │          │   │  :8000       │   │               │  │
│  └──────────┘   └──────┬───────┘   └───────────────┘  │
│       ▲                │                    ▲          │
│       └────────────────┴────────────────────┘          │
│                 ┌───────────────┐                       │
│                 │ Celery Beat   │                       │
│                 │ (Scheduler)   │                       │
│                 └───────────────┘                       │
│                                                        │
│         Persistent Volumes: SQLite + Static            │
└────────────────────────────────────────────────────────┘
```

## 📡 แหล่งข้อมูล API

| แหล่งข้อมูล | ข้อมูล | Key ที่ต้องการ |
|---|---|---|
| **Open-Meteo** | พยากรณ์ฝนรายชั่วโมง 72 ชม. | ❌ ฟรี ไม่ต้องมี |
| **กรมชลประทาน (RID)** | ระดับน้ำ/ปริมาณน้ำในอ่าง | ❌ ฟรี ไม่ต้องมี |
| **GISTDA** | พื้นที่น้ำท่วมจากดาวเทียม | 🔑 ต้องลงทะเบียน |
| **กรมอุตุนิยมวิทยา (TMD)** | พยากรณ์อากาศทางการ | 🔑 ต้องลงทะเบียน |

## 🚀 วิธีเริ่มใช้งาน

### 1. คัดลอกไฟล์ environment
```bash
cp .env.example .env
```

### 2. แก้ไข `.env` (ถ้ามี API key)
```
TMD_API_UID=your_uid_here
TMD_API_UKEY=your_ukey_here
GISTDA_API_KEY=your_key_here
```

### 3. รัน Docker Compose
```bash
docker-compose up --build
```

### 4. เข้าใช้งาน
- **Dashboard**: http://localhost:8000
- **Admin Panel**: http://localhost:8000/admin
- **API Predictions**: http://localhost:8000/api/predictions/
- **API Alerts**: http://localhost:8000/api/alerts/

### 5. สร้าง Django Admin User
```bash
docker-compose exec web python manage.py createsuperuser
```

## 🧮 ระบบทำนาย (Rule-Based Scoring)

ใช้ **Weighted Scoring Model** จาก 3 ปัจจัย:

| ปัจจัย | น้ำหนัก | คำอธิบาย |
|---|---|---|
| 🌧️ ฝนจากพยากรณ์ | **55%** | ปริมาณฝนสูงสุดในช่วง 24 ชม. |
| 🏞️ ระดับน้ำในอ่าง | **30%** | % การเก็บกักน้ำในอ่างเก็บน้ำ |
| 📅 ฤดูกาล/ประวัติ | **15%** | เดือนที่มีความเสี่ยงสูงตามฤดูกาล |

### ระดับความเสี่ยง

| ระดับ | คะแนน | ฝน |
|---|---|---|
| 🟢 ปลอดภัย | 0-20 | < 5 มม./ชม. |
| 🟡 เฝ้าระวัง | 20-40 | 5-15 มม./ชม. |
| 🟠 เสี่ยงปานกลาง | 40-60 | 15-35 มม./ชม. |
| 🔴 เสี่ยงสูง | 60-80 | 35-60 มม./ชม. |
| 🚨 วิกฤต | 80-100 | ≥ 60 มม./ชม. |

## ⏱️ ตารางเวลาอัตโนมัติ

| งาน | ความถี่ |
|---|---|
| ดึงข้อมูลพยากรณ์ฝน (Open-Meteo) | ทุก 1 ชม. |
| ดึงข้อมูลอ่างเก็บน้ำ (RID) | ทุก 3 ชม. |
| ประมวลผลทำนายน้ำท่วม | ทุก 30 นาที |
| ลบข้อมูลเก่า | ทุกวัน 02:00 |

## 🔌 WebSocket Real-time

เชื่อมต่อ: `ws://localhost:8000/ws/alerts/`

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/alerts/');
ws.onmessage = (event) => {
    const { type, data } = JSON.parse(event.data);
    if (type === 'alert') console.log(data);
};
```

## 🛠️ คำสั่งที่มีประโยชน์

```bash
# ดู logs ทั้งหมด
docker-compose logs -f

# ดู logs เฉพาะ worker
docker-compose logs -f celery-worker

# รันงานทำนายทันที
docker-compose exec web python -c "
from flood_alert.tasks import run_flood_predictions
run_flood_predictions.delay()
"

# เข้า Django shell
docker-compose exec web python manage.py shell

# รัน migrations
docker-compose exec web python manage.py migrate

# หยุด
docker-compose down

# หยุดและลบ volumes
docker-compose down -v
```

## 📁 โครงสร้างไฟล์

```
predicrainandwater/
├── docker-compose.yml
├── .env.example
├── .gitignore
└── pedicrainandwater/
    ├── Dockerfile
    ├── entrypoint.sh
    ├── requirements.txt
    ├── manage.py
    ├── flood_project/
    │   ├── settings.py       # การตั้งค่าหลัก
    │   ├── celery.py         # Celery config
    │   ├── asgi.py           # WebSocket (Daphne)
    │   └── urls.py
    └── flood_alert/
        ├── models.py         # ฐานข้อมูล (SQLite)
        ├── views.py          # Views & API
        ├── tasks.py          # Celery tasks
        ├── services.py       # เชื่อมต่อ API ภายนอก
        ├── predictor.py      # ระบบทำนายน้ำท่วม
        ├── consumers.py      # WebSocket
        ├── admin.py          # Django Admin
        ├── management/commands/
        │   └── seed_provinces.py  # seed จังหวัดทั้งหมด
        ├── templates/
        └── static/
```
