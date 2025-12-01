from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
import shutil
import os
import json 
from openai import OpenAI
import models, schemas, database
from datetime import datetime
import pytz

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

@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    text = ""
    result_title = ""
    result_date = None
    
    try:
        # 1. 저장
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # 2. Whisper
        # [로그 변경됨] 이 로그가 안 뜨면 배포 안 된 겁니다!
        print("📢 [1단계] Whisper 변환 시작...") 
        with open(temp_filename, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1", file=audio_file, language="ko"
            )
        text = transcript.text
        print(f"✅ [1단계 완료] 텍스트: {text}")

        # 3. GPT-4o-mini
        if text:
            print("🧠 [2단계] GPT 지능 분석 시작...")
            
            kst = pytz.timezone('Asia/Seoul')
            now_str = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

            # 프롬프트: 날짜와 할 일을 분리하라는 명령
            prompt = f"""
            기준시간: {now_str}
            문장: "{text}"
            
            1. '할일(title)'과 '날짜(date)'를 분리해.
            2. 날짜는 'YYYY-MM-DDTHH:MM:SS' 형식. 없으면 null.
            3. title에서는 날짜 관련 단어(내일, 7시 등)를 제거해.
            JSON으로만 답해. 예: {{"title": "밥 먹기", "date": "2025-12-02T07:00:00"}}
            """

            completion = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "JSON output only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"}
            )
            
            gpt_response = completion.choices[0].message.content
            print(f"✅ [2단계 완료] GPT 응답: {gpt_response}") # 이 로그가 떠야 함!
            
            parsed = json.loads(gpt_response)
            result_title = parsed.get("title", text)
            date_str = parsed.get("date")
            
            if date_str:
                try:
                    result_date = datetime.fromisoformat(date_str)
                except:
                    result_date = None

    except Exception as e:
        print(f"❌ [에러 발생] {e}")
        text = "서버 에러"
        result_title = "에러 발생"
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)
            
    return {
        "original_text": text,
        "parsed_date": result_date,
        "suggested_title": result_title if result_title else text
    }

# --- CRUD API 유지 ---
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

# (맨 아래에 이런 거 하나 적으세요)
# 강제 업데이트용 주석