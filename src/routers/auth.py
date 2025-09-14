from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Path, Header
from src.config import supabase, supabase_service
from src.models.user import (
    LoginIn, LoginOut, UserSafe, UserAdmin, UserCreate, UserOut, UserUpdate, SupabaseUserRaw
)
from src.services.supabase_service import ensure_default_app_metadata, g

router = APIRouter()

@router.get("/check")
async def check_connection():
    try:
        _ = supabase.rpc("get_users_safe").execute()
        return {"message": "Supabase'ga ulanildi", "status": "success"}
    except Exception as e:
        raise HTTPException(500, f"Ulanish xatosi: {str(e)}")

@router.get("/users", response_model=list[UserSafe])
async def get_users():
    try:
        resp = supabase.rpc("get_users_safe").execute()
        return [UserSafe(**row) for row in resp.data or []]
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/admin/users", response_model=list[UserAdmin])
async def get_users_admin():
    try:
        resp = supabase.rpc("get_users_admin").execute()
        return [UserAdmin(**row) for row in resp.data or []]
    except Exception as e:
        raise HTTPException(500, str(e))

@router.post("/admin/users", response_model=UserOut, status_code=201)
async def create_user(payload: UserCreate):
    try:
        req = {
            "email": payload.email,
            "password": payload.password,
            "user_metadata": payload.user_metadata or {}
        }
        res = supabase_service.auth.admin.create_user(req)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(500, "User yaratildi, lekin javobni o‘qib bo‘lmadi.")
        return UserOut(id=str(user.id), email=user.email)
    except Exception as e:
        raise HTTPException(400, str(e))

@router.patch("/admin/users/{user_id}", response_model=UserOut)
async def admin_update_user(user_id: str = Path(...), payload: UserUpdate = ...):
    try:
        if not any([payload.email, payload.password, payload.phone, payload.user_metadata, payload.app_metadata,
                    payload.email_confirm is not None, payload.phone_confirm is not None, payload.ban_duration]):
            raise HTTPException(422, "Hech qanday o‘zgartiriladigan maydon berilmagan.")

        attrs = {}
        if payload.email is not None: attrs["email"] = payload.email
        if payload.password is not None: attrs["password"] = payload.password
        if payload.phone is not None: attrs["phone"] = payload.phone
        if payload.user_metadata is not None: attrs["user_metadata"] = payload.user_metadata
        if payload.app_metadata is not None: attrs["app_metadata"] = payload.app_metadata
        if payload.email_confirm is not None: attrs["email_confirm"] = payload.email_confirm
        if payload.phone_confirm is not None: attrs["phone_confirm"] = payload.phone_confirm
        if payload.ban_duration is not None: attrs["ban_duration"] = payload.ban_duration

        res = supabase_service.auth.admin.update_user_by_id(user_id, attrs)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(404, "User topilmadi yoki yangilanmadi.")
        return UserOut(id=str(user.id), email=user.email)
    except Exception as e:
        msg = str(e).lower()
        if "invalid email" in msg:
            raise HTTPException(422, "Email noto‘g‘ri.")
        if "password" in msg and "length" in msg:
            raise HTTPException(422, "Parol eng kamida 6 belgidan iborat bo‘lsin.")
        if "not found" in msg:
            raise HTTPException(404, "User topilmadi.")
        raise HTTPException(400, str(e))

@router.delete("/admin/users/{user_id}", status_code=204)
async def admin_delete_user(user_id: str = Path(...)):
    try:
        supabase_service.auth.admin.delete_user(user_id)
        return
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg:
            raise HTTPException(404, "User topilmadi.")
        raise HTTPException(400, str(e))

@router.post("/auth/login", response_model=LoginOut)
async def login_email_password(body: LoginIn):
    try:
        res = supabase.auth.sign_in_with_password({"email": body.email, "password": body.password})
        session = getattr(res, "session", None)
        user = getattr(res, "user", None)
        if not session or not getattr(session, "access_token", None):
            raise HTTPException(401, "Login muvaffaqiyatsiz.")
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
        raise HTTPException(401, str(e))

@router.get("/auth/me", response_model=SupabaseUserRaw)
async def get_current_user(authorization: str = Header(..., alias="Authorization")):
    try:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(400, "Authorization header 'Bearer <token>' bo‘lishi kerak")
        token = authorization.split(" ", 1)[1].strip()
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(401, "Noto‘g‘ri token yoki user topilmadi.")
        user_id = str(g(user, "id"))
        app_meta = g(user, "raw_app_meta_data") or g(user, "app_metadata") or {}
        if not app_meta.get("plan"):
            ensure_default_app_metadata(user_id)
            user = supabase_service.auth.admin.get_user_by_id(user_id).user
            app_meta = g(user, "app_metadata", {})
        cur_end = app_meta.get("current_period_end")
        if cur_end:
            from datetime import datetime, timezone
            expires = None
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
                user = supabase_service.auth.admin.get_user_by_id(user_id).user
        def _g(obj, name, default=None):
            return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)
        return SupabaseUserRaw(
            instance_id=_g(user, "instance_id", "00000000-0000-0000-0000-000000000000"),
            id=str(_g(user, "id")),
            aud=_g(user, "aud"),
            role=_g(user, "role"),
            email=_g(user, "email"),
            email_confirmed_at=_g(user, "email_confirmed_at"),
            invited_at=_g(user, "invited_at"),
            confirmation_token=_g(user, "confirmation_token", ""),
            confirmation_sent_at=_g(user, "confirmation_sent_at"),
            recovery_token=_g(user, "recovery_token", ""),
            recovery_sent_at=_g(user, "recovery_sent_at"),
            email_change_token_new=_g(user, "email_change_token_new", ""),
            email_change=_g(user, "email_change", ""),
            email_change_sent_at=_g(user, "email_change_sent_at"),
            last_sign_in_at=_g(user, "last_sign_in_at"),
            raw_app_meta_data=_g(user, "raw_app_meta_data") or _g(user, "app_metadata"),
            raw_user_meta_data=_g(user, "raw_user_meta_data") or _g(user, "user_metadata"),
            is_super_admin=_g(user, "is_super_admin"),
            created_at=_g(user, "created_at"),
            updated_at=_g(user, "updated_at"),
            phone=_g(user, "phone"),
            phone_confirmed_at=_g(user, "phone_confirmed_at"),
            phone_change=_g(user, "phone_change", ""),
            phone_change_token=_g(user, "phone_change_token", ""),
            phone_change_sent_at=_g(user, "phone_change_sent_at"),
            confirmed_at=_g(user, "confirmed_at"),
            email_change_token_current=_g(user, "email_change_token_current", ""),
            email_change_confirm_status=_g(user, "email_change_confirm_status", 0),
            banned_until=_g(user, "banned_until"),
            reauthentication_token=_g(user, "reauthentication_token", ""),
            reauthentication_sent_at=_g(user, "reauthentication_sent_at"),
            is_sso_user=bool(_g(user, "is_sso_user", False)),
            deleted_at=_g(user, "deleted_at"),
            is_anonymous=bool(_g(user, "is_anonymous", False)),
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, str(e))