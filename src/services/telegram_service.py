
from __future__ import annotations

import json
import asyncio
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config import API_ID, API_HASH, SESS_ROOT, PENDING_FILE, BASE_URL
from pyrogram import Client, enums
import inspect
from pyrogram.enums import ChatType, UserStatus
from pyrogram.errors import RPCError,PeerIdInvalid
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
async def profile_from_session(user_id: str, account_index: int) -> dict:
    sess_dir = SESS_ROOT / user_id
    session_name = str(account_index)
    client = Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))
    try:
        await client.connect()
        me = await client.get_me()
        full_name = " ".join(filter(None, [me.first_name, me.last_name])) or None

        # Get profile picture
        photo_url = None
        try:
            if getattr(me, "photo", None):
                file_id = me.photo.big_file_id
                dest = _avatar_file(user_id, account_index, me.id)
                if not dest.exists():
                    data = await client.download_media(file_id, in_memory=True)
                    if data:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with open(dest, 'wb') as f:
                            f.write(data.getvalue())
                if dest.exists():
                    photo_url = f"/media/avatars/{user_id}/{account_index}/{me.id}.jpg"
        except Exception:
            pass

        return {
            "index": session_name,
            "full_name": full_name,
            "username": me.username,
            "phone_number": me.phone_number,
            "telegram_id": me.id,
            "profile_picture": photo_url,
            "profile_url": f"https://t.me/{me.username}" if me.username else None,
        }
    except Exception:
        return {
            "index": session_name,
            "full_name": None,
            "username": None,
            "phone_number": None,
            "telegram_id": None,
            "invalid": True,
            "profile_picture": None,
            "profile_url": None,
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

    # Limit concurrent connections to avoid overwhelming Telegram
    semaphore = asyncio.Semaphore(4)

    async def process_session(name):
        async with semaphore:
            return await profile_from_session(user_id, int(name))

    return await asyncio.gather(*[process_session(name) for name in session_names])

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

    # Delete associated avatar directory
    avatar_dir = AVATAR_DIR / user_id / session_name
    if avatar_dir.exists():
        try:
            shutil.rmtree(avatar_dir)
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
            chat = await client.get_chat(dialog.chat.id)
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
                    dest = _avatar_file(user_id, account_index, chat.id)
                    if not dest.exists():
                        file_id = getattr(chat.photo, "small_file_id", None) or getattr(chat.photo, "big_file_id", None)
                        if file_id:
                            data = await client.download_media(file_id, in_memory=True)
                            if data:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with open(dest, 'wb') as f:
                                    f.write(data.getvalue())
                    if dest.exists():
                        photo_url = f"/media/avatars/{user_id}/{account_index}/{chat.id}.jpg"
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


async def list_groups_minimal(user_id: str, account_index: int, limit: int = 10) -> List[Dict[str, Any]]:
    client = build_client_for(user_id, account_index)
    await client.connect()
    out: List[Dict[str, Any]] = []
    try:
        async for dialog in client.get_dialogs(limit=limit):
            chat = await client.get_chat(dialog.chat.id)
            if not chat or chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
                continue

            title = chat.title
            username = chat.username

            # Get member count and online count
            member_count = 0
            online_count = 0
            try:
                member_count = await client.get_chat_members_count(chat.id)
                # Get online count by checking up to 50 members
                count = 0
                async for member in client.get_chat_members(chat.id):
                    if member.user and member.user.status == UserStatus.ONLINE:
                        online_count += 1
                    count += 1
                    if count >= 50:  # Limit to 50 to avoid performance issues
                        break
            except Exception:
                member_count = 0
                online_count = 0

            # avatar
            photo_url = None
            has_photo = bool(getattr(chat, "photo", None))
            if has_photo:
                try:
                    dest = _avatar_file(user_id, account_index, chat.id)
                    if not dest.exists():
                        file_id = getattr(chat.photo, "small_file_id", None) or getattr(chat.photo, "big_file_id", None)
                        if file_id:
                            data = await client.download_media(file_id, in_memory=True)
                            if data:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with open(dest, 'wb') as f:
                                    f.write(data.getvalue())
                    if dest.exists():
                        photo_url = f"/media/avatars/{user_id}/{account_index}/{chat.id}.jpg"
                except Exception:
                    photo_url = None

            if not photo_url:
                photo_url = DEFAULT_AVATAR_URL

            out.append({
                "id": chat.id,
                "title": title,
                "username": username,
                "member_count": member_count,
                "online_count": online_count,
                "has_photo": has_photo,
                "photo_url": photo_url,
            })
        return out
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


async def get_chat_messages(user_id: str, account_index: int, chat_id: int,limit: int = 10,offset: int = 0) -> List[Dict[str, Any]]:
    """
    Chatdan xabarlarni olish va har bir xabarning o'qilganligini aniqlash.
    
    Args:
        user_id: Foydalanuvchi ID
        account_index: Telegram akkaunti index
        chat_id: Chat ID
        limit: Nechta xabar olish
        offset: Qayerdan boshlash
        
    Returns:
        Xabarlar ro'yxati
    """
    client = build_client_for(user_id, account_index)
    await client.start()

    try:
        # Dialogni topish
        dialog_obj = None
        async for d in client.get_dialogs():
            if d.chat.id == chat_id:
                dialog_obj = d
                break

        if not dialog_obj:
            raise ValueError(
                "Chat topilmadi yoki ushbu akkaunt uchun mavjud emas. "
                "Ehtimol, noto'g'ri sessiya tanlangan."
            )

        chat = dialog_obj.chat
        
        # O'qilgan xabarlarning maksimal ID lari
        read_inbox_max_id = getattr(dialog_obj, 'read_inbox_max_id', 0)
        read_outbox_max_id = getattr(dialog_obj, 'read_outbox_max_id', 0)

        # Xabarlarni olish
        messages: List[Dict[str, Any]] = []
        need = limit + offset
        skipped = 0

        async for msg in client.get_chat_history(chat.id, limit=need):
            # Offset qo'llash
            if skipped < offset:
                skipped += 1
                continue

            # isRead mantiq: 
            # - outgoing xabar bo'lsa: karshi tomon o'qiganmi?
            # - incoming xabar bo'lsa: biz o'qiganmizmi?
            if msg.outgoing:
                is_read = msg.id <= read_outbox_max_id
            else:
                is_read = msg.id <= read_inbox_max_id

            # from_user uchun avatar yuklab olish
            photo_url = None
            if msg.from_user and getattr(msg.from_user, "photo", None):
                dest = _avatar_file(user_id, account_index, msg.from_user.id)
                if not dest.exists():
                    file_id = getattr(msg.from_user.photo, "small_file_id", None) or getattr(msg.from_user.photo, "big_file_id", None)
                    if file_id:
                        try:
                            data = await client.download_media(file_id, in_memory=True)
                            if data:
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                with open(dest, 'wb') as f:
                                    f.write(data.getvalue())
                        except Exception:
                            pass
                if dest.exists():
                    photo_url = f"/media/avatars/{user_id}/{account_index}/{msg.from_user.id}.jpg"

            # Asosiy xabar ma'lumotlari
            item = {
                "id": msg.id,
                "date": msg.date.isoformat() if msg.date else None,
                "chat_id": chat.id,
                "chat_type": chat.type.value if hasattr(chat.type, 'value') else str(chat.type),
                "is_read": is_read,
                "is_outgoing": msg.outgoing,
                "from_user": {
                    "id": msg.from_user.id,
                    "first_name": msg.from_user.first_name,
                    "last_name": msg.from_user.last_name,
                    "username": msg.from_user.username,
                    "phone_number": getattr(msg.from_user, 'phone_number', None),
                    "photo_url": photo_url,
                    "status": str(msg.from_user.status) if msg.from_user.status else None,
                    "bio": getattr(msg.from_user, 'bio', None),
                } if msg.from_user else None,
                "text": msg.text,
                "caption": msg.caption,
                "media_type": None,
                "file_id": None,
                "file_name": None,
                "mime_type": None,
            }

            # Media turlarini aniqlash
            if msg.photo:
                item["media_type"] = "photo"
                item["file_id"] = msg.photo.file_id

            elif msg.video:
                item["media_type"] = "video"
                item["file_id"] = msg.video.file_id
                item["file_name"] = msg.video.file_name
                item["mime_type"] = msg.video.mime_type

            elif msg.audio:
                item["media_type"] = "audio"
                item["file_id"] = msg.audio.file_id
                item["file_name"] = msg.audio.file_name
                item["mime_type"] = msg.audio.mime_type

            elif msg.document:
                item["media_type"] = "document"
                item["file_id"] = msg.document.file_id
                item["file_name"] = msg.document.file_name
                item["mime_type"] = msg.document.mime_type

            elif msg.voice:
                item["media_type"] = "voice"
                item["file_id"] = msg.voice.file_id
                item["mime_type"] = msg.voice.mime_type

            elif msg.sticker:
                item["media_type"] = "sticker"
                item["file_id"] = msg.sticker.file_id

            elif msg.animation:
                item["media_type"] = "animation"
                item["file_id"] = msg.animation.file_id

            elif msg.video_note:
                item["media_type"] = "video_note"
                item["file_id"] = msg.video_note.file_id

            messages.append(item)

            # Limit yetganda to'xtatish
            if len(messages) >= limit:
                break

        return messages

    except PeerIdInvalid:
        raise ValueError(
            "Telegram ushbu chatni tanimaydi. "
            "Chat ID noto'g'ri yoki sessiya mos emas."
        )

    except Exception as e:
        raise Exception(f"Xabarlarni olishda xatolik: {str(e)}")

    finally:
        try:
            await client.stop()
        except Exception:
            pass