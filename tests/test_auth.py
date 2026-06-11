"""
JWT 认证核心逻辑测试 — 密码哈希、token 创建/解码/过期
"""
import time
import pytest
from datetime import datetime, timedelta, timezone

# 在导入前确保测试环境变量已设置
import os
os.environ.setdefault("JWT_SECRET", "test-secret-for-pytest")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_EXPIRE_HOURS", "168")

from app.auth import hash_password, verify_password, create_token, decode_token


class TestPasswordHashing:
    """密码哈希与验证"""

    def test_hash_produces_different_string(self):
        """哈希结果与原密码不同"""
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert hashed != plain

    def test_hash_is_reproducible_different_each_time(self):
        """每次哈希结果不同（盐值随机）"""
        plain = "mysecretpassword"
        h1 = hash_password(plain)
        h2 = hash_password(plain)
        assert h1 != h2

    def test_verify_correct_password(self):
        """正确密码验证通过"""
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_wrong_password(self):
        """错误密码验证失败"""
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_empty_password(self):
        """空密码验证"""
        plain = "mysecretpassword"
        hashed = hash_password(plain)
        assert verify_password("", hashed) is False


class TestTokenCreation:
    """JWT Token 创建"""

    def test_create_token_returns_string(self):
        token = create_token(1, "testuser")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_token_is_jwt_format(self):
        """Token 应为标准 JWT 三段格式"""
        token = create_token(1, "testuser")
        parts = token.split(".")
        assert len(parts) == 3

    def test_create_token_different_users(self):
        """不同用户产生不同 token"""
        t1 = create_token(1, "user1")
        t2 = create_token(2, "user2")
        assert t1 != t2


class TestTokenDecoding:
    """JWT Token 解码"""

    def test_decode_valid_token(self):
        token = create_token(42, "testuser")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "42"
        assert payload["username"] == "testuser"

    def test_decode_tampered_token(self):
        """篡改的 token 解码失败"""
        token = create_token(1, "testuser")
        # 修改 payload 部分（第二段）
        parts = token.split(".")
        tampered = parts[0] + "." + "tampered" + "." + parts[2]
        payload = decode_token(tampered)
        assert payload is None

    def test_decode_invalid_token(self):
        """完全无效的 token"""
        payload = decode_token("not.a.valid.jwt.token.at.all")
        assert payload is None

    def test_decode_empty_token(self):
        """空 token"""
        payload = decode_token("")
        assert payload is None

    def test_decode_none_token(self):
        """None token 引发异常（jose 库不接受 None）"""
        import pytest as pt
        with pt.raises(AttributeError):
            decode_token(None)

    def test_decode_token_preserves_username(self):
        """Token 解码后保留 username"""
        token = create_token(99, "alice")
        payload = decode_token(token)
        assert payload["username"] == "alice"

    def test_decode_token_preserves_user_id_type(self):
        """sub 字段为字符串格式的 user_id"""
        token = create_token(12345, "bob")
        payload = decode_token(token)
        assert payload["sub"] == "12345"


class TestTokenExpiry:
    """Token 过期处理"""

    def test_decode_expired_token(self):
        """过期 token 返回 None（直接构造过期 JWT）"""
        from datetime import datetime, timedelta, timezone
        from jose import jwt as jose_jwt
        from app.config import JWT_SECRET, JWT_ALGORITHM

        # 手动构造一个已过期的 token
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        payload_data = {
            "sub": "1",
            "username": "testuser",
            "exp": past,
        }
        expired_token = jose_jwt.encode(payload_data, JWT_SECRET, algorithm=JWT_ALGORITHM)

        result = decode_token(expired_token)
        assert result is None
