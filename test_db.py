# test_db.py
import psycopg2

try:
    # 여기에 정보를 직접 입력해서 테스트해보세요
    connection = psycopg2.connect(
        host="svc.sel3.cloudtype.app",  # 에러 메시지에 뜬 주소
        port="30741",                   # 에러 메시지에 뜬 포트
        database="postgres",            # 보통 기본 DB 이름은 postgres
        user="root",                # 1순위: postgres 로 먼저 해보세요
        # user="admin",                 # 2순위: 안되면 admin 로 해보세요
        password="milo8sge0129aa66"
    )
    print("✅ 접속 성공! 아이디와 비밀번호가 맞습니다.")
    connection.close()
    
except Exception as e:
    print("❌ 접속 실패...")
    print(e)