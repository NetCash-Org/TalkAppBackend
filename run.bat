@echo off
REM pip install --upgrade pip
REM pip install -r requirements.txt

REM set SESS_ROOT=./data/sessions
REM set MEDIA_ROOT=./data/media

REM mkdir %SESS_ROOT%
REM dir %MEDIA_ROOT%

REM uvicorn src.main:app --host 0.0.0.0 --port 8002 --proxy-headers --forwarded-allow-ips="*"
uvicorn src.main:app --host 0.0.0.0 --port 8002 --proxy-headers --forwarded-allow-ips="*" --reload