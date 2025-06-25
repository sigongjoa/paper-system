import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import Base # models.py에서 Base 임포트

logger = logging.getLogger(__name__)

DATABASE_URL = "sqlite:///./citation_graph/papers.db"

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
        engine = get_engine()
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        logger.debug("새로운 SessionLocal 팩토리 생성")
    logger.debug("get_session_local 함수 종료")
    return SessionLocal

def create_db_and_tables():
    logger.debug("create_db_and_tables 함수 시작")
    engine = get_engine()
    Base.metadata.create_all(engine) # 모든 테이블 생성
    logger.info("데이터베이스와 테이블이 성공적으로 생성되었습니다.")
    logger.debug("create_db_and_tables 함수 종료") 