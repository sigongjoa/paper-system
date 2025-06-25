import logging
from sqlalchemy.orm import Session
from citation_graph.backend.crawling_manager import MultiPlatformCrawlingManager
from citation_graph.backend.database import get_session_local, create_db_and_tables
from citation_graph.backend.models import Paper, Citation

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_test_crawl():
    logger.info("Test crawl 스크립트 시작.")

    # 1. 데이터베이스 초기화 (테스트를 위해 기존 데이터 삭제 후 재생성)
    # 실제 앱에서는 이 단계를 피하고, save_papers_to_db가 업데이트를 처리해야 합니다.
    # 여기서는 확실한 테스트를 위해 db 파일을 삭제하는 것이 가장 좋습니다.
    # 하지만 파일 삭제는 수동으로 요청드리겠습니다.
    # 사용자님, 테스트 전에 'papers.db' 파일을 한 번 더 삭제해주시면 좋습니다.
    # 예: `rm citation_graph/papers.db` (Windows에서는 `del citation_graph\papers.db`)
    
    create_db_and_tables() # 데이터베이스 테이블 재생성

    db: Session = get_session_local()()
    try:
        crawling_manager = MultiPlatformCrawlingManager()
        
        test_paper_id = "1807.01232" # 테스트할 논문 ID
        logger.info(f"논문 ID {test_paper_id} 크롤링 및 저장을 시도합니다.")
        
        # 크롤링 및 저장 로직 호출
        crawled_data = crawling_manager.crawl_and_save_paper_by_id(test_paper_id, "arxiv", db)
        
        if crawled_data:
            logger.info(f"논문 {test_paper_id} 크롤링 및 저장/업데이트 성공.")
        else:
            logger.error(f"논문 {test_paper_id} 크롤링 및 저장/업데이트 실패.")
            return

        # 2. 저장된 논문 데이터 확인
        retrieved_paper = db.query(Paper).filter(Paper.paper_id == test_paper_id).first()

        if retrieved_paper:
            logger.info(f"데이터베이스에서 논문 {test_paper_id} 조회 성공:")
            logger.info(f"  제목: {retrieved_paper.title}")
            logger.info(f"  Authors: {retrieved_paper.authors}")
            logger.info(f"  References IDs: {retrieved_paper.references_ids}")
            logger.info(f"  Cited By IDs: {retrieved_paper.cited_by_ids}")

            # 3. 인용 관계 확인
            citations = db.query(Citation).filter(Citation.citing_paper_id == test_paper_id).all()
            cited_by = db.query(Citation).filter(Citation.cited_paper_id == test_paper_id).all()

            logger.info(f"  총 인용 관계 (References): {len(citations)}개")
            for cit_rel in citations:
                cited_paper_title = db.query(Paper).filter(Paper.paper_id == cit_rel.cited_paper_id).first()
                if cited_paper_title:
                    logger.info(f"    -> {cited_paper_title.title}")
                else:
                    logger.info(f"    -> 제목을 찾을 수 없음 (ID: {cit_rel.cited_paper_id})")

            logger.info(f"  총 피인용 관계 (Cited By): {len(cited_by)}개")
            for cit_rel in cited_by:
                citing_paper_title = db.query(Paper).filter(Paper.paper_id == cit_rel.citing_paper_id).first()
                if citing_paper_title:
                    logger.info(f"    <- {citing_paper_title.title}")
                else:
                    logger.info(f"    <- 제목을 찾을 수 없음 (ID: {cit_rel.citing_paper_id})")
        else:
            logger.error(f"데이터베이스에서 논문 {test_paper_id}을(를) 찾을 수 없습니다.")

    except Exception as e:
        logger.error(f"Test crawl 스크립트 실행 중 오류 발생: {e}", exc_info=True)
    finally:
        db.close()
        logger.info("Test crawl 스크립트 종료.")

if __name__ == "__main__":
    run_test_crawl() 