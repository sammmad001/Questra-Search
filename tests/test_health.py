"""
冒烟测试 — 健康检查、模型列表、静态文件、路由权限
"""
import pytest


class TestHealthCheck:
    """健康检查端点测试"""

    def test_health_returns_200(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_contains_version(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "version" in data

    def test_health_contains_model(self, client):
        resp = client.get("/api/health")
        data = resp.json()
        assert "model" in data


class TestModelsEndpoint:
    """模型列表端点测试"""

    def test_models_returns_200(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200

    def test_models_returns_list(self, client):
        resp = client.get("/api/models")
        data = resp.json()
        assert "models" in data
        assert isinstance(data["models"], list)
        assert len(data["models"]) > 0

    def test_models_have_required_fields(self, client):
        resp = client.get("/api/models")
        data = resp.json()
        for model in data["models"]:
            assert "id" in model
            assert "name" in model


class TestStaticFiles:
    """静态文件测试"""

    def test_static_app_js(self, client):
        resp = client.get("/static/app.js")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_static_app_css(self, client):
        resp = client.get("/static/app.css")
        assert resp.status_code == 200
        assert len(resp.content) > 0

    def test_static_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "<html" in resp.text.lower()

    def test_static_nonexistent_returns_404(self, client):
        resp = client.get("/static/nonexistent.xyz")
        assert resp.status_code == 404


class TestRoutePermissions:
    """路由权限测试"""

    def test_health_no_auth_required(self, client):
        """健康检查无需认证"""
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_models_no_auth_required(self, client):
        """模型列表无需认证"""
        resp = client.get("/api/models")
        assert resp.status_code == 200

    def test_sessions_require_auth(self, client):
        """会话列表需要认证"""
        resp = client.get("/api/sessions")
        # 未认证应返回 401
        assert resp.status_code == 401

    def test_auth_login_endpoint_exists(self, client):
        """登录端点存在"""
        resp = client.post("/api/auth/login", json={
            "username": "nonexistent",
            "password": "wrong",
        })
        # 不应该 404
        assert resp.status_code != 404

    def test_auth_register_endpoint_exists(self, client):
        """注册端点存在"""
        resp = client.post("/api/auth/register", json={
            "username": "test",
            "password": "test123",
            "invite_code": "INVALID",
        })
        # 不应该 404（邀请码无效返回 400，不是 404）
        assert resp.status_code != 404
