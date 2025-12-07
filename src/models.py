from sqlalchemy import Column, Integer, Boolean, BigInteger, String, create_engine, DateTime, Text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(255), nullable=True)  # Telegram username like @Zak_Yuri
    trials_used = Column(Integer, default=0)
    transcription_count = Column(Integer, default=0)  # How many transcriptions user has done
    is_paid = Column(Boolean, default=False)
    subscription_expiry = Column(BigInteger, default=0)  # Timestamp when subscription expires
    referrer_id = Column(Integer, nullable=True)
    referral_code = Column(String(255), unique=True, nullable=True)
    free_weeks = Column(Integer, default=0)

class AuditLog(Base):
    __tablename__ = 'audit_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    details = Column(JSON, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    ip_address = Column(String(45), nullable=True)  # IPv6 support
    user_agent = Column(Text, nullable=True)

class UserData(BaseModel):
    user_id: int
    username: Optional[str] = None
    trials_used: int = 0
    transcription_count: int = 0
    is_paid: bool = False
    subscription_expiry: int = 0
    referrer_id: Optional[int] = None
    referral_code: Optional[str] = None
    free_weeks: int = 0
