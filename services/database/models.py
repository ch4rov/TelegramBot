from sqlalchemy import BigInteger, String, Boolean, DateTime, Integer, Text, func
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