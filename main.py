from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
from openai import OpenAI
import dateparser
import models, schemas, database
from datetime import datetime
import pytz # timezone 처리를 위해 추가

# DB 테이블 생성
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

# CORS 설정 (아이폰 웹 접속 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI 클라이언트
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# --- [API 1] 음성 분석 (방어 코드 적용됨) ---
@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    text = "" 
    
    try:
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # Whisper 호출
        with open(temp_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="ko"
            )
        text = transcript.text
        print(f"✅ 분석 성공: {text}")

    except Exception as e:
        print(f"❌ 분석 에러: {e}")
        text = "인식 실패"
        
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
    # [핵심 수정] 한국 시간 기준으로 날짜 분석
    parsed_datetime = None
    if text and text not in ["인식 실패", "목소리가 들리지 않습니다."]:
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst) # 현재 한국 시간
        
        # dateparser 설정 강화
        parsed_datetime = dateparser.parse(
            text, 
            languages=['ko'],
            settings={
                'RELATIVE_BASE': now_kst.replace(tzinfo=None), # 기준점: 한국 시간
                'PREFER_DATES_FROM': 'future', # "7시" 하면 미래의 7시로
                'PREFER_DAY_OF_MONTH': 'first',
                'RETURN_AS_TIMEZONE_AWARE': False 
            }
        )
    
    return {
        "original_text": text,
        "parsed_date": parsed_datetime,
        "suggested_title": text 
    }

# --- [API 2] 할 일 저장 ---
@app.post("/tasks", response_model=schemas.TaskResponse)
def create_task(task: schemas.TaskCreate, db: Session = Depends(database.get_db)):
    new_task = models.Task(
        title=task.title,
        due_date=task.due_date,
        description=task.description
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

# --- [API 3] 목록 조회 ---
@app.get("/tasks", response_model=List[schemas.TaskResponse])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    tasks = db.query(models.Task).order_by(models.Task.due_date).offset(skip).limit(limit).all()
    return tasks

# --- [API 4] 완료 처리 ---
@app.patch("/tasks/{task_id}")
def update_task_status(task_id: int, is_completed: bool, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.is_completed = is_completed
    db.commit()
    return {"message": "Updated"}

# --- [API 5] 삭제 ---
@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return {"message": "Deleted"}