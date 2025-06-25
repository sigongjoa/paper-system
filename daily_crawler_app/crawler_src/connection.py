from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base
import logging

logger = logging.getLogger(__name__)

# 더미 데이터베이스 연결을 위한 설정 (실제 사용 시에는 적절히 구성해야 합니다)
DATABASE_URL = "sqlite:///./papers.db" # 테스트용 SQLite 인메모리 데이터베이스, 이름 변경

engine = None
SessionLocal = None

def get_engine():
    logger.debug("get_engine 함수 시작")
    global engine
    if engine is None:
        engine = create_engine(DATABASE_URL)
        logger.debug(f"새로운 데이터베이스 엔진 생성: {DATABASE_URL}")
    logger.debug("get_engine 함수 종료")
    return engine

def get_session_local():
    logger.debug("get_session_local 함수 시작")
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
        logger.debug("새로운 SessionLocal 팩토리 생성")
    logger.debug("get_session_local 함수 종료")
    return SessionLocal

def create_db_and_tables():
    logger.debug("create_db_and_tables 함수 시작")
    engine = get_engine()
    Base.metadata.create_all(engine) # 모든 테이블 생성
    logger.info("데이터베이스와 테이블이 성공적으로 생성되었습니다.")
    logger.debug("create_db_and_tables 함수 종료")

class Session:
    """Mock Session class for testing."""
    def __init__(self, bind=None):
        logger.debug("Session mock __init__ 함수 시작")
        pass

    def query(self, *args, **kwargs):
        logger.debug("Session mock query 함수 호출")
        return MockQuery()

    def add(self, *args, **kwargs):
        logger.debug(f"Session mock add 함수 호출 - data: {args[0] if args else 'N/A'}")
        pass

    def commit(self):
        logger.debug("Session mock commit 함수 호출")
        pass

    def rollback(self):
        logger.debug("Session mock rollback 함수 호출")
        pass

    def close(self):
        logger.debug("Session mock close 함수 호출")
        pass

class MockQuery:
    """Mock Query class for testing."""
    def filter_by(self, *args, **kwargs):
        logger.debug(f"MockQuery filter_by 함수 호출 - filter: {kwargs}")
        return self

    def first(self):
        logger.debug("MockQuery first 함수 호출")
        return None # Always return None for first to simulate no existing paper 