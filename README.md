# Torex-Talk: Supabase va FastAPI loyihasi

Bu loyiha FastAPI va Supabase yordamida email va Google OAuth orqali foydalanuvchi autentifikatsiyasini amalga oshiradi.

## O'rnatish
1. Python 3.8+ o'rnatilgan bo'lishi kerak.
2. Kerakli kutubxonalarni o'rnatish:
   ```
   pip install -r requirements.txt
   ```
3. `.env` faylini yarating va quyidagi ma'lumotlarni kiriting:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_ANON_KEY=your_anon_key
   GOOGLE_CLIENT_ID=your_google_client_id
   GOOGLE_CLIENT_SECRET=your_google_client_secret
   ```

## Ishga tushirish
Serverni ishga tushirish uchun:
```
./run.sh
```

## Endpointlar
- `POST /signup`: Email orqali ro'yxatdan o'tish.
- `POST /signin`: Email orqali kirish.
- `POST /signin/google`: Google OAuth orqali kirish.
- `GET /user`: Foydalanuvchi ma'lumotlarini olish.

