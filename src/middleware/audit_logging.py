import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime
import re
from collections import deque

logger = logging.getLogger(__name__)

# In-memory audit log storage
audit_logs_memory: deque = deque(maxlen=10000)  # Keep last 10,000 logs

class AuditLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract request details
        path = request.url.path
        method = request.method
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        authorization = request.headers.get("authorization", "")

        # Extract user_id from token if present
        user_id = None
        if authorization.lower().startswith("bearer "):
            token = authorization.split(" ", 1)[1].strip()
            try:
                res = supabase_service.auth.get_user(token)
                user = getattr(res, "user", None) or (getattr(res, "data", {}) or {}).get("user")
                if user:
                    user_id = str(getattr(user, "id", ""))
            except Exception as e:
                logger.debug(f"Failed to extract user from token: {e}")

        # Determine action based on path and method
        action = self._determine_action(path, method)

        # Skip logging if no action determined
        if not action:
            return await call_next(request)

        # Process the request
        response = await call_next(request)

        # Extract response details
        status_code = response.status_code
        error_message = None

        # If error status, try to get error message from response body
        if status_code >= 400:
            try:
                # Note: This is a simplified approach. In production, you might need to read the response body carefully
                # as it can only be read once. For audit logging, we can log the status and a generic message.
                error_message = f"HTTP {status_code} error"
            except Exception:
                error_message = f"HTTP {status_code} error"

        # Prepare device info
        device_info = {
            "user_agent": user_agent,
            "accept": request.headers.get("accept", ""),
            "accept_language": request.headers.get("accept-language", ""),
            "accept_encoding": request.headers.get("accept-encoding", ""),
        }

        # Log to memory
        try:
            log_entry = {
                "id": str(datetime.utcnow().timestamp()) + "_" + str(len(audit_logs_memory)),
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "user_id": user_id,
                "action": action,
                "route": path,
                "http_method": method,
                "status": status_code,
                "ip_address": client_ip,
                "device_info": device_info,
                "error_message": error_message,
                "created_at": datetime.utcnow().isoformat() + "Z"
            }
            audit_logs_memory.append(log_entry)
            logger.info(f"Audit log: {action} on {path} by user {user_id}")
        except Exception as e:
            logger.error(f"Failed to store audit log in memory: {e}")

        return response

    def _get_client_ip(self, request: Request) -> Optional[str]:
        """Extract client IP address from request headers."""
        # Check X-Forwarded-For header (common with proxies/load balancers)
        x_forwarded_for = request.headers.get("x-forwarded-for")
        if x_forwarded_for:
            # Take the first IP if multiple are present
            return x_forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        x_real_ip = request.headers.get("x-real-ip")
        if x_real_ip:
            return x_real_ip.strip()

        # Fallback to client host
        client_host = getattr(request.client, "host", None) if request.client else None
        return client_host

    def _determine_action(self, path: str, method: str) -> Optional[str]:
        """Determine the audit action based on path and method."""
        # Define action mappings
        action_mappings = [
            # Auth actions
            (r"^/auth/login$", "POST", "login"),
            (r"^/auth/logout$", "POST", "logout"),  # Assuming logout endpoint exists

            # User CRUD actions
            (r"^/admin/users$", "POST", "create"),
            (r"^/admin/users/[^/]+$", "PATCH", "update"),
            (r"^/admin/users/[^/]+$", "DELETE", "delete"),

            # File upload (assuming telegram endpoints handle file uploads)
            (r"^/start_login$", "POST", "file_upload"),  # May need adjustment based on actual endpoints
            (r"^/me/telegrams$", "POST", "file_upload"),  # Assuming file upload for telegram sessions
        ]

        for pattern, req_method, action in action_mappings:
            if method == req_method and re.match(pattern, path):
                return action

        return None