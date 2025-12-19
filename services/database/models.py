from sqlalchemy import BigInteger, String, Boolean, DateTime, Integer, Text, func, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from datetime import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    # Основные данные
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="Unknown")
    user_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Язык пользователя
    language: Mapped[str] = mapped_column(String(2), default="en")
    
    # Статусы пользователя
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    ban_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    # Даты
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    username_updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    
    # Last.FM интеграция
    lastfm_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Статистика
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Куки (локальные - для пользователя)
    cookies_youtube: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies_tiktok: Mapped[str | None] = mapped_column(Text, nullable=True)
    cookies_vk: Mapped[str | None] = mapped_column(Text, nullable=True)


class SystemSettings(Base):
    __tablename__ = "system_settings"
    
    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class GlobalCookies(Base):
    __tablename__ = "global_cookies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    platform: Mapped[str] = mapped_column(String(50))  # youtube, tiktok, vk, instagram, etc
    cookies_data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class MediaCache(Base):
    __tablename__ = "media_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    url: Mapped[str] = mapped_column(Text)  # normalized/cleaned URL

    media_type: Mapped[str] = mapped_column(String(16))  # video|audio|photo|document
    file_id: Mapped[str] = mapped_column(String(512))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    last_used_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "url", "media_type", name="uq_media_cache_user_url_type"),
        Index("ix_media_cache_user_type", "user_id", "media_type"),
    )


class UserRequest(Base):
    __tablename__ = "user_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)

    kind: Mapped[str] = mapped_column(String(32), default="message")  # message|inline|text_search|admin
    input_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)

    media_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("media_cache.id"), nullable=True)

    __table_args__ = (
        Index("ix_user_requests_user_created", "user_id", "created_at"),
    )


class UserOAuthToken(Base):
    __tablename__ = "user_oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    service: Mapped[str] = mapped_column(String(32), index=True)  # spotify|yandex
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'service', name='uq_user_oauth_tokens_user_service'),
        Index('ix_user_oauth_tokens_user_service', 'user_id', 'service'),
    )


class OAuthState(Base):
    __tablename__ = "oauth_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    service: Mapped[str] = mapped_column(String(32), index=True)  # spotify|yandex
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)

    __table_args__ = (
        Index("ix_oauth_states_service_user", "service", "user_id"),
    )