import asyncio
from fastapi import APIRouter, HTTPException, Header, Query, Path
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid
from src.models.user import StartLoginIn, StartLoginInNew, VerifyCodeIn, VerifyCodeInNew, VerifyPasswordIn, VerifyPasswordInNew
from src.services.telegram_service import (
    login_states, build_client, list_user_telegram_profiles,
    logout_one, logout_all, ensure_user_avatar_downloaded, list_private_chats_minimal, list_groups_minimal
)
from src.services.supabase_service import get_user_from_token, get_user_by_token
from src.config import supabase
from typing import Optional



router = APIRouter()

# 1) START LOGIN
@router.post("/start_login")
async def start_login(body: StartLoginInNew, authorization: str = Header(..., alias="Authorization")):
    # Get user from token
    try:
        user = get_user_from_token(authorization)
        user_id = str(getattr(user, "id"))
    except ValueError as e:
        msg = str(e).lower()
        if "bearer" in msg:
            raise HTTPException(400, "Authorization header noto'g'ri formatda. Bearer <token> bo'lishi kerak.")
        elif "token" in msg:
            raise HTTPException(400, "Token noto'g'ri yoki muddati o'tgan. Qayta login qiling.")
        else:
            raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")

    # eski holatni tozalash
    if body.phone_number in login_states:
        try:
            old = login_states[body.phone_number].get("client")
            if old:
                try: await old.disconnect()
                except: pass
        finally:
            login_states.pop(body.phone_number, None)

    # AUTOINDEX: backend hisoblaydi (body.account_index e'tiborga olinmaydi)
    client, acc_idx, session_name = build_client(user_id, None)

    try:
        await client.connect()
        sent = await client.send_code(body.phone_number)
    except PhoneNumberInvalid:
        try: await client.disconnect()
        except: pass
        raise HTTPException(400, "Noto‘g‘ri telefon raqam formati. Telefon raqam +998... formatida bo‘lishi kerak.")
    except Exception as e:
        msg = str(e).lower()
        try: await client.disconnect()
        except: pass
        if "flood" in msg:
            raise HTTPException(429, "Juda ko'p so'rov yuborildi. Bir necha daqiqa kutib turing.")
        elif "network" in msg:
            raise HTTPException(500, "Tarmoq xatosi. Internet ulanishini tekshiring.")
        else:
            raise HTTPException(500, f"Telegram server xatosi: {str(e)}")

    login_states[body.phone_number] = {
        "user_id": user_id,
        "phone_code_hash": sent.phone_code_hash,
        "session_name": session_name,
        "account_index": acc_idx,
        "client": client,
        "requires_password": False,
    }

    return {
        "ok": True,
        "message": "Kod yuborildi",
        "phone_code_hash": sent.phone_code_hash,
        "session_name": session_name,
        "account_index": acc_idx,
    }

# 2) VERIFY CODE
@router.post("/verify_code")
async def verify_code(body: VerifyCodeInNew, authorization: str = Header(..., alias="Authorization")):
    # Get user from token
    try:
        user = get_user_from_token(authorization)
        user_id = str(getattr(user, "id"))
    except ValueError as e:
        msg = str(e).lower()
        if "bearer" in msg:
            raise HTTPException(400, "Authorization header noto'g'ri formatda. Bearer <token> bo'lishi kerak.")
        elif "token" in msg:
            raise HTTPException(400, "Token noto'g'ri yoki muddati o'tgan. Qayta login qiling.")
        else:
            raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")

    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != user_id:
        raise HTTPException(400, "Session user mos emas")

    client = state["client"]
    phone_code_hash = state["phone_code_hash"]
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

        del login_states[body.phone_number]
        try: await client.disconnect()
        except: pass

        return {"ok": True, "status": "LOGGED_IN", "session_name": session_name, "account_index": acc_idx}

    except SessionPasswordNeeded:
        state["requires_password"] = True
        return {"ok": False, "status": "PASSWORD_REQUIRED",
                "session_name": state["session_name"], "account_index": state["account_index"]}

    except PhoneCodeInvalid:
        raise HTTPException(400, "Noto‘g‘ri kod. Kodni to‘g‘ri kiriting.")

    except Exception as e:
        msg = str(e).lower()
        if "phone_code_expired" in msg or "phone_code_invalid" in msg:
            raise HTTPException(400, "Kod muddati o‘tdi. Yangi kod so‘rang.")
        elif "flood" in msg:
            raise HTTPException(429, "Juda ko'p urinish. Bir necha daqiqa kutib turing.")
        elif "network" in msg:
            raise HTTPException(500, "Tarmoq xatosi. Internet ulanishini tekshiring.")
        else:
            raise HTTPException(500, f"Telegram server xatosi: {str(e)}")

    finally:
        st = login_states.get(body.phone_number)
        if not st or not st.get("requires_password"):
            try: await client.disconnect()
            except: pass

# 3) VERIFY PASSWORD (2FA)
@router.post("/verify_password")
async def verify_password(body: VerifyPasswordInNew, authorization: str = Header(..., alias="Authorization")):
    # Get user from token
    try:
        user = get_user_from_token(authorization)
        user_id = str(getattr(user, "id"))
    except ValueError as e:
        msg = str(e).lower()
        if "bearer" in msg:
            raise HTTPException(400, "Authorization header noto'g'ri formatda. Bearer <token> bo'lishi kerak.")
        elif "token" in msg:
            raise HTTPException(400, "Token noto'g'ri yoki muddati o'tgan. Qayta login qiling.")
        else:
            raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")

    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != user_id:
        raise HTTPException(400, "Session user mos emas")

    client = state["client"]
    try:
        await client.check_password(body.password)
        await client.storage.save()

        session_name = state["session_name"]
        acc_idx = state["account_index"]

        del login_states[body.phone_number]
        try: await client.disconnect()
        except: pass

        return {"ok": True, "status": "LOGGED_IN", "message": "2FA orqali login qilindi",
                "session_name": session_name, "account_index": acc_idx}
    except Exception as e:
        msg = str(e).lower()
        if "password" in msg and ("invalid" in msg or "wrong" in msg):
            raise HTTPException(400, "Noto‘g‘ri parol. Parolni to‘g‘ri kiriting.")
        elif "flood" in msg:
            raise HTTPException(429, "Juda ko'p urinish. Bir necha daqiqa kutib turing.")
        elif "network" in msg:
            raise HTTPException(500, "Tarmoq xatosi. Internet ulanishini tekshiring.")
        else:
            raise HTTPException(400, f"Parol tekshirishda xatolik: {str(e)}")
    finally:
        st = login_states.get(body.phone_number)
        if not st or not st.get("requires_password"):
            try: await client.disconnect()
            except: pass

# --- Admin: barcha userlar Telegramlari (profil bilan)
@router.get("/admin/users-with-telegrams")
async def get_users_with_telegrams():
    from src.config import supabase_service
    try:
        resp = supabase_service.auth.admin.list_users()
        users = []
        for user in resp:
            # Map to safe user data
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "phone": getattr(user, 'phone', None),
            }
            users.append(user_data)

        async def build_row(u: dict) -> dict:
            uid = u.get("id")
            email = u.get("email")
            phone = u.get("phone")
            telegram_accounts = await list_user_telegram_profiles(uid)
            return {"id": uid, "email": email, "phone": phone, "telegram_accounts": telegram_accounts}

        rows = await asyncio.gather(*[build_row(u) for u in users])
        return {"ok": True, "users": rows}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- User: o‘z Telegram profil(lar)i
@router.get("/me/telegrams")
async def get_my_telegrams(authorization: str = Header(..., alias="Authorization")):
    from src.services.supabase_service import g
    try:
        user = get_user_from_token(authorization)
        uid = str(g(user, "id"))
        email = g(user, "email")
        telegram_accounts = await list_user_telegram_profiles(uid)
        return {"ok": True, "user_id": uid, "email": email, "telegram_accounts": telegram_accounts}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(400, str(e))

# --- Admin: bitta sessiyani logout
@router.delete("/admin/users/{user_id}/telegrams/{index}")
async def admin_logout_one_telegram(user_id: str, index: str):
    result = await logout_one(user_id, index)
    if result["status"] == "not_found":
        raise HTTPException(404, "Session topilmadi")
    return {"ok": True, "result": result}

# --- User: bitta sessiyani logout
@router.delete("/me/telegrams/{index}")
async def me_logout_one_telegram(index: str, authorization: str = Header(..., alias="Authorization")):
    from src.services.supabase_service import g
    try:
        user = get_user_from_token(authorization)
        uid = str(g(user, "id"))
        result = await logout_one(uid, index)
        if result["status"] == "not_found":
            raise HTTPException(404, "Session topilmadi")
        return {"ok": True, "result": result}
    except ValueError as e:
        raise HTTPException(400, str(e))

# --- User: hamma sessiyalarni logout
@router.delete("/me/telegrams")
async def me_logout_all_telegrams(authorization: str = Header(..., alias="Authorization")):
    from src.services.supabase_service import g
    try:
        user = get_user_from_token(authorization)
        uid = str(g(user, "id"))
        results = await logout_all(uid)
        return {"ok": True, "results": results}
    except ValueError as e:
        raise HTTPException(400, str(e))






# ---- shaxsiy chatlar ro‘yxati ----
@router.get("/me/private_chats/{session_index}")
async def list_private_chats(
    session_index: int = Path(...),
    authorization: str = Header(..., alias="Authorization"),
    dialog_limit: int = Query(10, ge=1, le=100),
):
    try:
        user = get_user_from_token(authorization)
        user_id = str(getattr(user, "id"))
    except ValueError as e:
        raise HTTPException(401, str(e))

    items = await list_private_chats_minimal(
        user_id=user_id,
        account_index=session_index,
        limit=dialog_limit
    )
    return {"ok": True, "count": len(items), "items": items}


# ---- guruhlar ro‘yxati ----
@router.get("/me/groups/{session_index}")
async def list_groups(
    session_index: int = Path(...),
    authorization: str = Header(..., alias="Authorization"),
    dialog_limit: int = Query(10, ge=1, le=100),
):
    try:
        user = get_user_from_token(authorization)
        user_id = str(getattr(user, "id"))
    except ValueError as e:
        raise HTTPException(401, str(e))

    items = await list_groups_minimal(
        user_id=user_id,
        account_index=session_index,
        limit=dialog_limit
    )
    return {"ok": True, "count": len(items), "items": items}
