"""
Pydantic 模型验证测试
"""
import pytest
from pydantic import ValidationError

from app.models import (
    RegisterRequest, LoginRequest, ChatRequest,
    SessionCreate, SessionRename, ChangePasswordRequest,
    UpdateProfileRequest, ExportPdfRequest,
)


class TestRegisterRequest:
    """注册请求模型验证"""

    def test_valid_register(self):
        req = RegisterRequest(
            username="testuser",
            password="testpass123",
            display_name="Test User",
            email="test@example.com",
            invite_code="ABC123",
        )
        assert req.username == "testuser"
        assert req.email == "test@example.com"

    def test_username_too_short(self):
        with pytest.raises(ValidationError) as exc:
            RegisterRequest(
                username="ab",
                password="testpass123",
                invite_code="ABC123",
            )
        assert "用户名长度" in str(exc.value)

    def test_username_too_long(self):
        with pytest.raises(ValidationError) as exc:
            RegisterRequest(
                username="a" * 21,
                password="testpass123",
                invite_code="ABC123",
            )
        assert "用户名长度" in str(exc.value)

    def test_username_with_special_chars(self):
        with pytest.raises(ValidationError) as exc:
            RegisterRequest(
                username="test@user",
                password="testpass123",
                invite_code="ABC123",
            )
        assert "用户名" in str(exc.value)

    def test_username_valid_chinese(self):
        """中文用户名应该通过"""
        req = RegisterRequest(
            username="测试用户",
            password="testpass123",
            invite_code="ABC123",
        )
        assert req.username == "测试用户"

    def test_password_too_short(self):
        with pytest.raises(ValidationError) as exc:
            RegisterRequest(
                username="testuser",
                password="12345",
                invite_code="ABC123",
            )
        assert "密码长度" in str(exc.value)

    def test_password_at_boundary(self):
        """恰好 6 位密码应该通过"""
        req = RegisterRequest(
            username="testuser",
            password="123456",
            invite_code="ABC123",
        )
        assert req.password == "123456"

    def test_invalid_email(self):
        with pytest.raises(ValidationError) as exc:
            RegisterRequest(
                username="testuser",
                password="testpass123",
                email="not-an-email",
                invite_code="ABC123",
            )
        assert "邮箱" in str(exc.value)

    def test_valid_email(self):
        req = RegisterRequest(
            username="testuser",
            password="testpass123",
            email="hello@world.com",
            invite_code="ABC123",
        )
        assert req.email == "hello@world.com"

    def test_empty_display_name_defaults(self):
        req = RegisterRequest(
            username="testuser",
            password="testpass123",
            invite_code="ABC123",
        )
        assert req.display_name == ""


class TestLoginRequest:
    """登录请求模型验证"""

    def test_valid_login(self):
        req = LoginRequest(username="testuser", password="testpass123")
        assert req.username == "testuser"
        assert req.password == "testpass123"


class TestChatRequest:
    """聊天请求模型验证"""

    def test_minimal_chat_request(self):
        req = ChatRequest(message="Hello")
        assert req.message == "Hello"
        assert req.model is None
        assert req.session_id is None
        assert req.use_responses is True

    def test_full_chat_request(self):
        req = ChatRequest(
            message="Hello",
            model="test-model",
            session_id=42,
            use_responses=False,
        )
        assert req.model == "test-model"
        assert req.session_id == 42
        assert req.use_responses is False

    def test_empty_message_allowed_at_model_level(self):
        """空消息在模型层允许（业务层拦截）"""
        req = ChatRequest(message="")
        assert req.message == ""


class TestSessionCreate:
    """会话创建模型验证"""

    def test_default_title(self):
        req = SessionCreate()
        assert req.title == "新对话"

    def test_custom_title(self):
        req = SessionCreate(title="My Session")
        assert req.title == "My Session"


class TestChangePasswordRequest:
    """修改密码请求模型验证"""

    def test_password_too_short(self):
        with pytest.raises(ValidationError) as exc:
            ChangePasswordRequest(old_password="old123", new_password="12345")
        assert "密码长度" in str(exc.value)


class TestUpdateProfileRequest:
    """更新资料请求模型验证"""

    def test_valid_email(self):
        req = UpdateProfileRequest(email="new@example.com")
        assert req.email == "new@example.com"

    def test_invalid_email(self):
        with pytest.raises(ValidationError) as exc:
            UpdateProfileRequest(email="bad-email")
        assert "邮箱" in str(exc.value)


class TestExportPdfRequest:
    """PDF 导出请求模型验证"""

    def test_default_mode(self):
        req = ExportPdfRequest(message_id=1)
        assert req.mode == "answer"

    def test_full_mode(self):
        req = ExportPdfRequest(message_id=1, mode="full")
        assert req.mode == "full"
