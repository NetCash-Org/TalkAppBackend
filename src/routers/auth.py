from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Path, Header
from typing import Optional
from src.config import supabase, supabase_service
from src.models.user import (
    LoginIn, LoginOut, UserSafe, UserAdmin, UserCreate, UserOut, UserUpdate, SupabaseUserRaw
)
from src.services.supabase_service import ensure_default_app_metadata, g

router = APIRouter()

@router.get("/check")
async def check_connection():
    try:
        # Test connection by trying to list users (will check if admin access works)
        _ = supabase_service.auth.admin.list_users()
        return {"message": "Supabase'ga ulanildi", "status": "success"}
    except Exception as e:
        raise HTTPException(500, f"Ulanish xatosi: {str(e)}")

@router.get("/users", response_model=list[UserSafe])
async def get_users():
    try:
        resp = supabase_service.auth.admin.list_users()
        users = []
        for user in resp:
            # Map admin user data to UserSafe model
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "phone": getattr(user, 'phone', None),
                "created_at": user.created_at,
                "last_sign_in_at": getattr(user, 'last_sign_in_at', None),
                "confirmed_at": getattr(user, 'email_confirmed_at', None),
                "is_anonymous": getattr(user, 'is_anonymous', False),
                "raw_app_meta_data": getattr(user, 'app_metadata', None) or getattr(user, 'raw_app_meta_data', None),
                "raw_user_meta_data": getattr(user, 'user_metadata', None) or getattr(user, 'raw_user_meta_data', None),
            }
            users.append(UserSafe(**user_data))
        return users
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/admin/users", response_model=list[UserAdmin])
async def get_users_admin():
    try:
        resp = supabase_service.auth.admin.list_users()
        users = []
        for user in resp:
            # Map full admin user data to UserAdmin model
            user_data = {
                "instance_id": getattr(user, 'instance_id', None),
                "id": str(user.id),
                "aud": getattr(user, 'aud', None),
                "role": getattr(user, 'role', None),
                "email": user.email,
                "email_confirmed_at": getattr(user, 'email_confirmed_at', None),
                "invited_at": getattr(user, 'invited_at', None),
                "confirmation_token": getattr(user, 'confirmation_token', ''),
                "confirmation_sent_at": getattr(user, 'confirmation_sent_at', None),
                "recovery_token": getattr(user, 'recovery_token', ''),
                "recovery_sent_at": getattr(user, 'recovery_sent_at', None),
                "email_change_token_new": getattr(user, 'email_change_token_new', ''),
                "email_change": getattr(user, 'email_change', ''),
                "email_change_sent_at": getattr(user, 'email_change_sent_at', None),
                "last_sign_in_at": getattr(user, 'last_sign_in_at', None),
                "raw_app_meta_data": getattr(user, 'app_metadata', None) or getattr(user, 'raw_app_meta_data', None),
                "raw_user_meta_data": getattr(user, 'user_metadata', None) or getattr(user, 'raw_user_meta_data', None),
                "is_super_admin": getattr(user, 'is_super_admin', None),
                "created_at": user.created_at,
                "updated_at": getattr(user, 'updated_at', None),
                "phone": getattr(user, 'phone', None),
                "phone_confirmed_at": getattr(user, 'phone_confirmed_at', None),
                "phone_change": getattr(user, 'phone_change', ''),
                "phone_change_token": getattr(user, 'phone_change_token', ''),
                "phone_change_sent_at": getattr(user, 'phone_change_sent_at', None),
                "confirmed_at": getattr(user, 'confirmed_at', None),
                "email_change_token_current": getattr(user, 'email_change_token_current', ''),
                "email_change_confirm_status": getattr(user, 'email_change_confirm_status', 0),
                "banned_until": getattr(user, 'banned_until', None),
                "reauthentication_token": getattr(user, 'reauthentication_token', ''),
                "reauthentication_sent_at": getattr(user, 'reauthentication_sent_at', None),
                "is_sso_user": bool(getattr(user, 'is_sso_user', False)),
                "deleted_at": getattr(user, 'deleted_at', None),
                "is_anonymous": bool(getattr(user, 'is_anonymous', False)),
            }
            users.append(UserAdmin(**user_data))
        return users
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

@router.post("/admin/users/{user_id}/set-admin")
async def set_user_admin(user_id: str = Path(...), is_admin: bool = True):
    """Set or remove admin role for a user"""
    try:
        # Get current user metadata
        user_res = supabase_service.auth.admin.get_user_by_id(user_id)
        current_user = user_res.user
        if not current_user:
            raise HTTPException(404, "User topilmadi.")

        current_meta = getattr(current_user, "app_metadata", {}) or {}

        # Update metadata
        new_meta = {**current_meta, "role": "admin" if is_admin else "user"}

        res = supabase_service.auth.admin.update_user_by_id(user_id, {"app_metadata": new_meta})
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(404, "User yangilanmadi.")

        return {"message": f"User {'admin' if is_admin else 'user'} ga o'zgartirildi.", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
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

@router.post("/auth/logout")
async def logout(authorization: str = Header(..., alias="Authorization")):
    try:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(400, "Authorization header 'Bearer <token>' bo‘lishi kerak")
        token = authorization.split(" ", 1)[1].strip()
        # Sign out the user
        supabase.auth.sign_out()
        return {"message": "Logout muvaffaqiyatli"}
    except Exception as e:
        raise HTTPException(400, str(e))

@router.get("/admin/audit-logs")
async def get_audit_logs(
    authorization: str = Header(..., alias="Authorization"),
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    offset: int = 0
):
    try:
        # Verify admin access
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(400, "Authorization header 'Bearer <token>' bo‘lishi kerak")
        token = authorization.split(" ", 1)[1].strip()
        try:
            res = supabase.auth.get_user(token)
            user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
            if not user:
                raise HTTPException(401, "Noto‘g‘ri token")
        except HTTPException:
            raise
        except Exception as e:
            msg = str(e).lower()
            if "session from session_id claim in jwt does not exist" in msg:
                raise HTTPException(400, "Token muddati o'tgan yoki sessiya mavjud emas. Qayta login qiling.")
            elif "invalid jwt" in msg or "jwt" in msg:
                raise HTTPException(400, "Token noto'g'ri yoki yaroqsiz.")
            else:
                raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")
        app_meta = getattr(user, "raw_app_meta_data", None) or getattr(user, "app_metadata", None) or {}
        is_super_admin = getattr(user, "is_super_admin", False)
        is_admin = app_meta.get("role") == "admin" or is_super_admin
        if not is_admin:
            raise HTTPException(403, "Faqat adminlar uchun")

        # Read from in-memory storage
        from src.middleware.audit_logging import audit_logs_memory

        # Filter logs
        filtered_logs = list(audit_logs_memory)

        # Apply filters
        if user_id:
            filtered_logs = [log for log in filtered_logs if log.get("user_id") == user_id]
        if action:
            filtered_logs = [log for log in filtered_logs if log.get("action") == action]
        if start_date:
            filtered_logs = [log for log in filtered_logs if log.get("timestamp", "") >= start_date]
        if end_date:
            filtered_logs = [log for log in filtered_logs if log.get("timestamp", "") <= end_date]

        # Sort by timestamp descending
        filtered_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        # Apply pagination
        total = len(filtered_logs)
        logs = filtered_logs[offset:offset + limit]

        return {
            "logs": logs,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@router.get("/auth/me", response_model=SupabaseUserRaw)
async def get_current_user(authorization: str = Header(..., alias="Authorization")):
    try:
        if not authorization.lower().startswith("bearer "):
            raise HTTPException(400, "Authorization header 'Bearer <token>' bo‘lishi kerak")
        token = authorization.split(" ", 1)[1].strip()
        try:
            res = supabase.auth.get_user(token)
            user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
            if not user:
                raise HTTPException(401, "Noto‘g‘ri token yoki user topilmadi.")
        except Exception as e:
            msg = str(e).lower()
            if "session from session_id claim in jwt does not exist" in msg:
                raise HTTPException(400, "Token muddati o'tgan yoki sessiya mavjud emas. Qayta login qiling.")
            elif "invalid jwt" in msg or "jwt" in msg:
                raise HTTPException(400, "Token noto'g'ri yoki yaroqsiz.")
            else:
                raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")
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