# models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base

class Task(Base):
    __tablename__ = "tasks" # 테이블 이름

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)       # 할 일 내용
    description = Column(String, nullable=True) # 메모 (선택)
    due_date = Column(DateTime, nullable=True)  # 마감 시간
    is_completed = Column(Boolean, default=False) # 완료 여부
    created_at = Column(DateTime(timezone=True), server_default=func.now()) # 생성일 자동입력