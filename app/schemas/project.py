import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.project import ProjectRole
from app.schemas.user import UserOut


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)


class ProjectMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ProjectRole
    joined_at: datetime
    user: UserOut


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    member_count: int = 0
    task_count: int = 0


class ProjectDetailOut(ProjectOut):
    members: list[ProjectMemberOut] = []


class MemberAdd(BaseModel):
    user_id: uuid.UUID | None = None
    email: EmailStr | None = None
    role: ProjectRole = ProjectRole.MEMBER

    @model_validator(mode="after")
    def _check_target(self):
        if not self.user_id and not self.email:
            raise ValueError("user_id 或 email 必须提供其一")
        if self.user_id and self.email:
            raise ValueError("user_id 和 email 只能提供其一")
        return self


class MemberRoleUpdate(BaseModel):
    role: ProjectRole
