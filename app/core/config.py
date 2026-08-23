from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    PROJECT_NAME: str = "TaskFlow API"
    PROJECT_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # 生产默认使用 PostgreSQL(asyncpg)，本地测试可切换 SQLite。
    DATABASE_URL: str = (
        "postgresql+asyncpg://taskflow:taskflow@localhost:5432/taskflow"
    )

    SECRET_KEY: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # 逗号分隔的允许来源，例如 https://a.com,https://b.com
    BACKEND_CORS_ORIGINS: str = "*"

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.BACKEND_CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def async_database_url(self) -> str:
        """统一为 asyncpg 驱动需要的连接串。

        Render Blueprint 注入的 DATABASE_URL 通常是 postgres:// 或
        postgresql:// 格式，SQLAlchemy 异步模式需要 postgresql+asyncpg://。
        """
        parts = urlsplit(self.DATABASE_URL)
        if parts.scheme in ("postgres", "postgresql"):
            return urlunsplit(("postgresql+asyncpg",) + parts[1:])
        return self.DATABASE_URL

@lru_cache
def get_settings() -> Settings:
    return Settings()
