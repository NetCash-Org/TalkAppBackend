
from __future__ import annotations 

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config import API_ID, API_HASH, SESS_ROOT, PENDING_FILE
from pyrogram import Client, enums
import inspect
from pyrogram.enums import ChatType, UserStatus
from pyrogram.errors import RPCError
from src.config import API_ID, API_HASH, SESS_ROOT
from .json_utils import _to_jsonable


# xotiradagi holat: phone_number -> state
login_states: dict[str, dict] = {}

# ---- fayl helperlar ----
def user_dir(user_id: str) -> Path:
    d = SESS_ROOT / user_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def next_index(user_id: str) -> int:
    d = user_dir(user_id)
    existing = sorted([int(p.stem.split(".")[0]) for p in d.glob("*.session") if p.stem.split(".")[0].isdigit()])
    return (existing[-1] + 1) if existing else 1

def session_path(user_id: str, account_index: Optional[int]) -> Path:
    if account_index is None:
        account_index = next_index(user_id)
    return user_dir(user_id) / f"{account_index}.session"

def pending_path(user_id: str) -> Path:
    return user_dir(user_id) / PENDING_FILE

def write_pending(user_id: str, data: dict) -> None:
    pending_path(user_id).write_text(json.dumps(data, ensure_ascii=False, indent=2))

def read_pending(user_id: str) -> dict:
    p = pending_path(user_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}

def clear_pending(user_id: str) -> None:
    p = pending_path(user_id)
    if p.exists():
        p.unlink(missing_ok=True)

# ---- telegram client yaratish ----
def build_client(user_id: str, account_index: int | None):
    sess_dir = user_dir(user_id)
    idx = next_index(user_id) if account_index is None else account_index
    session_name = str(idx)  # .session qo‘shilmaydi
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    return client, idx, session_name




# ---- profil o‘qish ----
async def profile_from_session(sess_dir: Path, session_name: str) -> dict:
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

async def list_user_telegram_profiles(user_id: str) -> list[dict]:
    sess_dir = SESS_ROOT / user_id
    if not sess_dir.exists():
        return []
    session_names = [p.stem for p in sorted(sess_dir.glob("*.session"), key=lambda x: int(x.stem))]
    return await asyncio.gather(*[profile_from_session(sess_dir, name) for name in session_names])

# ---- logout helpers ----
async def logout_one(user_id: str, session_name: str) -> dict:
    sess_dir = SESS_ROOT / user_id
    sess_file = sess_dir / f"{session_name}.session"
    if not sess_file.exists():
        return {"index": session_name, "status": "not_found"}

    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    server_logged_out = False
    try:
        await client.connect()
        try:
            await client.log_out()
            server_logged_out = True
        except Exception:
            server_logged_out = False
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    except Exception:
        pass

    try:
        sess_file.unlink(missing_ok=True)
    except Exception:
        pass

    return {"index": session_name, "status": "logged_out" if server_logged_out else "file_removed_only"}

async def logout_all(user_id: str) -> list[dict]:
    sess_dir = SESS_ROOT / user_id
    if not sess_dir.exists():
        return []
    session_names = [p.stem for p in sess_dir.glob("*.session")]
    if not session_names:
        return []
    return await asyncio.gather(*[logout_one(user_id, name) for name in session_names])



# ---- shaxsiy chatlar ro‘yxati ----


MEDIA_ROOT = Path("media")
AVATAR_DIR = MEDIA_ROOT / "avatars"
DEFAULT_AVATAR_URL = "/media/avatars/default.jpg"

# --- statusni ko'rsatish uchun mapper ---
def status_display(status) -> tuple[Optional[str], bool]:
    """
    last_seen_display (str) va is_online (bool) qaytaradi.
    Privacy tufayli exact datetime bo'lmasligi mumkin.
    """
    # Enum bo‘lsa:
    if isinstance(status, UserStatus):
        if status == UserStatus.ONLINE:
            return ("online", True)
        if status == UserStatus.OFFLINE:
            return ("offline", False)
        if status == UserStatus.RECENTLY:
            return ("recently", False)
        if status == UserStatus.LAST_WEEK:
            return ("last_week", False)
        if status == UserStatus.LAST_MONTH:
            return ("last_month", False)
        if status == UserStatus.LONG_AGO:
            return ("long_ago", False)
        return (None, False)

    # Obyekt bo‘lsa (ba'zi buildlarda bo‘lishi mumkin)
    disp = None
    online = bool(getattr(status, "online", False))
    was_online = getattr(status, "was_online", None)
    if online:
        disp = "online"
    elif was_online:
        try:
            disp = was_online.isoformat()
        except Exception:
            disp = str(was_online)
    return (disp, online)


async def ensure_user_avatar_downloaded(
    user_id: str,
    account_index: int,
    chat_id: int,
    force: bool = False,
    prefer_small: bool = True,   # <-- yangi: kichik faylni afzal ko‘ramiz (tezroq)
) -> Optional[str]:
    dest = _avatar_file(user_id, account_index, chat_id)
    if dest.exists() and not force:
        return f"/media/avatars/{user_id}/{account_index}/{chat_id}.jpg"

    client = build_client_for(user_id, account_index)
    await client.connect()
    try:
        chat = await client.get_chat(chat_id)
        if not chat or chat.type != ChatType.PRIVATE or not getattr(chat, "photo", None):
            return None

        # Tezlik uchun avval small, bo‘lmasa big
        file_id = None
        if prefer_small:
            file_id = getattr(chat.photo, "small_file_id", None) or getattr(chat.photo, "big_file_id", None)
        else:
            file_id = getattr(chat.photo, "big_file_id", None) or getattr(chat.photo, "small_file_id", None)
        if not file_id:
            return None

        dest.parent.mkdir(parents=True, exist_ok=True)
        await client.download_media(file_id, file_name=str(dest))
        return f"/media/avatars/{user_id}/{account_index}/{chat_id}.jpg" if dest.exists() else None
    except RPCError:
        return None
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

def build_client_for(user_id: str, account_index: int) -> Client:
    sess_dir = Path(SESS_ROOT) / user_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    session_name = str(account_index)
    return Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))

def _avatar_file(user_id: str, account_index: int, chat_id: int) -> Path:
    d = AVATAR_DIR / user_id / str(account_index)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{chat_id}.jpg"

def _status_to_last_seen_and_online(status_obj) -> tuple[Optional[str], bool]:
    """
    Pyrogram 2.x da User.status ko‘pincha enum (UserStatus.*). was_online hamma joyda bo‘lmasligi mumkin.
    Shuning uchun soddalashtiramiz:
    - ONLINE bo‘lsa: is_online=True
    - Agar LastSeen xususiyati yo‘q bo‘lsa: last_seen=None
    """
    is_online = False
    last_seen = None

    # Enum bo‘lsa:
    if isinstance(status_obj, UserStatus):
        # ONLINE enumini tekshiramiz
        if status_obj == UserStatus.ONLINE:
            is_online = True
        # boshqa holatlarda last_seen aniq emas, None qoldiramiz
        return last_seen, is_online

    # Ba’zi buildlarda obyekt bo‘lishi mumkin (was_online mavjud bo‘lsa)
    if hasattr(status_obj, "was_online") and status_obj.was_online:
        try:
            # datetime bo‘lsa stringga
            last_seen = status_obj.was_online.isoformat()
        except Exception:
            last_seen = str(status_obj.was_online)
    if hasattr(status_obj, "online"):
        try:
            is_online = bool(status_obj.online)
        except Exception:
            pass

    return last_seen, is_online


async def list_private_chats_minimal(user_id: str, account_index: int, limit: int = 10) -> List[Dict[str, Any]]:
    client = build_client_for(user_id, account_index)
    await client.connect()
    out: List[Dict[str, Any]] = []
    try:
        async for dialog in client.get_dialogs(limit=limit):
            chat = dialog.chat
            if not chat or chat.type != ChatType.PRIVATE:
                continue

            # user obyektini olish (status ko'pincha shu yerda to'liqroq bo'ladi)
            user_obj = None
            try:
                user_obj = await client.get_users(chat.id)
            except Exception:
                pass

            full_name = " ".join(filter(None, [chat.first_name, chat.last_name])) or None
            username = chat.username

            last_seen_disp, is_online = status_display(getattr(user_obj, "status", None) or getattr(chat, "status", None))

            # avatar
            photo_url = None
            has_photo = bool(getattr(chat, "photo", None))
            if has_photo:
                try:
                    photo_url = await ensure_user_avatar_downloaded(
                        user_id=user_id,
                        account_index=account_index,
                        chat_id=chat.id,
                        force=False,
                        prefer_small=True,
                    )
                except Exception:
                    photo_url = None

            if not photo_url:
                photo_url = DEFAULT_AVATAR_URL

            out.append({
                "id": chat.id,
                "full_name": full_name,
                "username": username,
                "last_seen": last_seen_disp,   # endi enum label yoki isoformat string
                "is_online": is_online,
                "has_photo": has_photo,
                "photo_url": photo_url,
            })
        return out
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass







