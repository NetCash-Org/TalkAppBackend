from fastapi import APIRouter, HTTPException, Header, Request
from typing import Optional
from pydantic import BaseModel
from src.config import supabase, POLAR_SUCCESS_URL
from src.services.polar_service import polar_service
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

class CheckoutCreateRequest(BaseModel):
    product_price_id: str
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None

class CheckoutCreateResponse(BaseModel):
    checkout_id: str
    url: str
    customer_id: str

class SubscriptionStatusResponse(BaseModel):
    is_premium: bool
    subscription: Optional[dict] = None


@router.post("/api/checkout/create", response_model=CheckoutCreateResponse)
async def create_checkout(
    request: CheckoutCreateRequest,
    authorization: str = Header(..., alias="Authorization")
):
    """
    Polar checkout session yaratish

    - Supabase auth token'dan user ma'lumotlarini olish
    - Polar'da checkout session yaratish
    - customer_id sifatida Supabase user UID'ni ishlatish
    """
    # Token tekshirish - auth/me dan nusxa
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(400, "Authorization header 'Bearer <token>' bo'lishi kerak")
    token = authorization.split(" ", 1)[1].strip()
    try:
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
        if not user:
            raise HTTPException(401, "Noto'g'ri token yoki user topilmadi.")
    except Exception as e:
        msg = str(e).lower()
        if "session from session_id claim in jwt does not exist" in msg:
            raise HTTPException(400, "Token muddati o'tgan yoki sessiya mavjud emas. Qayta login qiling.")
        elif "invalid jwt" in msg or "jwt" in msg:
            raise HTTPException(400, "Token noto'g'ri yoki yaroqsiz.")
        else:
            raise HTTPException(400, f"Autentifikatsiya xatosi: {str(e)}")

    user_id = str(getattr(user, "id", ""))
    email = getattr(user, "email", "")

    if not user_id or not email:
        raise HTTPException(400, "User ma'lumotlari to'liq emas")

    try:
        # Default success URL
        success_url = request.success_url or POLAR_SUCCESS_URL or "http://localhost:3000/success"
        cancel_url = request.cancel_url or "http://localhost:3000/cancel"

        checkout_data = await polar_service.create_checkout_session(
            customer_id=user_id,
            email=email,
            product_price_id=request.product_price_id,
            success_url=success_url,
            cancel_url=cancel_url
        )

        return CheckoutCreateResponse(**checkout_data)

    except Exception as e:
        logger.error(f"Checkout yaratishda xatolik: {str(e)}")
        raise HTTPException(500, f"Checkout yaratishda xatolik: {str(e)}")

@router.post("/api/webhooks/polar")
async def polar_webhook(request: Request):
    """
    Polar'dan webhook qabul qilish

    - checkout.completed eventi
    - Webhook signature verification
    """
    try:
        # Get raw body
        body = await request.body()
        signature = request.headers.get("polar-signature")

        # For development/testing, allow requests without signature
        if signature:
            # Verify signature
            if not await polar_service.verify_webhook_signature(body, signature):
                raise HTTPException(401, "Webhook signature noto'g'ri")
        else:
            logger.warning("Webhook received without signature - allowing for testing")

        # Parse webhook data
        try:
            if not body:
                logger.warning("Webhook received with empty body - returning ok for testing")
                return {"status": "ok", "message": "Empty body received"}

            webhook_data = json.loads(body.decode('utf-8'))

            event_type = webhook_data.get("type")
            logger.info(f"Polar webhook qabul qilindi: {event_type}")

            if event_type == "checkout.completed":
                # Handle checkout completion
                data = webhook_data.get("data", {})
                customer_id = data.get("customer_id")
                subscription_id = data.get("subscription_id")

                if customer_id and subscription_id:
                    logger.info(f"Checkout completed for customer {customer_id}, subscription {subscription_id}")
                    # Bu yerda subscription status'ni yangilash logikasini qo'shish mumkin

            return {"status": "ok"}
        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON in webhook body: {e} - returning ok for testing")
            return {"status": "ok", "message": "Invalid JSON received"}

    except json.JSONDecodeError:
        raise HTTPException(400, "Webhook body noto'g'ri JSON")
    except Exception as e:
        logger.error(f"Webhook processing xatolik: {str(e)}")
        raise HTTPException(500, f"Webhook processing xatolik: {str(e)}")

@router.get("/api/subscription/status", response_model=SubscriptionStatusResponse)
async def get_subscription_status(authorization: str = Header(..., alias="Authorization")):
    """
    Foydalanuvchi subscription status'ini tekshirish

    - Supabase auth token'dan user UID'ni olish
    - Polar API orqali customer_id bo'yicha active subscription borligini tekshirish
    """
    logger.info(f"Subscription status called with auth header: {authorization[:50]}...")

    # Token tekshirish - soddalashtirilgan
    if not authorization or "bearer" not in authorization.lower():
        logger.error("Authorization header yo'q yoki noto'g'ri format")
        raise HTTPException(401, "Authorization header kerak")

    try:
        token = authorization.split(" ", 1)[1].strip()
        logger.info(f"Extracted token: {token[:20]}...")

        # URL decode token if needed (browser may encode it)
        from urllib.parse import unquote
        token = unquote(token)
        logger.info(f"URL decoded token: {token[:20]}...")

        # Supabase user validation
        res = supabase.auth.get_user(token)
        user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")

        if not user:
            logger.error("User topilmadi")
            raise HTTPException(401, "User topilmadi")

        user_id = str(getattr(user, "id", ""))
        email = getattr(user, "email", "")
        logger.info(f"User ID: {user_id}, Email: {email}")

        if not user_id:
            logger.error("User ID yo'q")
            raise HTTPException(400, "User ma'lumotlari to'liq emas")

        # Polar API call - email bilan existing accounts uchun
        status_data = await polar_service.get_customer_subscriptions(user_id, email)
        logger.info(f"Subscription status: {status_data}")

        return SubscriptionStatusResponse(**status_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Subscription status xatolik: {str(e)}")
        raise HTTPException(500, f"Xatolik: {str(e)}")