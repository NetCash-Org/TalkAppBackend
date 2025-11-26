import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from src.main import app
from src.config import supabase_service

client = TestClient(app)

class TestAuditLogging:
    """Test audit logging functionality"""

    def test_login_audit_log(self):
        """Test that login action is logged"""
        from src.middleware.audit_logging import audit_logs_memory
        initial_count = len(audit_logs_memory)

        # Mock successful login
        with patch('src.config.supabase.auth.sign_in_with_password') as mock_signin:
            mock_session = MagicMock()
            mock_session.access_token = "test_token"
            mock_session.expires_in = 3600
            mock_session.refresh_token = "refresh_token"
            mock_signin.return_value.session = mock_session
            mock_signin.return_value.user = MagicMock(id="test_user_id", email="test@example.com")

            response = client.post("/auth/login", json={
                "email": "test@example.com",
                "password": "password123"
            })

            assert response.status_code == 200
            # Verify audit log was called
            mock_supabase.rpc.assert_called_once()
            call_args = mock_supabase.rpc.call_args
            assert call_args[0][0] == "insert_audit_log"
            log_data = call_args[0][1]
            assert log_data["p_action"] == "login"
            assert log_data["p_route"] == "/auth/login"
            assert log_data["p_http_method"] == "POST"
            assert log_data["p_user_id"] == "test_user_id"

    @patch('src.middleware.audit_logging.supabase_service')
    def test_create_user_audit_log(self, mock_supabase):
        """Test that create user action is logged"""
        mock_supabase.rpc.return_value = None

        # Mock admin user creation
        with patch('src.config.supabase_service.auth.admin.create_user') as mock_create:
            mock_user = MagicMock()
            mock_user.id = "new_user_id"
            mock_user.email = "new@example.com"
            mock_create.return_value.user = mock_user

            response = client.post("/admin/users", json={
                "email": "new@example.com",
                "password": "password123"
            })

            assert response.status_code == 201
            # Verify audit log was called
            mock_supabase.rpc.assert_called_once()
            call_args = mock_supabase.rpc.call_args
            log_data = call_args[0][1]
            assert log_data["p_action"] == "create"
            assert log_data["p_route"] == "/admin/users"
            assert log_data["p_http_method"] == "POST"

    def test_admin_audit_logs_access(self):
        """Test admin can access audit logs"""
        # Mock admin user
        with patch('src.config.supabase.auth.get_user') as mock_get_user, \
             patch('src.config.supabase.table') as mock_table:

            mock_user = MagicMock()
            mock_user.raw_app_meta_data = {"role": "admin"}
            mock_get_user.return_value.user = mock_user

            mock_query = MagicMock()
            mock_query.select.return_value = mock_query
            mock_query.order.return_value = mock_query
            mock_query.range.return_value = mock_query
            mock_query.execute.return_value = MagicMock(data=[{"id": "1", "action": "login"}])

            mock_count_query = MagicMock()
            mock_count_query.select.return_value = mock_count_query
            mock_count_query.execute.return_value = MagicMock(count=1)

            mock_table.return_value = mock_query

            response = client.get("/admin/audit-logs", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert "total" in data

    def test_non_admin_cannot_access_audit_logs(self):
        """Test non-admin cannot access audit logs"""
        with patch('src.config.supabase.auth.get_user') as mock_get_user:
            mock_user = MagicMock()
            mock_user.raw_app_meta_data = {"role": "user"}
            mock_user.is_super_admin = False
            mock_get_user.return_value.user = mock_user

            response = client.get("/admin/audit-logs", headers={"Authorization": "Bearer test_token"})

            assert response.status_code == 403

    @patch('src.middleware.audit_logging.supabase_service')
    def test_error_logging(self, mock_supabase):
        """Test that errors are logged"""
        mock_supabase.rpc.return_value = None

        # Test invalid login
        with patch('src.config.supabase.auth.sign_in_with_password') as mock_signin:
            mock_signin.side_effect = Exception("Invalid credentials")

            response = client.post("/auth/login", json={
                "email": "test@example.com",
                "password": "wrongpassword"
            })

            assert response.status_code == 401
            # Verify audit log was called with error
            mock_supabase.rpc.assert_called_once()
            call_args = mock_supabase.rpc.call_args
            log_data = call_args[0][1]
            assert log_data["p_status"] == 401
            assert "Invalid credentials" in log_data["p_error_message"]

# Example request/response documentation
"""
Example API Requests and Responses for Audit Logging:

1. Login Action:
POST /auth/login
Request:
{
    "email": "user@example.com",
    "password": "password123"
}
Response (200):
{
    "access_token": "eyJ...",
    "token_type": "bearer",
    "expires_in": 3600,
    "refresh_token": "refresh_token",
    "user": {
        "id": "user_id",
        "email": "user@example.com"
    }
}
Audit Log Created:
{
    "user_id": "user_id",
    "action": "login",
    "route": "/auth/login",
    "http_method": "POST",
    "status": 200,
    "ip_address": "192.168.1.1",
    "device_info": {"user_agent": "Mozilla/5.0...", "accept": "application/json"},
    "error_message": null
}

2. Admin View Audit Logs:
GET /admin/audit-logs?limit=10&action=login
Headers: Authorization: Bearer <admin_token>
Response (200):
{
    "logs": [
        {
            "id": "log_id",
            "timestamp": "2025-11-26T07:25:25Z",
            "user_id": "user_id",
            "action": "login",
            "route": "/auth/login",
            "http_method": "POST",
            "status": 200,
            "ip_address": "192.168.1.1",
            "device_info": {"user_agent": "Mozilla/5.0..."},
            "error_message": null
        }
    ],
    "total": 1,
    "limit": 10,
    "offset": 0
}

3. Create User Action:
POST /admin/users
Headers: Authorization: Bearer <admin_token>
Request:
{
    "email": "newuser@example.com",
    "password": "securepass123"
}
Response (201):
{
    "id": "new_user_id",
    "email": "newuser@example.com"
}
Audit Log Created:
{
    "user_id": "admin_user_id",
    "action": "create",
    "route": "/admin/users",
    "http_method": "POST",
    "status": 201,
    "ip_address": "192.168.1.1",
    "device_info": {"user_agent": "Mozilla/5.0..."},
    "error_message": null
}

4. Set Admin Role:
POST /admin/users/{user_id}/set-admin?is_admin=true
Headers: Authorization: Bearer <admin_token>
Response (200):
{
    "message": "User admin ga o'zgartirildi.",
    "user_id": "user_id"
}
"""