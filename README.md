from pathlib import Path

# README.md content
readme_content = """# 🚀 TalkAppBackend

Telegram akkauntlari orqali **xususiy chatlar** va **dialog ma’lumotlari**ni boshqarish uchun yaratilgan kuchli backend.  
Loyiha FastAPI, Pyrogram va Supabase texnologiyalari asosida qurilgan bo‘lib, sizga **Telegram akkauntlaringizni ulash, chatlarni olish, foydalanuvchi avatarlarini serverga yuklab saqlash** imkonini beradi.  

---

## ✨ Asosiy imkoniyatlar

- 🔑 **Supabase autentifikatsiyasi** orqali xavfsiz token asosida login.  
- 💬 **Shaxsiy chatlar ro‘yxati**: fullname, username, online/offline status, oxirgi faollik.  
- 🖼 **Foydalanuvchi avatarlarini serverda saqlash** va `/media/avatars/...` orqali URL sifatida ko‘rsatish.  
- 📜 **Minimal va to‘liq chat metadatalar**ni olish imkoniyati.  
- 📂 **Ko‘p akkauntli qo‘llab-quvvatlash** (1 foydalanuvchi bir nechta Telegram sessiya ulashi mumkin).  
- 🌐 **Deploy-ready**: Railway yoki Heroku’da ishlashga tayyor konfiguratsiya (`Procfile`, `run.sh`).  

---

## 🛠 Texnologiyalar

- [**FastAPI**](https://fastapi.tiangolo.com) — backend framework  
- [**Pyrogram**](https://docs.pyrogram.org/) — Telegram API bilan ishlash  
- [**Supabase**](https://supabase.com/) — autentifikatsiya va foydalanuvchi ma’lumotlarini boshqarish  
- [**Uvicorn**](https://www.uvicorn.org/) — ASGI server  
- [**Railway**](https://railway.app/) — deploy uchun  

---

## 📂 Loyihaning strukturasi

```
.
├── src/
│   ├── main.py              # FastAPI asosiy entrypoint
│   ├── routers/telegram.py  # Telegram API endpointlari
│   ├── services/            # Telegram va Supabase xizmatlari
│   ├── models/              # Model va helper fayllar
│   └── config.py            # API_ID, API_HASH, Supabase sozlamalari
├── sessions/                # Telegram sessiya fayllari
├── media/avatars/           # Foydalanuvchi profil suratlari
├── requirements.txt         # Python kutubxonalari
├── run.sh                   # Serverni lokal ishga tushirish skripti
└── Procfile                 # Railway deploy konfiguratsiyasi
```

---

## ⚡️ O‘rnatish

1. Reponi klonlash:
   ```bash
   git clone https://github.com/NetCash-Org/TalkAppBackend
   cd TalkAppBackend
   ```

2. Virtual environment yaratish:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Kerakli paketlarni o‘rnatish:
   ```bash
   pip install -r requirements.txt
   ```

4. `.env` fayl yarating va quyidagilarni to‘ldiring:
   ```env
   API_ID=your_telegram_api_id
   API_HASH=your_telegram_api_hash
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_service_key
   ```

5. Lokal serverni ishga tushirish:
   ```bash
   bash run.sh
   ```
   Server `http://127.0.0.1:8000` da ishlaydi.

---

## 🔑 Autentifikatsiya

Barcha endpointlar **Bearer token** orqali chaqiriladi.  
Tokenni Supabase orqali olasiz va headerga qo‘shasiz:

```http
Authorization: Bearer <token>
```

---

## 📡 API Endpointlari

### 1. Shaxsiy chatlar ro‘yxati
```http
GET /me/private_chats/{user_id}/{session_index}?dialog_limit=10
```

**Parametrlar**:
- `user_id` — Supabase foydalanuvchi ID  
- `session_index` — Telegram sessiya raqami  
- `dialog_limit` — nechta chat qaytarilishi (default: 10)  

**Natija**:
```json
{
  "ok": true,
  "count": 2,
  "items": [
    {
      "id": 1844592233,
      "full_name": "Dilshodjon Haydarov",
      "username": "torex_dev",
      "last_seen": "2025-09-15T12:30:00",
      "is_online": true,
      "photo_url": "/media/avatars/409fc386/1/1844592233_big.jpg"
    }
  ]
}
```

---

### 2. Chat avatarini saqlash
```http
POST /me/private_chats/avatar/{user_id}/{session}/{chat_id}?size=big
```

**Parametrlar**:
- `user_id` — Supabase foydalanuvchi ID  
- `session` — Telegram sessiya raqami  
- `chat_id` — Telegram chat ID  
- `size` — `big` yoki `small` (default: big)  

**Natija**:
```json
{
  "ok": true,
  "photo_url": "/media/avatars/409fc386/1/1844592233_big.jpg"
}
```

---

## 🚀 Deploy (Railway)

1. Repo GitHub’da bo‘lishi kerak.  
2. Railway’da yangi Service → GitHub repo ulash.  
3. **Procfile** va **run.sh** repo ildizida turgan bo‘lishi kerak.  

   - `Procfile`:
     ```
     web: uvicorn src.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers
     ```

   - `run.sh`:
     ```bash
     #!/bin/bash
     uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload
     ```

4. Settings → Variables bo‘limida `.env` dagi kalitlarni qo‘shing.  
5. Deploy boshlanganidan keyin `https://talkapp.up.railway.app/healthz` orqali tekshiring.  

---

## ❤️ Hissa qo‘shish

Loyiha **open-source**. PR va issue’lar xush kelibsiz.  
Qo‘shmoqchi bo‘lsangiz quyidagi branch flow’dan foydalaning:  

- `main` → Production  
- `dev` → Development  

---

## 📜 Litsenziya

MIT License. Erkin foydalanish mumkin.  
"""

# Save README.md
path = Path("README.md")
path.write_text(readme_content, encoding="utf-8")

path.absolute()