# src/models.py
"""Data models for the mandap entry management app.
We use SQLAlchemy for persistence and Pydantic for validation of JSON payloads.
"""
import enum
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from pydantic import BaseModel, Field, validator

Base = declarative_base()

class Religion(str, enum.Enum):
    HINDU = "Hindu"
    NON_HINDU = "Non-Hindu"

class Visitor(Base):
    __tablename__ = "visitors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    religion = Column(Enum(Religion), nullable=False)
    reservation_id = Column(String, nullable=False, unique=True)
    arrival_time = Column(DateTime, nullable=False)
    processed = Column(Boolean, default=False)  # has the entry been allowed?
    created_at = Column(DateTime, default=datetime.utcnow)

# SQLite engine – the DB file lives under the project "data" directory.
import os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATA_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "data"))
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(DATA_DIR, "mandap.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    Base.metadata.create_all(bind=engine)

# Pydantic schemas used for JSON export / validation
class VisitorSchema(BaseModel):
    id: int
    name: str
    religion: Religion
    reservation_id: str
    arrival_time: datetime
    processed: bool
    created_at: datetime

    class Config:
        from_attributes = True

class DailyCountsSchema(BaseModel):
    date: datetime = Field(..., description="Date for which the counts are reported")
    total_visitors: int = Field(..., ge=0)
    hindu_visitors: int = Field(..., ge=0)
    non_hindu_visitors: int = Field(..., ge=0)
    pending_non_hindu: int = Field(..., ge=0)
    pending_hindu: int = Field(..., ge=0)

    @validator('hindu_visitors', 'non_hindu_visitors', 'pending_hindu', 'pending_non_hindu')
    def non_negative(cls, v):
        if v < 0:
            raise ValueError('must be non‑negative')
        return v
