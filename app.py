import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Union

from database import init_db, get_db, Paper, Citation, SessionLocal # .database -> database 변경

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    logger.debug("애플리케이션 시작 이벤트 감지")
    init_db()
    logger.debug("데이터베이스 초기화 완료")
    # Add some sample data for testing
    db = SessionLocal()
    try:
        add_sample_data(db)
        logger.debug("샘플 데이터 추가 완료")
    finally:
        db.close()

def add_sample_data(db: Session):
    logger.debug("add_sample_data 함수 진입")
    # Clear existing data for clean test runs
    db.query(Citation).delete()
    db.query(Paper).delete()
    db.commit()

    paper1 = Paper(id="10.1000/paper1", title="Deep Learning for NLP", authors="John Doe, Jane Smith", year=2020, abstract="Abstract 1")
    paper2 = Paper(id="10.1000/paper2", title="Graph Neural Networks", authors="Alice Wonderland", year=2021, abstract="Abstract 2")
    paper3 = Paper(id="10.1000/paper3", title="Attention Mechanisms in Transformers", authors="Bob The Builder", year=2019, abstract="Abstract 3")
    paper4 = Paper(id="10.1000/paper4", title="Reinforcement Learning Basics", authors="Charlie Chaplin", year=2022, abstract="Abstract 4")
    paper5 = Paper(id="10.1000/paper5", title="Convolutional Neural Networks", authors="Diana Prince", year=2018, abstract="Abstract 5")

    db.add_all([paper1, paper2, paper3, paper4, paper5])
    db.commit()
    logger.debug("샘플 논문 데이터 추가 완료")

    citation1 = Citation(citing_paper_id=paper1.id, cited_paper_id=paper2.id) # P1 cites P2
    citation2 = Citation(citing_paper_id=paper1.id, cited_paper_id=paper3.id) # P1 cites P3
    citation3 = Citation(citing_paper_id=paper2.id, cited_paper_id=paper4.id) # P2 cites P4
    citation4 = Citation(citing_paper_id=paper3.id, cited_paper_id=paper1.id) # P3 cites P1 (cited by)
    citation5 = Citation(citing_paper_id=paper5.id, cited_paper_id=paper1.id) # P5 cites P1 (cited by)

    db.add_all([citation1, citation2, citation3, citation4, citation5])
    db.commit()
    db.refresh(paper1)
    db.refresh(paper2)
    db.refresh(paper3)
    db.refresh(paper4)
    db.refresh(paper5)
    logger.debug("샘플 인용 데이터 추가 완료")

    logger.debug("add_sample_data 함수 종료")

@app.get("/api/graph/{paper_id}", response_model=Dict[str, List[Dict[str, Union[str, int]]]])
async def get_citation_graph(paper_id: str, db: Session = Depends(get_db)):
    logger.debug(f"get_citation_graph 함수 진입 - paper_id: {paper_id}")
    paper = db.query(Paper).filter(Paper.id == paper_id).first()

    if not paper:
        logger.debug(f"논문을 찾을 수 없음: {paper_id}")
        raise HTTPException(status_code=404, detail="Paper not found")

    nodes = []
    edges = []

    # Add the central paper as a node
    nodes.append({"id": paper.id, "label": paper.title, "group": "central"})

    # Add cited papers (references)
    for citation in paper.citations_made:
        cited_paper = db.query(Paper).filter(Paper.id == citation.cited_paper_id).first()
        if cited_paper:
            nodes.append({"id": cited_paper.id, "label": cited_paper.title, "group": "cited"})
            edges.append({"from": paper.id, "to": cited_paper.id, "arrows": "to", "label": "cites"})

    # Add citing papers (cited by)
    for citation in paper.citations_received:
        citing_paper = db.query(Paper).filter(Paper.id == citation.citing_paper_id).first()
        if citing_paper:
            nodes.append({"id": citing_paper.id, "label": citing_paper.title, "group": "citing"})
            edges.append({"from": citing_paper.id, "to": paper.id, "arrows": "to", "label": "cited by"})

    # Remove duplicate nodes using a set for efficiency
    unique_nodes = list({frozenset(node.items()): node for node in nodes}.values())

    logger.debug("get_citation_graph 함수 종료")
    return {"nodes": unique_nodes, "edges": edges} 