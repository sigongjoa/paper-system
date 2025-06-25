import os
import sys
import logging
from datetime import datetime, timedelta

# 모든 로거의 레벨을 DEBUG로 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# daily_crawler_app 디렉토리를 sys.path에 추가하여 crawler_src 모듈을 찾을 수 있도록 함
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from crawler_src.models import Base
from crawler_src.connection import get_engine, get_session_local, create_db_and_tables
from crawler_src.multi_platform_crawler import multi_platform_crawl, save_papers_to_db
from crawler_src.models import Paper

logger = logging.getLogger(__name__)

def run_test_crawl():
    logger.info("독립 크롤링 테스트 스크립트 시작")

    # 1. 데이터베이스 초기화 (기존 데이터 삭제 및 새 테이블 생성)
    db_path = os.path.join(current_dir, "papers.db")
    if os.path.exists(db_path):
        os.remove(db_path)
        logger.info(f"기존 데이터베이스 파일 삭제: {db_path}")
    
    create_db_and_tables()
    logger.info("데이터베이스 초기화 및 테이블 생성 완료")

    session = get_session_local()()

    # 2. 6월 20일 데이터 크롤링 (초기화 시나리오)
    logger.info("--- 6월 20일 데이터 크롤링 시작 (초기화) ---")
    start_date_20 = datetime(2024, 6, 19, 0, 0, 0)
    end_date_20 = datetime(2024, 6, 20, 23, 59, 59)
    
    try:
        logger.debug(f"[20일] multi_platform_crawl 호출 직전. 쿼리: research, 시작일: {start_date_20}, 종료일: {end_date_20}")
        crawled_papers_20 = list(multi_platform_crawl(query="research", platforms=['arxiv'], start_date=start_date_20, end_date=end_date_20, max_results=100))
        logger.debug(f"[20일] multi_platform_crawl 호출 직후. 크롤링된 논문 수: {len(crawled_papers_20)}")
        save_papers_to_db(crawled_papers_20)
        logger.info(f"6월 20일 데이터 크롤링 및 저장 완료. 총 논문 수: {len(crawled_papers_20)}")
    except Exception as e:
        logger.error(f"6월 20일 크롤링 중 오류 발생: {e}", exc_info=True)

    # 3. 데이터베이스에서 6월 20일 크롤링 결과 확인
    papers_20 = session.query(Paper).all()
    logger.info(f"데이터베이스에 저장된 6월 20일 논문 수: {len(papers_20)}")
    for p in papers_20:
        logger.debug(f"[DB 20일] ID: {p.paper_id}, 제목: {p.title[:30]}..., 발행일: {p.published_date.date()}, 크롤링일: {p.crawled_date.date() if p.crawled_date else 'N/A'}")

    # 4. 6월 21일 데이터 크롤링 (새로고침 시나리오)
    logger.info("\n--- 6월 21일 데이터 크롤링 시작 ---")
    start_date_21 = datetime(2024, 6, 21, 0, 0, 0)
    end_date_21 = datetime(2024, 6, 21, 23, 59, 59)

    try:
        logger.debug(f"[21일] multi_platform_crawl 호출 직전. 쿼리: research, 시작일: {start_date_21}, 종료일: {end_date_21}")
        crawled_papers_21 = list(multi_platform_crawl(query="research", platforms=['arxiv'], start_date=start_date_21, end_date=end_date_21, max_results=100))
        logger.debug(f"[21일] multi_platform_crawl 호출 직후. 크롤링된 논문 수: {len(crawled_papers_21)}")
        save_papers_to_db(crawled_papers_21)
        logger.info(f"6월 21일 데이터 크롤링 및 저장 완료. 총 논문 수: {len(crawled_papers_21)}")
    except Exception as e:
        logger.error(f"6월 21일 크롤링 중 오류 발생: {e}", exc_info=True)

    # 5. 데이터베이스에서 총 논문 수 확인
    final_papers = session.query(Paper).all()
    logger.info(f"최종 데이터베이스에 저장된 총 논문 수: {len(final_papers)}")
    for p in final_papers:
        logger.debug(f"[DB 최종] ID: {p.paper_id}, 제목: {p.title[:30]}..., 발행일: {p.published_date.date()}, 크롤링일: {p.crawled_date.date() if p.crawled_date else 'N/A'}")

    session.close()
    logger.info("독립 크롤링 테스트 스크립트 종료")

if __name__ == '__main__':
    run_test_crawl() 