# main.py
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from openai import OpenAI
import shutil
import os
import dateparser

# 우리가 만든 파일들 불러오기
import models, schemas, database

# 1. DB 테이블 자동 생성 (서버 켜질 때 없으면 만듦)
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

# OpenAI 키 설정 (환경변수 권장)
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# --- [API 1] 음성 분석 (저장 X, 분석만 해서 앱에 돌려줌) ---
@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    parsed_datetime = dateparser.parse(
    text, 
    languages=['ko'],
    settings={
        'PREFER_DATES_FROM': 'future',  # "7시"라고 하면 무조건 미래(오늘 저녁 or 내일)로
        'RELATIVE_BASE': datetime.now() # 기준 시간 명시
    }
)

    try:
        # 파일 저장
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Whisper로 텍스트 변환
        with open(temp_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="ko" 
            )
        
        text = transcript.text # 딕셔너리가 아니라 객체로 반환됨
        
        # 날짜 추출
        parsed_datetime = dateparser.parse(text, languages=['ko'])
        
        return {
            "original_text": text,
            "parsed_date": parsed_datetime, # 날짜 없으면 null
            "suggested_title": text         # 일단 전체 텍스트를 제목으로
        }
        
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

# --- [API 2] 할 일 저장 (앱에서 확인 버튼 누르면 실행) ---
@app.post("/tasks", response_model=schemas.TaskResponse)
def create_task(task: schemas.TaskCreate, db: Session = Depends(database.get_db)):
    # DB 모델 생성
    new_task = models.Task(
        title=task.title,
        due_date=task.due_date,
        description=task.description
    )
    db.add(new_task)
    db.commit() # 저장 확정
    db.refresh(new_task) # ID 등 생성된 정보 받아오기
    return new_task

# --- [API 3] 할 일 목록 조회 (날짜별 필터링 등 가능) ---
@app.get("/tasks", response_model=List[schemas.TaskResponse])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    tasks = db.query(models.Task).order_by(models.Task.due_date).offset(skip).limit(limit).all()
    return tasks

# --- [API 4] 완료 체크/해제 ---
@app.patch("/tasks/{task_id}")
def update_task_status(task_id: int, is_completed: bool, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    task.is_completed = is_completed
    db.commit()
    return {"message": "Updated successfully"}

# --- [API 5] 삭제 ---
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(task)
    db.commit()
    return {"message": "Deleted successfully"}