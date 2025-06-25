import logging
from datetime import datetime
from sqlalchemy.orm import Session
from .models import Paper, Citation
from .database import get_session_local, create_db_and_tables

logger = logging.getLogger(__name__)

def save_papers_to_db(papers_data: list, db: Session):
    logger.debug("save_papers_to_db 함수 시작")
    try:
        saved_count = 0
        skipped_count = 0
        citation_count = 0
        logger.debug(f"데이터베이스 저장을 위해 {len(papers_data)}개 논문 처리 중.")

        for data in papers_data:
            paper_id = data.get('paper_id')
            paper_title = data.get('title', 'N/A')
            if not paper_id:
                logger.warning("Paper ID가 없어 논문을 건너뜠니다.")
                skipped_count += 1
                continue

            logger.debug(f"'{paper_title}' 논문 확인 중.")
            existing_paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()

            if existing_paper:
                logger.info(f"'{paper_title}' 논문이 이미 존재합니다. 정보(references_ids, cited_by_ids)를 업데이트합니다.")
                # 기존 논문의 인용/피인용 ID 업데이트
                existing_paper.references_ids = data.get('references_ids', [])
                existing_paper.cited_by_ids = data.get('cited_by_ids', [])
                db.add(existing_paper) # 변경 사항을 세션에 반영
                updated_paper = existing_paper # 업데이트된 논문을 사용하도록 변경
            else:
                logger.debug(f"새 논문 추가: {paper_title[:50]}...")
                new_paper = Paper(
                    paper_id=paper_id,
                    external_id=data.get('external_id'),
                    platform=data.get('platform'),
                    title=data.get('title'),
                    abstract=data.get('abstract'),
                    authors=data.get('authors', []),
                    categories=data.get('categories', []),
                    pdf_url=data.get('pdf_url'),
                    embedding=data.get('embedding'),
                    published_date=data.get('published_date'),
                    updated_date=data.get('updated_date'),
                    year=data.get('year'),
                    references_ids=data.get('references_ids', []),
                    cited_by_ids=data.get('cited_by_ids', []),
                )
                db.add(new_paper)
                saved_count += 1
                updated_paper = new_paper # 새로 추가된 논문을 사용하도록 변경

            # 인용 관계 저장 및 업데이트
            current_paper_id = updated_paper.paper_id
            current_paper_title = updated_paper.title
            logger.debug(f"논문 '{current_paper_title}'의 인용 관계 처리 중.")

            # 이 논문이 인용하는 논문들 (references_ids)
            for cited_paper_id in data.get('references_ids', []):
                if cited_paper_id and current_paper_id != cited_paper_id:
                    # 중복 인용 관계 확인 및 추가
                    existing_citation = db.query(Citation).filter(
                        Citation.citing_paper_id == current_paper_id,
                        Citation.cited_paper_id == cited_paper_id
                    ).first()
                    if not existing_citation:
                        citation = Citation(citing_paper_id=current_paper_id, cited_paper_id=cited_paper_id)
                        db.add(citation)
                        citation_count += 1
                        # cited_paper 정보는 이 시점에는 없을 수 있으므로, 로그는 ID로만 남김
                        logger.debug(f"새 인용 관계 추가: '{current_paper_title}' -> '{cited_paper_id}'")
                    else:
                        logger.debug(f"인용 관계 '{current_paper_title}' -> '{cited_paper_id}'이(가) 이미 존재합니다. 건너뜠습니다.")

            # 이 논문을 인용한 논문들 (cited_by_ids)
            for citing_paper_id in data.get('cited_by_ids', []):
                if citing_paper_id and current_paper_id != citing_paper_id:
                    # 중복 피인용 관계 확인 및 추가
                    existing_citation = db.query(Citation).filter(
                        Citation.citing_paper_id == citing_paper_id,
                        Citation.cited_paper_id == current_paper_id
                    ).first()
                    if not existing_citation:
                        citation = Citation(citing_paper_id=citing_paper_id, cited_paper_id=current_paper_id)
                        db.add(citation)
                        citation_count += 1
                        # citing_paper 정보는 이 시점에는 없을 수 있으므로, 로그는 ID로만 남김
                        logger.debug(f"새 피인용 관계 추가: '{citing_paper_id}' -> '{current_paper_title}'")
                    else:
                        logger.debug(f"피인용 관계 '{citing_paper_id}' -> '{current_paper_title}'이(가) 이미 존재합니다. 건너뜠습니다.")

        db.commit()
        logger.info(f"총 {len(papers_data)}개 논문 처리 완료. 새 논문 {saved_count}개 저장, {skipped_count}개 업데이트/건너뜜, 인용 관계 {citation_count}개 저장/추가.")
    except Exception as e:
        db.rollback()
        logger.error(f"데이터베이스 저장 중 오류 발생: {e}", exc_info=True)
    logger.debug("save_papers_to_db 함수 종료") 