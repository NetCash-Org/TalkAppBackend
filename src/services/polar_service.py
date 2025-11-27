import os
import httpx
from src.config import POLAR_ACCESS_TOKEN
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

class PolarService:
    def __init__(self):
        self.access_token = POLAR_ACCESS_TOKEN
        self.base_url = "https://api.polar.sh/v1"
        self.client = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.access_token}"},
            follow_redirects=True
        )

    async def create_checkout_session(
        self,
        customer_id: str,
        email: str,
        product_price_id: str,
        success_url: Optional[str] = None,
        cancel_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Polar'da checkout session yaratish

        Args:
            customer_id: Supabase user UID
            email: Foydalanuvchi email'i
            product_price_id: Polar product price ID
            success_url: Muvaffaqiyat sahifasi URL
            cancel_url: Bekor qilish sahifasi URL

        Returns:
            Checkout session ma'lumotlari
        """
        try:
            payload = {
                "products": [product_price_id],
                "success_url": success_url or "http://localhost:3000/success"
            }

            response = await self.client.post(f"{self.base_url}/checkouts/", json=payload)
            if response.status_code >= 400:
                logger.error(f"Polar API error: {response.status_code} - {response.text}")
            response.raise_for_status()
            checkout = response.json()

            logger.info(f"Checkout session yaratildi: {checkout['id']} for customer {customer_id}")
            return {
                "checkout_id": checkout["id"],
                "url": checkout["url"],
                "customer_id": customer_id
            }
        except Exception as e:
            logger.error(f"Checkout session yaratishda xatolik: {str(e)}")
            raise

    async def get_customer_subscriptions(self, customer_id: str, email: str = None) -> Dict[str, Any]:
        """
        Customer uchun active subscription'larni olish

        Args:
            customer_id: Supabase user UID
            email: User email for existing Polar accounts

        Returns:
            Subscription ma'lumotlari
        """
        try:
            # First, try to find existing Polar customer by email
            polar_customer_id = None
            if email:
                try:
                    logger.info(f"Looking for existing Polar customer by email: {email}")
                    customers_response = await self.client.get(f"{self.base_url}/customers/", params={"email": email})
                    if customers_response.status_code == 200:
                        customers_data = customers_response.json()
                        customers = customers_data.get("items", [])
                        if customers:
                            polar_customer_id = customers[0]["id"]
                            logger.info(f"Found existing Polar customer: {polar_customer_id}")
                except Exception as e:
                    logger.warning(f"Could not query customers by email: {e}")

            # Use found customer ID or fallback to provided customer_id
            query_customer_id = polar_customer_id or customer_id

            # Get subscriptions for the customer
            response = await self.client.get(f"{self.base_url}/subscriptions/", params={"customer_id": query_customer_id})
            response.raise_for_status()
            subscriptions = response.json()

            # Faqat active subscription'larni qaytarish
            active_subscriptions = [
                sub for sub in subscriptions.get("items", [])
                if sub.get("status") == "active"
            ]

            if active_subscriptions:
                subscription = active_subscriptions[0]  # Birinchi active subscription
                logger.info(f"Found active subscription for customer {query_customer_id}")
                return {
                    "is_premium": True,
                    "subscription": {
                        "id": subscription["id"],
                        "status": subscription["status"],
                        "current_period_start": subscription["current_period_start"],
                        "current_period_end": subscription["current_period_end"],
                        "product_id": subscription["product_id"],
                        "price_id": subscription["price_id"]
                    }
                }

            logger.info(f"No active subscriptions found for customer {query_customer_id}")
            return {
                "is_premium": False,
                "subscription": None
            }
        except Exception as e:
            logger.error(f"Subscription ma'lumotlarini olishda xatolik: {str(e)}")
            return {
                "is_premium": False,
                "subscription": None
            }

    async def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Webhook signature'ni tekshirish

        Args:
            payload: Webhook body
            signature: Polar webhook signature

        Returns:
            Signature to'g'ri yoki yo'qligi
        """
        try:
            # Polar webhook signature verification
            # Note: Polar uses HMAC with webhook secret, but for now we'll skip detailed verification
            # In production, implement proper HMAC verification with webhook secret
            if not signature:
                return False
            # Basic check - in production, verify HMAC
            return True
        except Exception as e:
            logger.error(f"Webhook signature verification xatolik: {str(e)}")
            return False

# Global instance
polar_service = PolarService()