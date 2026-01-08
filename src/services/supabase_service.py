import jwt
import time
from datetime import datetime, timezone
from typing import Any
from src.config import supabase, supabase_service, SUPABASE_JWT_SECRET, SUPABASE_ANON_KEY

user_cache = {}

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

    if token in user_cache:
        cached = user_cache[token]
        if time.time() - cached['time'] < 300:  # 5 min cache
            return cached['user']

    try:
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise ValueError("Token noto‘g‘ri")
        user_cache[token] = {'user': user, 'time': time.time()}
        return user
    except Exception as e:
        msg = str(e).lower()
        if "session from session_id claim in jwt does not exist" in msg:
            # Try JWT decoding
            try:
                secret = SUPABASE_JWT_SECRET or SUPABASE_ANON_KEY
                payload = jwt.decode(token, secret, algorithms=["HS256"])
                user_id = payload.get('sub')
                if not user_id:
                    raise ValueError("Token noto'g'ri")
                # Return a simple user object
                class SimpleUser:
                    def __init__(self, id):
                        self.id = id
                user = SimpleUser(user_id)
                user_cache[token] = {'user': user, 'time': time.time()}
                return user
            except jwt.ExpiredSignatureError:
                raise ValueError("Token muddati o'tgan. Qayta login qiling.")
            except jwt.InvalidTokenError:
                raise ValueError("Token noto'g'ri yoki yaroqsiz.")
            except Exception:
                raise ValueError("Token muddati o'tgan yoki sessiya mavjud emas. Qayta login qiling.")
        elif "invalid jwt" in msg or "jwt" in msg:
            raise ValueError("Token noto'g'ri yoki yaroqsiz.")
        else:
            raise ValueError(f"Autentifikatsiya xatosi: {str(e)}")


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