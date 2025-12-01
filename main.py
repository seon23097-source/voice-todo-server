from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
from openai import OpenAI
# [변경] search_dates 추가
import dateparser
from dateparser.search import search_dates 
import models, schemas, database
from datetime import datetime, timedelta
import pytz
import regex

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

# [API 1] 음성 분석 (search_dates 적용)
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
            print(f"✅ 분석 성공: {text}")

    except Exception as e:
        print(f"❌ 분석 에러: {e}")
        text = "인식 실패"
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)
            
    # [핵심 변경] 문장 속에서 날짜 찾기 (search_dates)
    parsed_datetime = None
    if text and text not in ["인식 실패", "목소리가 들리지 않습니다."]:
        try:
            kst = pytz.timezone('Asia/Seoul')
            now_kst = datetime.now(kst)
            
            # 1. 설정: 한국 시간 기준, 미래 날짜 선호
            settings = {
                'RELATIVE_BASE': now_kst.replace(tzinfo=None),
                'PREFER_DATES_FROM': 'future',
                'PREFER_DAY_OF_MONTH': 'first',
                'RETURN_AS_TIMEZONE_AWARE': False, # 단순 날짜값만 추출
                'STRICT_PARSING': False
            }
            
            # 2. 문장 안에서 날짜 검색!
            # 결과 예시: [('내일 아침 7시', datetime객체)]
            found_dates = search_dates(text, languages=['ko'], settings=settings)
            
            if found_dates:
                # 찾은 것 중 가장 마지막에 언급된 날짜를 사용 (보통 구체적인 시간은 뒤에 나옴)
                # 예: "내일 밥" -> '내일' 추출
                # 예: "내일 아침 7시 밥" -> '내일 아침 7시' 추출
                date_text, date_obj = found_dates[-1] 
                parsed_datetime = date_obj
                print(f"📅 날짜 추출됨: {date_text} -> {parsed_datetime}")
            else:
                print("⚠️ 날짜 정보 없음")

        except Exception as e:
            print(f"날짜 분석 중 오류: {e}")
    
    return {
        "original_text": text,
        "parsed_date": parsed_datetime,
        "suggested_title": text 
    }

# --- [나머지 API는 기존과 동일하게 유지] ---
# (create_task, read_tasks, update_task_status, delete_task 코드는 그대로 두시면 됩니다)
# 만약 덮어쓰기라 다 지워졌다면 아래 코드를 다시 복사해서 main.py 아래에 붙여넣으세요.

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