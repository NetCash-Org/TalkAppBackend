from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routers.auth import router as auth_router
from src.routers.telegram import router as telegram_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Oldingi endpoint yo‘llari saqlanadi:
# /check, /users, /admin/users, /admin/users-with-telegrams,
# /admin/users/{id} CRUD, /auth/login, /auth/me
# /start_login, /verify_code, /verify_password,
# /me/telegrams (GET/DELETE), /me/telegrams/{index} (DELETE),
# /admin/users/{user_id}/telegrams/{index} (DELETE)
app.include_router(auth_router)
app.include_router(telegram_router)