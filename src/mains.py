from datetime import datetime, timezone
from typing import Optional, Any
from src.models.user import LoginIn, LoginOut, SetPlanIn, SupabaseUserRaw, UserAdmin, UserCreate, UserOut, UserSafe, UserUpdate, StartLoginIn, VerifyCodeIn, VerifyPasswordIn
from fastapi import FastAPI, HTTPException, Path, Header, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from src.config import API_ID, API_HASH, SESS_ROOT, PENDING_FILE, supabase, supabase_service
import json
import asyncio
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid, PhoneCodeExpired


app = FastAPI()



# ----------------- Helperlar -----------------

# --- helperlar (o'zgarish: type-annotatsiyada pathlib.Path ishlaydi) ---
def _user_dir(user_id: str) -> Path:
    p = SESS_ROOT / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def _next_index(user_id: str) -> int:
    d = _user_dir(user_id)
    existing = sorted(
        [int(p.stem.split(".")[0]) for p in d.glob("*.session") if p.stem.split(".")[0].isdigit()]
    )
    return (existing[-1] + 1) if existing else 1

def _session_path(user_id: str, account_index: Optional[int]) -> Path:
    if account_index is None:
        account_index = _next_index(user_id)
    return _user_dir(user_id) / f"{account_index}.session"

def _pending_path(user_id: str) -> Path:
    return _user_dir(user_id) / PENDING_FILE

def _write_pending(user_id: str, data: dict) -> None:
    f = _pending_path(user_id)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def _read_pending(user_id: str) -> dict:
    f = _pending_path(user_id)
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {}

def _clear_pending(user_id: str) -> None:
    f = _pending_path(user_id)
    if f.exists():
        f.unlink(missing_ok=True)

#Auth ---------------------------------------------------------------------------------------------------------

@app.post("/admin/set-plan")
async def admin_set_plan(body: SetPlanIn):
    try:
        meta = {
            "plan": body.plan,
            "status": "active" if body.plan != "free" else "inactive",
            "accounts_limit": body.accounts_limit,
            "features": body.features,
            "current_period_end": body.current_period_end,
        }
        supabase_service.auth.admin.update_user_by_id(body.user_id, {"app_metadata": meta})
        return {"ok": True, "app_metadata": meta}
    except Exception as e:
        raise HTTPException(400, str(e))

# CORS middleware (frontend localhost:3000 yoki 8000 da ishlayotgan bo‘lsa kerak)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],  # keraklisini qo‘shing
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SOG'LIK: Supabase'ga ulanishni tekshirish ---
@app.get("/check")
async def check_connection():
    try:
        # oddiy RPC chaqiruv bilan tekshirish
        _ = supabase.rpc("get_users_safe").execute()
        return {"message": "Supabase'ga ulanildi", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ulanish xatosi: {str(e)}")


# --- OMMAVIY: barcha userlarni olish (safe versiya) ---
@app.get("/users", response_model=list[UserSafe])
async def get_users():
    try:
        resp = supabase.rpc("get_users_safe").execute()
        return [UserSafe(**row) for row in resp.data or []]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- ADMIN: barcha userlarni olish (admin uchun) ---
@app.get("/admin/users", response_model=list[UserAdmin])
async def get_users_admin():
    try:
        resp = supabase.rpc("get_users_admin").execute()
        return [UserAdmin(**row) for row in resp.data or []]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

# --- ADMIN: create user ---
@app.post("/admin/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate):
    try:
        req = {
            "email": payload.email,
            "password": payload.password,  # None bo'lmasin
            "user_metadata": payload.user_metadata or {}
        }
        
        res = supabase_service.auth.admin.create_user(req)  # 403 bo'lsa, service key emas
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(status_code=500, detail="User yaratildi, lekin javobni o‘qib bo‘lmadi.")
        return UserOut(id=str(user.id), email=user.email)
    except Exception as e:
        print("AUTH CREATE USER ERROR:", repr(e))
        raise HTTPException(status_code=400, detail=str(e))
    

# --- ADMIN: update user ---
@app.patch("/admin/users/{user_id}", response_model=UserOut)
async def admin_update_user(
    user_id: str = Path(..., description="auth.users.id (uuid)"),
    payload: UserUpdate = ...
):
    try:
        # hech bo'lmaganda bitta field berilganiga ishonch hosil qilamiz
        if not any([
            payload.email, payload.password, payload.phone,
            payload.user_metadata, payload.app_metadata,
            payload.email_confirm is not None, payload.phone_confirm is not None,
            payload.ban_duration
        ]):
            raise HTTPException(status_code=422, detail="Hech qanday o‘zgartiriladigan maydon berilmagan.")

        attrs = {}
        if payload.email is not None: attrs["email"] = payload.email
        if payload.password is not None: attrs["password"] = payload.password
        if payload.phone is not None: attrs["phone"] = payload.phone
        if payload.user_metadata is not None: attrs["user_metadata"] = payload.user_metadata
        if payload.app_metadata is not None: attrs["app_metadata"] = payload.app_metadata
        if payload.email_confirm is not None: attrs["email_confirm"] = payload.email_confirm
        if payload.phone_confirm is not None: attrs["phone_confirm"] = payload.phone_confirm
        if payload.ban_duration is not None: attrs["ban_duration"] = payload.ban_duration

        # supabase-py v2: update_user_by_id(user_id, attributes)
        res = supabase_service.auth.admin.update_user_by_id(user_id, attrs)

        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(status_code=404, detail="User topilmadi yoki yangilanmadi.")
        return UserOut(id=str(user.id), email=user.email)

    except Exception as e:
        msg = str(e).lower()
        if "invalid email" in msg:
            raise HTTPException(status_code=422, detail="Email noto‘g‘ri.")
        if "password" in msg and "length" in msg:
            raise HTTPException(status_code=422, detail="Parol eng kamida 6 belgidan iborat bo‘lsin.")
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="User topilmadi.")
        raise HTTPException(status_code=400, detail=str(e))


# --- ADMIN: delete user (hard delete) ---
@app.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(user_id: str = Path(..., description="auth.users.id (uuid)")):
    try:
        # supabase-py v2: delete_user(user_id)
        supabase_service.auth.admin.delete_user(user_id)
        return  # 204 No Content
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(status_code=404, detail="User topilmadi.")
        raise HTTPException(status_code=400, detail=str(e))


# --- AUTH: email/parol bilan login ---
@app.post("/auth/login", response_model=LoginOut)
async def login_email_password(body: LoginIn):
    try:
        res = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password
        })

        session = getattr(res, "session", None)  # Session object
        user = getattr(res, "user", None)        # User object

        if not session or not getattr(session, "access_token", None):
            raise HTTPException(status_code=401, detail="Login muvaffaqiyatsiz.")

        # User obyektini frontend uchun sodda dict ko'rinishiga keltiramiz
        user_out = None
        if user:
            user_out = {
                "id": str(getattr(user, "id", None)),
                "email": getattr(user, "email", None),
                "aud": getattr(user, "aud", None),
                "created_at": getattr(user, "created_at", None),
                "last_sign_in_at": getattr(user, "last_sign_in_at", None),
                "email_confirmed_at": getattr(user, "email_confirmed_at", None),
                "phone": getattr(user, "phone", None),
            }

        return {
            "access_token": session.access_token,
            "token_type": "bearer",
            "expires_in": getattr(session, "expires_in", None),
            "refresh_token": getattr(session, "refresh_token", None),
            "user": user_out,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
    

# --- AUTH: joriy user haqida ma'lumot olish (token bo'yicha) ---
@app.get("/auth/me", response_model=SupabaseUserRaw)
async def get_current_user(authorization: str = Header(..., alias="Authorization")):
    try:
        # 1) Token tekshirish
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=400, detail="Authorization header 'Bearer <token>' bo‘lishi kerak")
        token = authorization.split(" ", 1)[1].strip()

        # 2) Supabase'dan user olish
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Noto‘g‘ri token yoki user topilmadi.")

        user_id = str(_g(user, "id"))

        # 3) app_metadata o‘qish (raw_app_meta_data yoki app_metadata)
        app_meta = _g(user, "raw_app_meta_data") or _g(user, "app_metadata") or {}

        # 3a) plan yo‘q bo‘lsa → default free (idempotent)
        if not app_meta.get("plan"):
            ensure_default_app_metadata(user_id)
            user = supabase_service.auth.admin.get_user_by_id(user_id).user
            app_meta = _g(user, "app_metadata", {})

        # 3b) current_period_end o‘tganmi? → status: expired (plan o‘zgarmaydi)
        cur_end = app_meta.get("current_period_end")
        if cur_end:
            expires = None
            # ISO8601 ("...Z") yoki epoch seconds ikkisini ham qo‘llab-quvvatlaymiz
            try:
                expires = datetime.fromisoformat(str(cur_end).replace("Z", "+00:00"))
            except Exception:
                try:
                    expires = datetime.fromtimestamp(int(cur_end), tz=timezone.utc)
                except Exception:
                    expires = None

            if expires and expires < datetime.now(timezone.utc) and app_meta.get("status") != "expired":
                new_meta = {**app_meta, "status": "expired"}
                supabase_service.auth.admin.update_user_by_id(user_id, {"app_metadata": new_meta})
                user = supabase_service.auth.admin.get_user_by_id(user_id).user  # yangilangan user

        # 4) Qaytarish (SupabaseUserRaw formatiga map)
        def g(obj: Any, name: str, default=None):
            return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)

        return SupabaseUserRaw(
            instance_id=g(user, "instance_id", "00000000-0000-0000-0000-000000000000"),
            id=str(g(user, "id")),
            aud=g(user, "aud"),
            role=g(user, "role"),
            email=g(user, "email"),
            email_confirmed_at=g(user, "email_confirmed_at"),
            invited_at=g(user, "invited_at"),
            confirmation_token=g(user, "confirmation_token", ""),
            confirmation_sent_at=g(user, "confirmation_sent_at"),
            recovery_token=g(user, "recovery_token", ""),
            recovery_sent_at=g(user, "recovery_sent_at"),
            email_change_token_new=g(user, "email_change_token_new", ""),
            email_change=g(user, "email_change", ""),
            email_change_sent_at=g(user, "email_change_sent_at"),
            last_sign_in_at=g(user, "last_sign_in_at"),
            raw_app_meta_data=g(user, "raw_app_meta_data") or g(user, "app_metadata"),
            raw_user_meta_data=g(user, "raw_user_meta_data") or g(user, "user_metadata"),
            is_super_admin=g(user, "is_super_admin"),
            created_at=g(user, "created_at"),
            updated_at=g(user, "updated_at"),
            phone=g(user, "phone"),
            phone_confirmed_at=g(user, "phone_confirmed_at"),
            phone_change=g(user, "phone_change", ""),
            phone_change_token=g(user, "phone_change_token", ""),
            phone_change_sent_at=g(user, "phone_change_sent_at"),
            confirmed_at=g(user, "confirmed_at"),
            email_change_token_current=g(user, "email_change_token_current", ""),
            email_change_confirm_status=g(user, "email_change_confirm_status", 0),
            banned_until=g(user, "banned_until"),
            reauthentication_token=g(user, "reauthentication_token", ""),
            reauthentication_sent_at=g(user, "reauthentication_sent_at"),
            is_sso_user=bool(g(user, "is_sso_user", False)),
            deleted_at=g(user, "deleted_at"),
            is_anonymous=bool(g(user, "is_anonymous", False)),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- YORDAMCHI FUNKSIYA: user uchun default app_metadata ni o'rnatish (faqat plan yo'q bo'lsa) ---
def _g(obj, name, default=None):
    return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)


def ensure_default_app_metadata(user_id: str):
    # Idempotent: faqat plan yo'q bo'lsa yozadi
    from .config import supabase_service
    # hozirgi app_metadata ni o‘qib kelamiz
    cur = supabase_service.auth.admin.get_user_by_id(user_id).user
    app_meta = _g(cur, "app_metadata", {}) or {}
    if app_meta.get("plan"):
        return  # allaqachon bor
    default_meta = {
        "plan": "free",
        "status": "active",
        "accounts_limit": 1,
        "features": {"ai_pro": False},
        "current_period_end": None,
    }
    supabase_service.auth.admin.update_user_by_id(user_id, {"app_metadata": {**app_meta, **default_meta}})

# Telegram apilari -------------------------------------------------------------------------------------------------


# --- TELEGRAM LOGIN STATE (xotirada) ---
# phone_number -> state dict
login_states: dict[str, dict] = {}

def _session_dir_for_user(user_id: str) -> Path:
    d = SESS_ROOT / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _next_index(user_id: str) -> int:
    d = _session_dir_for_user(user_id)
    existing = sorted([int(p.stem.split(".")[0]) for p in d.glob("*.session") if p.stem.split(".")[0].isdigit()])
    return (existing[-1] + 1) if existing else 1


def _build_persistent_client(user_id: str, account_index: int | None):
    sess_dir = _session_dir_for_user(user_id)
    idx = _next_index(user_id) if account_index is None else account_index
    session_name = str(idx)
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    return client, idx, session_name


async def _profile_from_session(sess_dir: Path, session_name: str) -> dict:
    """
    sess_dir: sessions/<user_id>
    session_name: '1', '2', ...
    """
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    try:
        await client.connect()
        me = await client.get_me()
        full_name = " ".join(filter(None, [me.first_name, me.last_name])) or None
        return {
            "index": session_name,
            "full_name": full_name,
            "username": me.username,
            "phone_number": me.phone_number,
            "telegram_id": me.id,
        }
    except Exception:
        # Session yaroqsiz/yopilgan bo‘lishi mumkin — minimal info qaytaramiz
        return {
            "index": session_name,
            "full_name": None,
            "username": None,
            "phone_number": None,
            "telegram_id": None,
            "invalid": True,
        }
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


# --- YORDAMCHI: user_id bo‘yicha hamma Telegram session profilini yig‘ish ---
async def _list_user_telegram_profiles(user_id: str) -> list[dict]:
    sess_dir = SESS_ROOT / user_id
    if not sess_dir.exists():
        return []

    session_names = [p.stem for p in sorted(sess_dir.glob("*.session"), key=lambda x: int(x.stem))]
    tasks = [ _profile_from_session(sess_dir, name) for name in session_names ]
    profiles = await asyncio.gather(*tasks, return_exceptions=False)

    # ixtiyoriy: invalidlarni ham ko‘rsatamiz (agar xohlasangiz filtrlang)
    return profiles


# === YORDAMCHI: bitta sessionni logout qilish ===
async def _logout_one(user_id: str, session_name: str) -> dict:
    sess_dir = SESS_ROOT / user_id
    sess_file = sess_dir / f"{session_name}.session"
    if not sess_file.exists():
        return {"index": session_name, "status": "not_found"}

    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    server_logged_out = False
    try:
        await client.connect()
        try:
            await client.log_out()           # Telegram serveridagi sessiyani ham bekor qiladi
            server_logged_out = True
        except Exception:
            # Agar serverda bekor qilish imkoni bo‘lmasa ham, lokal faylni tozalaymiz
            server_logged_out = False
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    except Exception:
        # Ulanib bo‘lmasa ham lokal faylni o‘chiramiz
        pass

    # Lokal faylni tozalaymiz
    try:
        sess_file.unlink(missing_ok=True)
    except Exception:
        pass

    return {
        "index": session_name,
        "status": "logged_out" if server_logged_out else "file_removed_only"
    }


# === YORDAMCHI: userdagi barcha sessionlarni logistic logout ===
async def _logout_all(user_id: str) -> list[dict]:
    sess_dir = SESS_ROOT / user_id
    if not sess_dir.exists():
        return []
    session_names = [p.stem for p in sess_dir.glob("*.session")]
    if not session_names:
        return []
    results = await asyncio.gather(*[ _logout_one(user_id, name) for name in session_names ])
    return results


# 1) START LOGIN -----------------------------------------------------------------
@app.post("/start_login")
async def start_login(body: StartLoginIn):
    # eski holatni tozalash (xuddi oldingidek)
    if body.phone_number in login_states:
        try:
            old = login_states[body.phone_number].get("client")
            if old:
                try: await old.disconnect()
                except: pass
        finally:
            login_states.pop(body.phone_number, None)

    # MUHIM: account_index=None => _next_index(user_id) avtomatik bo‘ladi
    client, acc_idx, session_name = _build_persistent_client(body.user_id, None)

    try:
        await client.connect()
        sent = await client.send_code(body.phone_number)
    except PhoneNumberInvalid:
        try: await client.disconnect()
        except: pass
        raise HTTPException(400, "Noto‘g‘ri telefon raqam")
    except Exception as e:
        try: await client.disconnect()
        except: pass
        raise HTTPException(500, str(e))

    login_states[body.phone_number] = {
        "user_id": body.user_id,
        "phone_code_hash": sent.phone_code_hash,
        "session_name": session_name,
        "account_index": acc_idx,          # <-- backend hisoblagan indeks
        "client": client,
        "requires_password": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "ok": True,
        "message": "Kod yuborildi",
        "phone_code_hash": sent.phone_code_hash,
        "session_name": session_name,
        "account_index": acc_idx,
    }


# 2) VERIFY CODE -----------------------------------------------------------------
@app.post("/verify_code")
async def verify_code(body: VerifyCodeIn):
    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != body.user_id:
        raise HTTPException(400, "Session user mos emas")

    client: Client = state["client"]
    phone_code_hash: str = state["phone_code_hash"]

    if not phone_code_hash:
        raise HTTPException(400, "phone_code_hash yo‘q. Avval /start_login ni chaqiring.")

    try:
        await client.sign_in(
            phone_number=body.phone_number,
            phone_code_hash=phone_code_hash,
            phone_code=body.code.strip(),
        )
        await client.storage.save()

        session_name = state["session_name"]
        acc_idx = state["account_index"]

        # 2FA yo‘q: state ni tozalab, clientni uzamiz
        del login_states[body.phone_number]
        try: await client.disconnect()
        except: pass

        return {"ok": True, "status": "LOGGED_IN", "session_name": session_name, "account_index": acc_idx}

    except SessionPasswordNeeded:
        state["requires_password"] = True
        # client ochiq qoladi — password kutiladi
        return {"ok": False, "status": "PASSWORD_REQUIRED", "session_name": state["session_name"], "account_index": state["account_index"]}

    except PhoneCodeInvalid:
        raise HTTPException(400, "Noto‘g‘ri kod")

    except Exception as e:
        msg = str(e)
        if "PHONE_CODE_EXPIRED" in msg or "PHONE_CODE_INVALID" in msg:
            raise HTTPException(400, "Kod muddati o‘tdi yoki noto‘g‘ri.")
        raise HTTPException(500, msg)

    finally:
        st = login_states.get(body.phone_number)
        if not st or not st.get("requires_password"):
            try: await client.disconnect()
            except: pass


# 3) VERIFY PASSWORD -------------------------------------------------------------
@app.post("/verify_password")
async def verify_password(body: VerifyPasswordIn):
    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != body.user_id:
        raise HTTPException(400, "Session user mos emas")

    client: Client = state["client"]

    try:
        await client.check_password(body.password)
        await client.storage.save()

        session_name = state["session_name"]
        acc_idx = state["account_index"]

        del login_states[body.phone_number]
        try: await client.disconnect()
        except: pass

        return {
            "ok": True,
            "status": "LOGGED_IN",
            "message": "2FA orqali login qilindi",
            "session_name": session_name,
            "account_index": acc_idx,
        }

    except Exception as e:
        raise HTTPException(400, f"Invalid password: {e}")

    finally:
        st = login_states.get(body.phone_number)
        if not st or not st.get("requires_password"):
            try: await client.disconnect()
            except: pass


# --- ADMIN: barcha userlar va ularning Telegram akkauntlari (profil ma'lumotlari bilan) ---
@app.get("/admin/users-with-telegrams")
async def get_users_with_telegrams():
    """
    Admin: barcha userlar va ularga bog'langan Telegram akkauntlar (profil ma'lumotlari bilan).
    """
    try:
        resp = supabase.rpc("get_users_safe").execute()
        users = resp.data or []

        results = []
        # Profil yig‘ish parallel bo‘lishi uchun coroutine tayyorlaymiz
        async def build_row(u: dict) -> dict:
            uid = u.get("id")
            email = u.get("email")
            phone = u.get("phone")
            telegram_accounts = await _list_user_telegram_profiles(uid)
            return {
                "id": uid,
                "email": email,
                "phone": phone,
                "telegram_accounts": telegram_accounts  # endi har biri dict: index, full_name, username, phone_number, telegram_id
            }

        rows = await asyncio.gather(*[build_row(u) for u in users])
        return {"ok": True, "users": rows}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- USER: o‘zining Telegram akkauntlarini profil ma'lumotlari bilan olish ---
@app.get("/me/telegrams")
async def get_my_telegrams(authorization: str = Header(..., alias="Authorization")):
    """
    User: faqat o‘zining Telegram akkauntlarini profil ma'lumotlari bilan qaytaradi.
    """
    try:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=400, detail="Bearer token kerak")

        token = authorization.split(" ", 1)[1].strip()
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Token noto‘g‘ri")

        uid = str(getattr(user, "id", None))
        email = getattr(user, "email", None)

        telegram_accounts = await _list_user_telegram_profiles(uid)

        return {
            "ok": True,
            "user_id": uid,
            "email": email,
            "telegram_accounts": telegram_accounts
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# 1) Bitta Telegram accountni logout qilish (index bo‘yicha)
@app.delete("/admin/users/{user_id}/telegrams/{index}")
async def admin_logout_one_telegram(user_id: str, index: str):
    """
    Admin: user_id ga tegishli bitta Telegram sessiyani (index) logout qiladi.
    """
    result = await _logout_one(user_id, index)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Session topilmadi")
    return {"ok": True, "result": result}


# 3) User: o‘zining bitta Telegram accountini logout qilish
@app.delete("/me/telegrams/{index}")
async def me_logout_one_telegram(index: str, authorization: str = Header(..., alias="Authorization")):
    """
    User: o‘zining index bo‘yicha Telegram sessiyasini logout qiladi.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Bearer token kerak")
    token = authorization.split(" ", 1)[1].strip()
    res = supabase.auth.get_user(token)
    user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Token noto‘g‘ri")

    user_id = str(getattr(user, "id", None))
    result = await _logout_one(user_id, index)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Session topilmadi")
    return {"ok": True, "result": result}


# 4) User: o‘zining barcha Telegram accountlarini logout qilish
@app.delete("/me/telegrams")
async def me_logout_all_telegrams(authorization: str = Header(..., alias="Authorization")):
    """
    User: o‘zining barcha Telegram sessiyalarini logout qiladi.
    """
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=400, detail="Bearer token kerak")
    token = authorization.split(" ", 1)[1].strip()
    res = supabase.auth.get_user(token)
    user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Token noto‘g‘ri")

    user_id = str(getattr(user, "id", None))
    results = await _logout_all(user_id)
    return {"ok": True, "results": results}


























