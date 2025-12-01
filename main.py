from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
from openai import OpenAI
# 날짜 관련
import dateparser
from dateparser.search import search_dates 
import models, schemas, database
from datetime import datetime, timedelta
import pytz
import regex # 필수

models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# [API 1] 음성 분석 (디버깅 로그 추가됨)
@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    text = ""
    
    try:
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(temp_filename)
        if file_size < 100:
            text = "목소리가 들리지 않습니다."
        else:
            with open(temp_filename, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="ko"
                )
            text = transcript.text
            print(f"✅ [Whisper] 텍스트 변환: {text}") # 로그 확인용

    except Exception as e:
        print(f"❌ [Whisper] 에러: {e}")
        text = "인식 실패"
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)
            
    # [핵심] 날짜 분석 로직
    parsed_datetime = None
    if text and text not in ["인식 실패", "목소리가 들리지 않습니다."]:
        try:
            # 1. 한국 시간 기준 설정
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst).replace(tzinfo=None) # dateparser는 naive datetime을 좋아함
            
            print(f"🔎 [Date] 분석 시작: '{text}' (기준시간: {now_kst})")

            # 2. search_dates로 문장 속 날짜 찾기
            found = search_dates(text, languages=['ko'], settings={
                'RELATIVE_BASE': now_kst,
                'PREFER_DATES_FROM': 'future', # 미래 우선
                'PREFER_DAY_OF_MONTH': 'first',
                'STRICT_PARSING': False,
                'DATE_ORDER': 'YMD'
            })

            if found:
                # 찾은 것 로그 찍기
                for date_str, date_obj in found:
                    print(f"   -> 발견됨: '{date_str}' => {date_obj}")

                # [전략] 가장 긴 글자(구체적인 정보)를 가진 날짜를 선택
                # 예: "내일" vs "내일 아침 7시" -> 긴 게 더 정확함
                best_match = max(found, key=lambda x: len(x[0]))
                parsed_datetime = best_match[1]
                
                print(f"🎯 [Date] 최종 선택: {parsed_datetime}")
            else:
                print("⚠️ [Date] 날짜 정보를 찾을 수 없음 -> None 반환")

        except Exception as e:
            print(f"❌ [Date] 분석 중 에러: {e}")
    
    return {
        "original_text": text,
        "parsed_date": parsed_datetime,
        "suggested_title": text 
    }

# --- [나머지 API는 기존 유지] ---
@app.post("/tasks", response_model=schemas.TaskResponse)
def create_task(task: schemas.TaskCreate, db: Session = Depends(database.get_db)):
    new_task = models.Task(title=task.title, due_date=task.due_date, description=task.description)
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

@app.get("/tasks", response_model=List[schemas.TaskResponse])
def read_tasks(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    tasks = db.query(models.Task).order_by(models.Task.due_date).all()
    return tasks

@app.patch("/tasks/{task_id}")
def update_task_status(task_id: int, is_completed: bool, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task: raise HTTPException(status_code=404, detail="Not found")
    task.is_completed = is_completed
    db.commit()
    return {"message": "Updated"}

@app.delete("/tasks/{task_id}")
def delete_task(task_id: int, db: Session = Depends(database.get_db)):
    task = db.query(models.Task).filter(models.Task.id == task_id).first()
    if not task: raise HTTPException(status_code=404, detail="Not found")
    db.delete(task)
    db.commit()
    return {"message": "Deleted"}