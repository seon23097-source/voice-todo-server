from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import shutil
import os
import json # JSON 처리를 위해 추가
from openai import OpenAI
import models, schemas, database
from datetime import datetime
import pytz

# DB 테이블 생성
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OpenAI 클라이언트
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# [API 1] 스마트 음성 분석 (GPT-4o-mini 사용)
@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    text = ""
    result_title = ""
    result_date = None
    
    try:
        # 1. 파일 저장
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        file_size = os.path.getsize(temp_filename)
        if file_size < 100:
            text = "목소리가 들리지 않습니다."
        else:
            # 2. Whisper (귀): 음성을 텍스트로 변환
            with open(temp_filename, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", file=audio_file, language="ko"
                )
            text = transcript.text
            print(f"✅ [Whisper] 들은 내용: {text}")

            # 3. GPT (뇌): 텍스트에서 '할 일'과 '시간' 분리
            if text:
                kst = pytz.timezone('Asia/Seoul')
                now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")
                
                # GPT에게 내리는 지령
                prompt = f"""
                현재 시간은 {now_kst} (한국 시간)이야.
                사용자의 말: "{text}"
                
                위 말에서 '할 일 내용(title)'과 '마감 시간(due_date)'을 추출해서 JSON으로 줘.
                
                규칙:
                1. due_date는 반드시 'YYYY-MM-DDTHH:MM:SS' 형식이어야 해.
                2. 날짜/시간 언급이 없으면 due_date는 null로 해.
                3. title에는 날짜/시간 관련 단어를 빼고 핵심 내용만 적어. (예: "내일 밥" -> "밥")
                4. 내일, 모레, 다음주 등은 현재 시간을 기준으로 계산해.
                """

                completion = client.chat.completions.create(
                    model="gpt-4o-mini", # 가성비 최고 모델 (빠르고 정확함)
                    messages=[
                        {"role": "system", "content": "너는 일정 관리 비서야. JSON 형식으로만 답해."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"} # 무조건 JSON으로 뱉게 강제
                )
                
                # GPT 응답 해석
                gpt_response = completion.choices[0].message.content
                print(f"🧠 [GPT] 분석 결과: {gpt_response}")
                
                parsed_json = json.loads(gpt_response)
                result_title = parsed_json.get("title", text)
                
                # 날짜 문자열을 datetime 객체로 변환
                date_str = parsed_json.get("due_date")
                if date_str:
                    try:
                        result_date = datetime.fromisoformat(date_str)
                    except:
                        result_date = None

    except Exception as e:
        print(f"❌ 에러 발생: {e}")
        text = "인식 실패"
        result_title = "인식 실패"
        
    finally:
        if os.path.exists(temp_filename): os.remove(temp_filename)
            
    return {
        "original_text": text,
        "parsed_date": result_date,
        "suggested_title": result_title if result_title else text
    }

# --- [CRUD API는 기존 유지] ---
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