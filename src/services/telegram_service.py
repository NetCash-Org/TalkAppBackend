import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from pyrogram import Client
from src.config import API_ID, API_HASH, SESS_ROOT, PENDING_FILE

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