from sqlalchemy import Column, Integer, Boolean, BigInteger, String, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic import BaseModel
from typing import Optional

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'

    user_id = Column(Integer, primary_key=True)
    trials_used = Column(Integer, default=0)
    is_paid = Column(Boolean, default=False)
    subscription_expiry = Column(BigInteger, default=0)
    referrer_id = Column(Integer, nullable=True)
    referral_code = Column(String(255), unique=True, nullable=True)
    free_weeks = Column(Integer, default=0)

class UserData(BaseModel):
    user_id: int
    trials_used: int = 0
    is_paid: bool = False
    subscription_expiry: int = 0
    referrer_id: Optional[int] = None
    referral_code: Optional[str] = None
    free_weeks: int = 0
