import asyncio
from fastapi import APIRouter, HTTPException, Header, Path
from pyrogram.errors import SessionPasswordNeeded, PhoneCodeInvalid, PhoneNumberInvalid
from src.models.user import StartLoginIn, VerifyCodeIn, VerifyPasswordIn
from src.services.telegram_service import (
    login_states, build_client, list_user_telegram_profiles,
    logout_one, logout_all
)
from src.services.supabase_service import get_user_from_token

router = APIRouter()

# 1) START LOGIN
@router.post("/start_login")
async def start_login(body: StartLoginIn):
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
    client, acc_idx, session_name = build_client(body.user_id, None)

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
async def verify_code(body: VerifyCodeIn):
    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != body.user_id:
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

# 3) VERIFY PASSWORD (2FA)
@router.post("/verify_password")
async def verify_password(body: VerifyPasswordIn):
    state = login_states.get(body.phone_number)
    if not state:
        raise HTTPException(404, "Login session topilmadi")
    if state["user_id"] != body.user_id:
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
        raise HTTPException(400, f"Invalid password: {e}")
    finally:
        st = login_states.get(body.phone_number)
        if not st or not st.get("requires_password"):
            try: await client.disconnect()
            except: pass

# --- Admin: barcha userlar Telegramlari (profil bilan)
@router.get("/admin/users-with-telegrams")
async def get_users_with_telegrams():
    from src.config import supabase
    try:
        resp = supabase.rpc("get_users_safe").execute()
        users = resp.data or []

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