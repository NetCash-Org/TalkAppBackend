from typing import List, Optional, Dict, Any
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime


class User(BaseModel):
    id: str
    email: str




class UserAdmin(BaseModel):
    instance_id: Optional[str] = None
    id: str
    aud: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    email_confirmed_at: Optional[datetime] = None
    invited_at: Optional[datetime] = None
    confirmation_token: Optional[str] = None
    confirmation_sent_at: Optional[datetime] = None
    recovery_token: Optional[str] = None
    recovery_sent_at: Optional[datetime] = None
    email_change_token_new: Optional[str] = None
    email_change: Optional[str] = None
    email_change_sent_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    raw_app_meta_data: Optional[Dict[str, Any]] = None
    raw_user_meta_data: Optional[Dict[str, Any]] = None
    is_super_admin: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    phone: Optional[str] = None
    phone_confirmed_at: Optional[datetime] = None
    phone_change: Optional[str] = None
    phone_change_token: Optional[str] = None
    phone_change_sent_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    email_change_token_current: Optional[str] = None
    email_change_confirm_status: Optional[int] = None
    banned_until: Optional[datetime] = None
    reauthentication_token: Optional[str] = None
    reauthentication_sent_at: Optional[datetime] = None
    is_sso_user: bool = False
    deleted_at: Optional[datetime] = None
    is_anonymous: bool = False



class UserSafe(BaseModel):
    id: str
    email: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    is_anonymous: bool
    raw_app_meta_data: Optional[Dict[str, Any]] = None
    raw_user_meta_data: Optional[Dict[str, Any]] = None


class UserCreate(BaseModel):
    email: EmailStr
    password: Optional[str] = Field(default=None, min_length=6)  # None => passwordless
    phone: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None
    app_metadata: Optional[Dict[str, Any]] = None
    email_confirm: bool = False
    phone_confirm: bool = False
    send_confirmation_email: bool = True
    redirect_to: Optional[str] = None  # email tasdiq/magic-link qaytish URL

class UserOut(BaseModel):
    id: str
    email: Optional[str] = None


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default=None, min_length=6)
    phone: Optional[str] = None
    user_metadata: Optional[Dict[str, Any]] = None
    app_metadata: Optional[Dict[str, Any]] = None
    email_confirm: Optional[bool] = None
    phone_confirm: Optional[bool] = None
    # ixtiyoriy: vaqtincha bloklash (GoTrue qo‘llab-quvvatlasa)
    ban_duration: Optional[str] = None  # masalan: "indefinite" yoki "3600s"



class MeOut(BaseModel):
    id: str
    email: Optional[str] = None

    providers: List[str] = []
    email_confirmed: bool = False
    phone: Optional[str] = None
    phone_confirmed: bool = False

    created_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None

    is_anonymous: bool = False
    raw_app_meta_data: Optional[Dict[str, Any]] = None
    raw_user_meta_data: Optional[Dict[str, Any]] = None

    # Ko‘p joyda kerak bo‘lishi mumkin:
    user_metadata: Optional[Dict[str, Any]] = None
    app_metadata: Optional[Dict[str, Any]] = None

    role: Optional[str] = None
    aud: Optional[str] = None



class LoginIn(BaseModel):
    email: EmailStr
    password: str

class LoginOut(BaseModel):
    access_token: str
    token_type: str
    expires_in: int | None = None
    refresh_token: str | None = None
    user: dict | None = None



class SupabaseUserRaw(BaseModel):
    # Supabase auth.users dagi tipik ustunlar (1:1 mapping)
    instance_id: Optional[str] = None
    id: str
    aud: Optional[str] = None
    role: Optional[str] = None

    email: Optional[EmailStr] = None
    email_confirmed_at: Optional[datetime] = None
    invited_at: Optional[datetime] = None
    confirmation_token: Optional[str] = Field(default="")
    confirmation_sent_at: Optional[datetime] = None
    recovery_token: Optional[str] = Field(default="")
    recovery_sent_at: Optional[datetime] = None
    email_change_token_new: Optional[str] = Field(default="")
    email_change: Optional[str] = Field(default="")
    email_change_sent_at: Optional[datetime] = None
    last_sign_in_at: Optional[datetime] = None

    raw_app_meta_data: Optional[Dict[str, Any]] = None
    raw_user_meta_data: Optional[Dict[str, Any]] = None

    is_super_admin: Optional[bool] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    phone: Optional[str] = None
    phone_confirmed_at: Optional[datetime] = None
    phone_change: Optional[str] = Field(default="")
    phone_change_token: Optional[str] = Field(default="")
    phone_change_sent_at: Optional[datetime] = None
    confirmed_at: Optional[datetime] = None
    email_change_token_current: Optional[str] = Field(default="")
    email_change_confirm_status: Optional[int] = Field(default=0)
    banned_until: Optional[datetime] = None
    reauthentication_token: Optional[str] = Field(default="")
    reauthentication_sent_at: Optional[datetime] = None
    is_sso_user: bool = False
    deleted_at: Optional[datetime] = None
    is_anonymous: bool = False




class SetPlanIn(BaseModel):
    user_id: str                  # auth.users.id
    plan: str                     # 'free' | 'pro' | 'business'
    accounts_limit: int
    features: dict = {}           # {"ai_pro": True}
    current_period_end: str | None = None  # ISO (e.g. "2025-10-12T10:00:00Z")



class StartLoginIn(BaseModel):
    user_id: str
    phone_number: str

class VerifyCodeIn(BaseModel):
    user_id: str
    phone_number: str
    code: str

class VerifyPasswordIn(BaseModel):
    user_id: str
    phone_number: str
    password: str