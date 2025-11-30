from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import urllib.parse # 이 줄 추가!

# 1. 여기에 본인 정보를 각각 입력하세요 (주소 통째로 말고 나눠서)
USER = "root"
PASSWORD = "milo8sge0129aa66"
HOST = "svc.sel3.cloudtype.app" # 주소 (포트 앞부분까지)
PORT = "30741" # 포트 번호
DB_NAME = "postgres"

# 2. 비밀번호의 특수문자를 컴퓨터가 이해하는 문자로 변환 (URL Encoding)
encoded_password = urllib.parse.quote_plus(PASSWORD)

# 3. 안전한 주소 생성
SQLALCHEMY_DATABASE_URL = f"postgresql://{USER}:{encoded_password}@{HOST}:{PORT}/{DB_NAME}"

# --- 아래는 기존과 동일 ---
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()