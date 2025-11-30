# main.py
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware # [추가] 이 줄 꼭 필요!
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

# --- [여기부터 추가] CORS 허용 설정 ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 곳에서 접속 허용 (보안상 나중엔 주소 지정 권장)
    allow_credentials=True,
    allow_methods=["*"],  # 모든 통신 방식(GET, POST 등) 허용
    allow_headers=["*"],  # 모든 헤더 허용
)

# OpenAI 키 설정 (환경변수 권장)
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

# --- [API 1] 음성 분석 (저장 X, 분석만 해서 앱에 돌려줌) ---
@app.post("/analyze-voice", response_model=schemas.VoiceParseResult)
async def analyze_voice(file: UploadFile = File(...)):
    temp_filename = f"temp_{file.filename}"
    text = "" # [중요] 변수 미리 생성 (에러 방지)
    
    try:
        # 1. 파일 저장
        with open(temp_filename, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # [디버깅] 파일 크기 확인 (로그에 찍힘)
        file_size = os.path.getsize(temp_filename)
        print(f"📁 수신된 파일 크기: {file_size} bytes")
        
        if file_size < 100: # 너무 작으면(소리가 없으면) 처리 안 함
            text = "목소리가 들리지 않습니다."
        else:
            # 2. Whisper 호출
            print("🤖 Whisper 분석 시작...")
            with open(temp_filename, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1", 
                    file=audio_file,
                    language="ko"
                )
            text = transcript.text
            print(f"✅ 분석 완료: {text}")

    except Exception as e:
        print(f"❌ 에러 발생: {e}") # [중요] 로그에 진짜 에러 원인이 찍힘
        text = "인식 실패"
        
    finally:
        if os.path.exists(temp_filename):
            os.remove(temp_filename)
            
    # 3. 날짜 분석 (text가 있어도 없어도 안전하게 실행)
    parsed_datetime = None
    if text and text not in ["인식 실패", "목소리가 들리지 않습니다."]:
        parsed_datetime = dateparser.parse(text, languages=['ko'])
    
    return {
        "original_text": text,
        "parsed_date": parsed_datetime,
        "suggested_title": text
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