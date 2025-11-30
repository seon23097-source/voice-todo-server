# schemas.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

# 앱 -> 서버로 보낼 때 (생성 요청)
class TaskCreate(BaseModel):
    title: str
    due_date: Optional[datetime] = None
    description: Optional[str] = None

# 서버 -> 앱으로 보낼 때 (응답)
class TaskResponse(TaskCreate):
    id: int
    is_completed: bool
    created_at: datetime

    class Config:
        from_attributes = True

# 음성 분석 결과만 보여줄 때
class VoiceParseResult(BaseModel):
    original_text: str
    parsed_date: Optional[datetime]
    suggested_title: str