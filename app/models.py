"""
Pydantic 请求/响应模型
"""
import re
from typing import Optional, List, Any
from pydantic import BaseModel, field_validator


# ============ 认证 ============
class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""
    invite_code: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if len(v) < 3 or len(v) > 20:
            raise ValueError("用户名长度需在 3-20 个字符之间")
        if not re.match(r"^[a-zA-Z0-9_\u4e00-\u9fa5]+$", v):
            raise ValueError("用户名只能包含字母、数字、下划线或中文")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("密码长度至少 6 个字符")
        if len(v) > 64:
            raise ValueError("密码长度不能超过 64 个字符")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        v = v.strip()
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("邮箱格式不正确")
        return v


class UserResponse(BaseModel):
    id: int
    username: str
    display_name: str = ""
    email: str = ""


class AccountInfoResponse(BaseModel):
    """账户详情（含统计信息）"""
    id: int
    username: str
    display_name: str = ""
    email: str = ""
    is_active: int = 1
    created_at: str = ""
    last_login_at: str = ""
    # 统计
    total_sessions: int = 0
    total_messages: int = 0
    total_tokens: int = 0


class UpdateProfileRequest(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            v = v.strip()
            if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
                raise ValueError("邮箱格式不正确")
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError("新密码长度至少 6 个字符")
        if len(v) > 64:
            raise ValueError("新密码长度不能超过 64 个字符")
        return v


# ============ 邀请码 ============
class InviteCodeCreate(BaseModel):
    count: int = 1  # 一次生成几个


class InviteCodeResponse(BaseModel):
    id: int
    code: str
    used_by: Optional[int] = None
    used_at: Optional[str] = None
    created_at: str = ""


# ============ 会话 ============
class SessionCreate(BaseModel):
    title: Optional[str] = "新对话"
    model: Optional[str] = None


class SessionRename(BaseModel):
    title: str


class SessionResponse(BaseModel):
    id: int
    title: str
    model: str
    created_at: str
    updated_at: str


class SessionListResponse(BaseModel):
    items: List[SessionResponse]
    total: int


# ============ 消息 ============
class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    model: Optional[str] = None
    thinking_text: str = ""
    tool_events: Any = []
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    duration_ms: int = 0
    status: str = "completed"
    created_at: str = ""


class SessionDetailResponse(BaseModel):
    id: int
    title: str
    model: str
    created_at: str
    updated_at: str
    messages: List[MessageResponse]


# ============ 聊天 ============
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    session_id: Optional[int] = None
    use_responses: bool = True


class CancelRequest(BaseModel):
    request_id: str


# ============ 历史 ============
class HistoryItemResponse(BaseModel):
    id: int
    session_id: int
    session_title: str
    role: str
    content: str
    model: Optional[str] = None
    total_tokens: int = 0
    created_at: str = ""


class HistoryListResponse(BaseModel):
    items: List[HistoryItemResponse]
    total: int
    page: int
    limit: int


# ============ PDF 导出 ============
class ExportPdfRequest(BaseModel):
    message_id: int
    mode: str = "answer"  # "answer" | "full"


# ============ 通用 ============
class OkResponse(BaseModel):
    ok: bool = True
    detail: str = ""
