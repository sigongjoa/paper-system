import logging
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'
    id = Column(String, primary_key=True) # DOI or unique ID
    title = Column(String, nullable=False)
    authors = Column(String) # Comma separated authors
    year = Column(Integer)
    abstract = Column(String)

    # Relationship for papers cited by this paper (references)
    citations_made = relationship(
        "Citation",
        foreign_keys="Citation.citing_paper_id",
        back_populates="citing_paper"
    )
    # Relationship for papers that cite this paper (cited by)
    citations_received = relationship(
        "Citation",
        foreign_keys="Citation.cited_paper_id",
        back_populates="cited_paper"
    )

    def __repr__(self):
        return f"<Paper(id='{self.id}', title='{self.title}')>"

class Citation(Base):
    __tablename__ = 'citations'
    citing_paper_id = Column(String, ForeignKey('papers.id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.id'), primary_key=True)

    citing_paper = relationship("Paper", foreign_keys=[citing_paper_id])
    cited_paper = relationship("Paper", foreign_keys=[cited_paper_id])

    def __repr__(self):
        return f"<Citation(citing='{self.citing_paper_id}', cited='{self.cited_paper_id}')>"

DATABASE_URL = "sqlite:///./papers.db" # SQLite database file

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    logger.debug("init_db 함수 진입")
    try:
        Base.metadata.create_all(bind=engine)
        logger.debug("데이터베이스 테이블이 성공적으로 생성되었습니다.")
    except Exception as e:
        logger.debug(f"데이터베이스 테이블 생성 중 오류 발생: {e}")
        raise # 예외를 다시 발생시켜 상위 호출자에게 알림
    logger.debug("init_db 함수 종료")

def get_db():
    logger.debug("get_db 함수 진입")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        logger.debug("get_db 함수 종료") 