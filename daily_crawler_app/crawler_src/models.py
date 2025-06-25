from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship # Added for relationships
import logging # logging 임포트 추가

logger = logging.getLogger(__name__) # 로거 인스턴스 생성

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'

    paper_id = Column(String, primary_key=True)
    external_id = Column(String)
    platform = Column(String)
    title = Column(Text)
    abstract = Column(Text)
    authors = Column(JSON)
    categories = Column(JSON)
    pdf_url = Column(String)
    embedding = Column(JSON, nullable=True) # Assuming embedding can be null
    published_date = Column(DateTime)
    updated_date = Column(DateTime)
    crawled_date = Column(DateTime, nullable=True) # New field for crawl date
    year = Column(Integer) # Added year column
    references_ids = Column(JSON, nullable=True) # New field for IDs of papers this paper cites
    cited_by_ids = Column(JSON, nullable=True) # New field for IDs of papers that cite this paper

    # Define relationships for citations
    citing_papers = relationship("Citation", foreign_keys="Citation.cited_paper_id", backref="cited_paper", primaryjoin="Paper.paper_id == Citation.cited_paper_id")
    cited_papers = relationship("Citation", foreign_keys="Citation.citing_paper_id", backref="citing_paper", primaryjoin="Paper.paper_id == Citation.citing_paper_id")

    def __init__(self, **kwargs):
        logger.debug("Paper 모델 __init__ 함수 시작") # Add this for init
        super().__init__(**kwargs)
        logger.debug(f"Paper 모델 __init__ 함수 종료 - paper_id: {self.paper_id}")

    def __repr__(self):
        return f"<Paper(title='{self.title[:20]}...', platform='{self.platform}', year={self.year})>"

    def to_dict(self):
        logger.debug(f"Paper 모델 to_dict 함수 시작 - paper_id: {self.paper_id}")
        result = {
            "paper_id": self.paper_id,
            "external_id": self.external_id,
            "platform": self.platform,
            "title": self.title,
            "abstract": self.abstract,
            "authors": self.authors,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "embedding": self.embedding,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
            "crawled_date": self.crawled_date.isoformat() if self.crawled_date else None, # Added to dict
            "year": self.year, # Added year to dict
            "references_ids": self.references_ids, # Added to dict
            "cited_by_ids": self.cited_by_ids, # Added to dict
        }
        logger.debug(f"Paper 모델 to_dict 함수 종료 - paper_id: {self.paper_id}")
        return result

class Citation(Base):
    __tablename__ = 'citations'

    citing_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)

    def __init__(self, **kwargs):
        logger.debug("Citation 모델 __init__ 함수 시작") # Add this for init
        super().__init__(**kwargs)
        logger.debug(f"Citation 모델 __init__ 함수 종료 - citing_paper_id: {self.citing_paper_id}, cited_paper_id: {self.cited_paper_id}")

    def __repr__(self):
        return f"<Citation(citing_paper_id='{self.citing_paper_id}', cited_paper_id='{self.cited_paper_id}')>" 