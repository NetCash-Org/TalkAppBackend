# src/services/json_utils.py
from __future__ import annotations
from datetime import datetime, date
from enum import Enum
from typing import Any

PRIMITIVES = (str, int, float, bool, type(None))

def _is_jsonable_basic(x: Any) -> bool:
    return isinstance(x, PRIMITIVES)

def _to_jsonable(value: Any, *, max_depth: int = 2, _depth: int = 0) -> Any:
    """
    Pyrogram obyektlari uchun xavfsiz serializer.
    - callable/metodlar, private ('_' bilan boshlangan) fieldlar tashlab yuboriladi
    - datetime/date -> isoformat()
    - Enum -> name (yoki value)
    - list/tuple/set -> rekursiv
    - dict -> rekursiv (kalitlar str ga o‘tkaziladi)
    - boshqa obyekt -> attr scanning (dir()), callables & dunder chiqib ketadi
    """
    if _depth > max_depth:
        # chuqurlikni cheklaymiz
        return None

    if _is_jsonable_basic(value):
        return value

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, Enum):
        # nomi ma’qulroq ko‘rinadi; istasangiz .value ni ham qaytaring
        return getattr(value, "name", str(value))

    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            try:
                sk = str(k)
                out[sk] = _to_jsonable(v, max_depth=max_depth, _depth=_depth + 1)
            except Exception:
                # muammo bo‘lsa tashlab ketamiz
                continue
        return out

    if isinstance(value, (list, tuple, set)):
        return [
            _to_jsonable(v, max_depth=max_depth, _depth=_depth + 1)
            for v in list(value)
        ]

    # Pyrogram & boshqa obyektlar uchun attr-scan
    out = {}
    for name in dir(value):
        if not name or name.startswith("_"):
            continue
        try:
            attr = getattr(value, name)
        except Exception:
            continue
        # metod/callable’lar kerakmas
        if callable(attr):
            continue
        # Client kabi og‘ir maydonlarni tashlaymiz
        if name in {"client", "_client", "raw", "_raw"}:
            continue
        try:
            out[name] = _to_jsonable(attr, max_depth=max_depth, _depth=_depth + 1)
        except Exception:
            continue
    # hech nima topilmasa, fallback sifatida str()
    return out or str(value)