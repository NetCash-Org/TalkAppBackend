
from __future__ import annotations

import json
import asyncio
import shutil
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config import API_ID, API_HASH, SESS_ROOT, PENDING_FILE, BASE_URL
from pyrogram import Client, enums
import inspect
from pyrogram.enums import ChatType, UserStatus
from pyrogram.errors import RPCError, PeerIdInvalid, AuthKeyInvalid, SessionRevoked, SessionExpired
from src.config import API_ID, API_HASH, SESS_ROOT
from .json_utils import _to_jsonable

logger = logging.getLogger(__name__)

def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"


# xotiradagi holat: phone_number -> state
login_states: dict[str, dict] = {}

# Download locks to prevent concurrent access to same session
download_locks: dict[str, asyncio.Lock] = {}

# Session locks to prevent concurrent access to same session file
session_locks: dict[str, asyncio.Lock] = {}

# Client pool for persistent clients
client_pool: dict[str, dict[int, Client]] = {}

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
    session_name = str(account_index)
    try:
        client = await get_client(user_id, account_index)
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
    except (AuthKeyInvalid, SessionRevoked, SessionExpired):
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
    except Exception:
        # Temporary errors, don't mark as invalid
        return {
            "index": session_name,
            "full_name": None,
            "username": None,
            "phone_number": None,
            "telegram_id": None,
            "invalid": False,
            "profile_picture": None,
            "profile_url": None,
        }

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

    profiles = await asyncio.gather(*[process_session(name) for name in session_names])

    # Delete invalid sessions
    for profile in profiles:
        if profile.get("invalid"):
            index = profile.get("index")
            if index:
                try:
                    sess_file = user_dir(user_id) / f"{index}.session"
                    if sess_file.exists():
                        sess_file.unlink()
                        logger.info(f"Deleted invalid session file: {sess_file}")
                except Exception as e:
                    logger.error(f"Failed to delete invalid session {index}: {e}")

    # Filter out invalid or failed profiles from the result
    valid_profiles = [p for p in profiles if p.get("telegram_id") is not None]
    return valid_profiles

# ---- logout helpers ----
async def logout_one(user_id: str, session_name: str) -> dict:
    sess_dir = SESS_ROOT / user_id
    sess_file = sess_dir / f"{session_name}.session"
    if not sess_file.exists():
        return {"index": session_name, "status": "not_found"}

    # Stop and remove from pool if exists
    if user_id in client_pool and int(session_name) in client_pool[user_id]:
        client = client_pool[user_id][int(session_name)]
        try:
            await client.stop()
        except Exception:
            pass
        client_pool[user_id].pop(int(session_name), None)

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

    key = f"{user_id}_{account_index}"
    lock = session_locks.setdefault(key, asyncio.Lock())
    
    async with lock:
        client = build_client_for(user_id, account_index)
        await client.connect()
        try:
            chat = await client.get_chat(chat_id)
            if not chat or chat.type != ChatType.PRIVATE or not getattr(chat, "photo", None):
                return None

            # Tezlik uchun avval small, bo'lsa big
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
                await client.stop()
            except Exception:
                pass

def build_client_for(user_id: str, account_index: int) -> Client:
    sess_dir = Path(SESS_ROOT) / user_id
    sess_dir.mkdir(parents=True, exist_ok=True)
    session_name = str(account_index)
    return Client(session_name, api_id=API_ID, api_hash=API_HASH, workdir=str(sess_dir))

async def get_client(user_id: str, account_index: int) -> Client:
    if user_id not in client_pool:
        client_pool[user_id] = {}
    if account_index not in client_pool[user_id]:
        client = build_client_for(user_id, account_index)
        try:
            await client.start()
            client_pool[user_id][account_index] = client
        except Exception as e:
            logger.error(f"Failed to start client for {user_id} {account_index}: {e}")
            raise
    return client_pool[user_id][account_index]

def _avatar_file(user_id: str, account_index: int, chat_id: int) -> Path:
    d = AVATAR_DIR / user_id / str(account_index)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{chat_id}.jpg"

def _message_file(user_id: str, account_index: int, message_id: int, ext: str) -> Path:
    d = MEDIA_ROOT / "messages" / user_id / str(account_index)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{message_id}.{ext}"

def _thumb_file(user_id: str, account_index: int, message_id: int) -> Path:
    d = MEDIA_ROOT / "thumbs" / user_id / str(account_index)
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{message_id}.jpg"

async def download_thumb(client, thumb, dest: Path):
    try:
        data = await client.download_media(thumb.file_id, in_memory=True)
        if data:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, 'wb') as f:
                f.write(data.getvalue())
    except Exception:
        pass

async def get_thumb_url(msg, media_type: str, user_id: str, account_index: int, message_id: int, client) -> Optional[str]:
    media = getattr(msg, media_type, None)
    if media and hasattr(media, 'thumbs') and media.thumbs:
        thumb = min(media.thumbs, key=lambda t: t.file_size)
        dest = _thumb_file(user_id, account_index, message_id)
        if not dest.exists():
            await download_thumb(client, thumb, dest)
        if dest.exists():
            return f"/media/thumbs/{user_id}/{account_index}/{message_id}.jpg"
    return None

def get_media_ext(media_type: str, msg) -> str:
    if media_type == "photo":
        return "jpg"
    elif media_type == "video":
        return "mp4"
    elif media_type == "audio":
        return "mp3"
    elif media_type == "document":
        if hasattr(msg, 'document') and msg.document.file_name:
            parts = msg.document.file_name.split('.')
            return parts[-1] if len(parts) > 1 else 'file'
        return 'file'
    elif media_type == "voice":
        return "ogg"
    elif media_type == "sticker":
        return "webp"
    elif media_type == "animation":
        return "gif"
    elif media_type == "video_note":
        return "mp4"
    else:
        return "file"

async def download_message_media(user_id: str, account_index: int, file_id: str, dest: Path):
    key = f"{user_id}_{account_index}"
    lock = download_locks.setdefault(key, asyncio.Lock())
    async with lock:
        logger.info(f"Starting download for user {user_id} account {account_index} file {file_id} to {dest}")
        client = build_client_for(user_id, account_index)
        await client.connect()
        try:
            await client.download_media(file_id, file_name=str(dest))
            logger.info(f"Download completed for {file_id} to {dest}")
        except Exception as e:
            logger.error(f"Download failed for {file_id}: {e}")
        finally:
            await client.stop()

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
    key = f"{user_id}_{account_index}"
    lock = session_locks.setdefault(key, asyncio.Lock())
    
    async with lock:
        client = await get_client(user_id, account_index)
        out: List[Dict[str, Any]] = []
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

            is_premium = getattr(user_obj, 'is_premium', False) if user_obj else False

            # emoji_status uchun emoji yuklab olish
            emoji_url = None
            if user_obj and getattr(user_obj, "emoji_status", None):
                custom_emoji_id = getattr(user_obj.emoji_status, 'custom_emoji_id', None)
                if custom_emoji_id:
                    dest = AVATAR_DIR / user_id / str(account_index) / f"{user_obj.id}_emoji.webp"
                    if not dest.exists():
                        try:
                            stickers = await client.get_custom_emoji_stickers([custom_emoji_id])
                            if stickers and stickers[0]:
                                sticker = stickers[0]
                                file_id = sticker.file_id
                                data = await client.download_media(file_id, in_memory=True)
                                if data:
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    with open(dest, 'wb') as f:
                                        f.write(data.getvalue())
                        except Exception:
                            pass
                    if dest.exists():
                        emoji_url = f"/media/avatars/{user_id}/{account_index}/{user_obj.id}_emoji.webp"

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
                "is_premium": is_premium,
                "emoji_url": emoji_url,
            })
        return out


async def list_groups_minimal(user_id: str, account_index: int, limit: int = 10) -> List[Dict[str, Any]]:
    key = f"{user_id}_{account_index}"
    lock = session_locks.setdefault(key, asyncio.Lock())
    
    async with lock:
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
    client = await get_client(user_id, account_index)

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

        # Get account user id for bio fetching
        me = await client.get_me()
        account_user_id = me.id

        # Xabarlarni olish
        messages: List[Dict[str, Any]] = []
        need = limit + offset
        skipped = 0
        user_ids_to_fetch = set()

        async for msg in client.get_chat_history(chat.id, limit=need):
            # Offset qo'llash
            if skipped < offset:
                skipped += 1
                continue

            if msg.from_user:
                user_ids_to_fetch.add(msg.from_user.id)

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

            # emoji_status uchun emoji yuklab olish
            emoji_url = None
            if msg.from_user and getattr(msg.from_user, "emoji_status", None):
                custom_emoji_id = getattr(msg.from_user.emoji_status, 'custom_emoji_id', None)
                if custom_emoji_id:
                    dest = AVATAR_DIR / user_id / str(account_index) / f"{msg.from_user.id}_emoji.webp"
                    if not dest.exists():
                        try:
                            stickers = await client.get_custom_emoji_stickers([custom_emoji_id])
                            if stickers and stickers[0]:
                                sticker = stickers[0]
                                file_id = sticker.file_id
                                data = await client.download_media(file_id, in_memory=True)
                                if data:
                                    dest.parent.mkdir(parents=True, exist_ok=True)
                                    with open(dest, 'wb') as f:
                                        f.write(data.getvalue())
                        except Exception:
                            pass
                    if dest.exists():
                        emoji_url = f"/media/avatars/{user_id}/{account_index}/{msg.from_user.id}_emoji.webp"

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
                    "is_premium": getattr(msg.from_user, 'is_premium', False),
                    "emoji_url": emoji_url,
                } if msg.from_user else None,
                "text": msg.text,
                "caption": msg.caption,
                "media_type": None,
                "file_id": None,
                "file_name": None,
                "mime_type": None,
                "thumb_url": None,
            }

            # Media turlarini aniqlash
            if msg.photo:
                item["media_type"] = "photo"
                item["file_id"] = msg.photo.file_id
                item["file_size"] = format_file_size(msg.photo.file_size)

            elif msg.video:
                item["media_type"] = "video"
                item["file_name"] = msg.video.file_name
                item["mime_type"] = msg.video.mime_type
                item["file_id"] = msg.video.file_id
                item["file_size"] = format_file_size(msg.video.file_size)

            elif msg.audio:
                item["media_type"] = "audio"
                item["file_name"] = msg.audio.file_name
                item["mime_type"] = msg.audio.mime_type
                item["file_id"] = msg.audio.file_id
                item["file_size"] = format_file_size(msg.audio.file_size)

            elif msg.document:
                item["media_type"] = "document"
                item["file_name"] = msg.document.file_name
                item["mime_type"] = msg.document.mime_type
                item["file_id"] = msg.document.file_id
                item["file_size"] = format_file_size(msg.document.file_size)

            elif msg.voice:
                item["media_type"] = "voice"
                item["mime_type"] = msg.voice.mime_type
                item["file_id"] = msg.voice.file_id
                item["file_size"] = format_file_size(msg.voice.file_size)
                item["duration_seconds"] = msg.voice.duration
                minutes = msg.voice.duration // 60
                seconds = msg.voice.duration % 60
                item["duration_formatted"] = f"{minutes}:{seconds:02d}"
                item["waveform"] = list(msg.voice.waveform)

            elif msg.sticker:
                item["media_type"] = "sticker"
                item["file_id"] = msg.sticker.file_id
                item["file_size"] = format_file_size(msg.sticker.file_size)

            elif msg.animation:
                item["media_type"] = "animation"
                item["file_id"] = msg.animation.file_id
                item["file_size"] = format_file_size(msg.animation.file_size)

            elif msg.video_note:
                item["media_type"] = "video_note"
                item["file_id"] = msg.video_note.file_id
                item["file_size"] = format_file_size(msg.video_note.file_size)
                item["duration_seconds"] = msg.video_note.duration
                minutes = msg.video_note.duration // 60
                seconds = msg.video_note.duration % 60
                item["duration_formatted"] = f"{minutes}:{seconds:02d}"

            elif msg.location:
                item["media_type"] = "location"
                item["latitude"] = msg.location.latitude
                item["longitude"] = msg.location.longitude

            elif msg.contact:
                item["media_type"] = "contact"

            elif msg.poll:
                item["media_type"] = "poll"

            elif msg.venue:
                item["media_type"] = "venue"

            elif msg.game:
                item["media_type"] = "game"

            # Get thumbnail if available
            thumb_url = await get_thumb_url(msg, item["media_type"], user_id, account_index, msg.id, client) if item["media_type"] in ["photo", "video", "document", "animation", "sticker", "video_note"] else None
            item["thumb_url"] = thumb_url

            # Check if file is downloaded
            item["file_url"] = None
            if item["file_id"]:
                downloads_dir = MEDIA_ROOT / "downloads" / user_id / str(account_index)
                if downloads_dir.exists():
                    import os
                    for filename in os.listdir(str(downloads_dir)):
                        if filename.startswith(item["file_id"] + "."):
                            item["file_url"] = f"/media/downloads/{user_id}/{account_index}/{filename}"
                            break

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


async def export_chat_messages(user_id: str, account_index: int, chat_id: int) -> Dict[str, Any]:
    """
    Chatdan barcha xabarlarni eksport qilish (boshidan oxirigacha).

    Args:
        user_id: Foydalanuvchi ID
        account_index: Telegram akkaunti index
        chat_id: Chat ID

    Returns:
        Eksport ma'lumotlari va soddalashtirilgan xabarlar ro'yxati JSON formatida:
        [
          { "from": "Ali", "text": "Salom", "type": "text" },
          { "from": "me", "text": "Salom 👋", "type": "text" }
        ]
    """
    client = await get_client(user_id, account_index)

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

        # Get account user id
        me = await client.get_me()
        account_user_id = me.id

        # Xabarlarni olish (barchasi, limit yo'q)
        messages: List[Dict[str, str]] = []

        async for msg in client.get_chat_history(chat.id, limit=None):
            # Xabar matnini olish (text yoki caption)
            message_text = msg.text or msg.caption or ""
            
            # Xabar turini aniqlash
            message_type = "text"
            if msg.photo:
                message_type = "photo"
            elif msg.video:
                message_type = "video"
            elif msg.audio:
                message_type = "audio"
            elif msg.voice:
                message_type = "voice"
            elif msg.document:
                message_type = "document"
            elif msg.sticker:
                message_type = "sticker"
            elif msg.animation:
                message_type = "animation"
            elif msg.video_note:
                message_type = "video_note"
            elif msg.location:
                message_type = "location"
            elif msg.contact:
                message_type = "contact"
            elif msg.poll:
                message_type = "poll"
            elif msg.venue:
                message_type = "venue"
            elif msg.game:
                message_type = "game"
            
            # Xabarni kim yozganini aniqlash
            if msg.outgoing:
                from_name = "me"
            elif msg.from_user:
                from_name = " ".join(filter(None, [msg.from_user.first_name, msg.from_user.last_name])) or msg.from_user.username or "Unknown"
            else:
                from_name = "Unknown"
            
            # Soddalashtirilgan format
            messages.append({
                "from": from_name,
                "text": message_text,
                "type": message_type
            })

        # Export qilingan ma'lumotlarni diskka saqlash
        export_dir = MEDIA_ROOT / "exports" / user_id / str(account_index)
        export_dir.mkdir(parents=True, exist_ok=True)
        
        # JSON faylni diskka saqlash
        import time
        timestamp = int(time.time())
        filename = f"chat_{chat_id}_{timestamp}.json"
        filepath = export_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        
        # Fayl URLini va soddalashtirilgan xabarlarni qaytarish
        return {
            "ok": True,
            "file_url": f"/media/exports/{user_id}/{account_index}/{filename}",
            "file_path": str(filepath),
            "total_messages": len(messages),
            "filename": filename,
            "messages": messages
        }

    except PeerIdInvalid:
        raise ValueError(
            "Telegram ushbu chatni tanimaydi. "
            "Chat ID noto'g'ri yoki sessiya mos emas."
        )

    except Exception as e:
        raise Exception(f"Chat eksport qilishda xatolik: {str(e)}")