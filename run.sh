#!/bin/bash
#uvicorn src.main:app --reload
#uvicorn src.main:app --reload

#!/bin/bash
set -e

# Python deps
pip install --upgrade pip
pip install -r requirements.txt

# Kerakli papkalarni yaratib oling (Railway volume’ga yo‘naltiramiz)
mkdir -p "${SESS_ROOT:-/data/sessions}"
mkdir -p "${MEDIA_ROOT:-/data/media}"

# Uvicorn ishga tushirish (Railway $PORT beradi)
uvicorn src.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8002}" \
  --proxy-headers \
  --forwarded-allow-ips="*"