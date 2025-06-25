import logging
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

logger = logging.getLogger(__name__)

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'

    paper_id = Column(String, primary_key=True)
    external_id = Column(String, nullable=True)
    platform = Column(String)
    title = Column(Text)
    abstract = Column(Text, nullable=True)
    authors = Column(JSON, nullable=True)
    categories = Column(JSON, nullable=True)
    pdf_url = Column(String, nullable=True)
    embedding = Column(JSON, nullable=True)
    published_date = Column(DateTime, nullable=True)
    updated_date = Column(DateTime, nullable=True)
    year = Column(Integer, nullable=True)
    references_ids = Column(JSON, nullable=True) # IDs of papers this paper cites
    cited_by_ids = Column(JSON, nullable=True) # IDs of papers that cite this paper

    # Define relationships for citations
    citing_papers = relationship("Citation", foreign_keys="Citation.cited_paper_id", backref="cited_paper_obj", primaryjoin="Paper.paper_id == Citation.cited_paper_id")
    cited_papers = relationship("Citation", foreign_keys="Citation.citing_paper_id", backref="citing_paper_obj", primaryjoin="Paper.paper_id == Citation.citing_paper_id")

    def __init__(self, **kwargs):
        logger.debug(f"Paper 모델 __init__ 함수 시작 - paper_id: {kwargs.get('paper_id')}")
        super().__init__(**kwargs)
        logger.debug(f"Paper 모델 __init__ 함수 종료 - paper_id: {self.paper_id}")

    def __repr__(self):
        return f"<Paper(title='{self.title[:20] if self.title else 'N/A'}...', platform='{self.platform}', year={self.year})>"

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
            "year": self.year,
            "references_ids": self.references_ids,
            "cited_by_ids": self.cited_by_ids,
        }
        logger.debug(f"Paper 모델 to_dict 함수 종료 - paper_id: {self.paper_id}")
        return result

class Citation(Base):
    __tablename__ = 'citations'

    citing_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)

    def __init__(self, **kwargs):
        logger.debug(f"Citation 모델 __init__ 함수 시작 - citing_paper_id: {kwargs.get('citing_paper_id')}, cited_paper_id: {kwargs.get('cited_paper_id')}")
        super().__init__(**kwargs)
        logger.debug(f"Citation 모델 __init__ 함수 종료 - citing_paper_id: {self.citing_paper_id}, cited_paper_id: {self.cited_paper_id}")

    def __repr__(self):
        return f"<Citation(citing_paper_id='{self.citing_paper_id}', cited_paper_id='{self.cited_paper_id}')>" 