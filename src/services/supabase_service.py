from datetime import datetime, timezone
from typing import Any
from src.config import supabase, supabase_service

def g(obj: Any, name: str, default=None):
    return getattr(obj, name, default) if not isinstance(obj, dict) else obj.get(name, default)

def ensure_default_app_metadata(user_id: str):
    cur = supabase_service.auth.admin.get_user_by_id(user_id).user
    app_meta = g(cur, "app_metadata", {}) or {}
    if app_meta.get("plan"):
        return
    default_meta = {
        "plan": "free",
        "status": "active",
        "accounts_limit": 1,
        "features": {"ai_pro": False},
        "current_period_end": None,
    }
    supabase_service.auth.admin.update_user_by_id(user_id, {"app_metadata": {**app_meta, **default_meta}})

def get_user_from_token(authorization: str):
    if not authorization.lower().startswith("bearer "):
        raise ValueError("Bearer token kerak")
    token = authorization.split(" ", 1)[1].strip()
    res = supabase.auth.get_user(token)
    user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
    if not user:
        raise ValueError("Token noto‘g‘ri")
    return user


def get_user_by_token(token: str):
    try:
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            print("[AUTH] get_user_by_token: user = None")
            return None
        print("[AUTH] token user_id =", getattr(user, "id", None))
        return user
    except Exception as e:
        print("[AUTH] get_user_by_token error:", e)
        return None