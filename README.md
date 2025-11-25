# 🚀 TalkApp Backend

Telegram integratsiyasi va foydalanuvchi boshqaruvi uchun yaratilgan zamonaviy backend platformasi.
FastAPI, Pyrogram va Supabase texnologiyalari asosida qurilgan bo'lib, foydalanuvchilarga Telegram akkauntlarini ulash, chatlarni boshqarish va autentifikatsiya imkoniyatlarini taqdim etadi.

## ✨ Asosiy xususiyatlar

- 🔐 **Supabase autentifikatsiyasi** - Xavfsiz token asosida login va foydalanuvchi boshqaruvi
- 📱 **Telegram integratsiyasi** - Ko'p akkauntli Telegram sessiyalarini boshqarish
- 👥 **Admin panel** - Foydalanuvchilarni va ularning Telegram akkauntlarini boshqarish
- 🖼️ **Media boshqaruvi** - Avatar va media fayllarini serverda saqlash
- 📊 **Monitoring** - Tizim holatini real vaqtda kuzatish
- 🌐 **Deploy-ready** - Railway, Heroku va boshqa platformalarda ishga tushirishga tayyor

## 🛠 Texnologiyalar

- [**FastAPI**](https://fastapi.tiangolo.com) - Backend framework
- [**Pyrogram**](https://docs.pyrogram.org/) - Telegram API bilan ishlash
- [**Supabase**](https://supabase.com/) - Database va autentifikatsiya
- [**Uvicorn**](https://www.uvicorn.org/) - ASGI server
- [**Chart.js**](https://www.chartjs.org/) - Monitoring uchun grafiklar

## 📂 Loyihaning strukturasi

```
TalkAppBackend/
├── src/
│   ├── main.py                 # FastAPI asosiy fayl
│   ├── config.py               # Konfiguratsiya va sozlamalar
│   ├── routers/
│   │   ├── auth.py            # Autentifikatsiya endpointlari
│   │   └── telegram.py        # Telegram integratsiyasi
│   ├── services/
│   │   ├── telegram_service.py # Telegram xizmatlari
│   │   ├── supabase_service.py # Supabase yordamchi funksiyalar
│   │   └── json_utils.py      # JSON yordamchi funksiyalar
│   └── models/
│       └── user.py            # Pydantic modellar
├── migrations/                 # Database migratsiyalari
├── sessions/                   # Telegram sessiya fayllari
├── media/                      # Yuklangan fayllar
├── requirements.txt            # Python paketlari
├── run.sh & run.bat           # Ishga tushirish skriptlari
├── Procfile                    # Railway deploy konfiguratsiyasi
└── README.md                   # Ushbu fayl
```

## ⚡ O'rnatish va ishga tushirish

### 1. Reponi klonlash
```bash
git clone <repository-url>
cd TalkAppBackend
```

### 2. Virtual environment yaratish
```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

### 3. Paketlarni o'rnatish
```bash
pip install -r requirements.txt
```

### 4. Environment variables
`.env` fayl yarating va quyidagi o'zgaruvchilarni to'ldiring:
```env
API_ID=your_telegram_api_id
API_HASH=your_telegram_api_hash
SUPABASE_URL=your_supabase_project_url
SUPABASE_ANON_KEY=your_supabase_anon_key
SUPABASE_SERVICE_KEY=your_supabase_service_key
```

### 5. Serverni ishga tushirish
```bash
# Development mode
python -m uvicorn src.main:app --reload

# yoki run.sh dan foydalanish
bash run.sh
```

Server `http://127.0.0.1:8000` da ishlaydi.

## 🔑 API Endpointlari

### Autentifikatsiya

#### Login
```http
POST /auth/login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "password"
}
```

#### Joriy foydalanuvchi ma'lumotlari
```http
GET /auth/me
Authorization: Bearer <token>
```

### Admin endpointlar

#### Barcha foydalanuvchilarni ko'rish
```http
GET /admin/users
Authorization: Bearer <admin-token>
```

#### Foydalanuvchi yaratish
```http
POST /admin/users
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "email": "newuser@example.com",
  "password": "password123"
}
```

#### Foydalanuvchilarni Telegram akkauntlari bilan ko'rish
```http
GET /admin/users-with-telegrams
Authorization: Bearer <admin-token>
```

### Telegram integratsiyasi

#### Login boshlash
```http
POST /start_login
Content-Type: application/json

{
  "phone_number": "+998901234567",
  "user_id": "supabase-user-id"
}
```

#### Kodni tasdiqlash
```http
POST /verify_code
Content-Type: application/json

{
  "phone_number": "+998901234567",
  "user_id": "supabase-user-id",
  "code": "12345"
}
```

#### Shaxsiy chatlar ro'yxati
```http
GET /me/private_chats/{user_id}/{session_index}?dialog_limit=10
Authorization: Bearer <token>
```

## 📊 Monitoring

Server ishga tushganda `/` sahifasida tizim monitoringi mavjud:
- CPU va RAM foydalanish
- Disk holati
- Tarmoq trafigi
- Real vaqt loglari

## 🚀 Deploy

### Railway
1. GitHub repositoriyasini Railway'ga ulang
2. Environment variables ni qo'shing
3. Deploy boshlang

### Heroku
```bash
heroku create your-app-name
heroku config:set API_ID=your_api_id API_HASH=your_api_hash SUPABASE_URL=your_url SUPABASE_ANON_KEY=your_key SUPABASE_SERVICE_KEY=your_service_key
git push heroku main
```

## 🔧 Konfiguratsiya

### Environment Variables
- `API_ID` - Telegram API ID
- `API_HASH` - Telegram API Hash
- `SUPABASE_URL` - Supabase project URL
- `SUPABASE_ANON_KEY` - Supabase anon key
- `SUPABASE_SERVICE_KEY` - Supabase service key
- `PORT` - Server port (Railway/Heroku uchun)

## 📝 Logs

Loglar `app.log` faylida saqlanadi va `/logs` endpoint orqali ko'rish mumkin.

## 🤝 Hissa qo'shish

1. Fork qiling
2. Feature branch yarating (`git checkout -b feature/amazing-feature`)
3. O'zgarishlarni commit qiling (`git commit -m 'Add amazing feature'`)
4. Push qiling (`git push origin feature/amazing-feature`)
5. Pull Request yarating

## 📄 Litsenziya

Bu loyiha MIT litsenziyasi ostida tarqatiladi.