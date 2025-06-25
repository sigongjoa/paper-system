import logging
import os
import sys
from datetime import datetime, timedelta

# `paper_system` 디렉토리를 sys.path에 직접 추가하여 deepsearch 패키지를 찾을 수 있도록 합니다.
sys.path.insert(0, "D:\\paper_system")

# multi_platform_crawler에서 get_crawler 함수를 임포트합니다.
from cawler.multi_platform_crawler import get_crawler

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_crawler_class(platform_name, query, max_results=5, start_date=None, end_date=None):
    logger.info(f"--- {platform_name} 크롤러 테스트 시작 ---")
    try:
        crawler = get_crawler(platform_name) # get_crawler 함수를 사용하여 크롤러 인스턴스 생성
        papers = list(crawler.crawl_papers(query=query, limit=max_results, start_date=start_date, end_date=end_date))
        if papers:
            logger.info(f"{platform_name} 크롤러 성공: {len(papers)}개의 논문 발견.")
            for i, paper in enumerate(papers[:min(len(papers), 2)]): # 처음 2개 논문만 자세히 출력
                logger.info(f"  [{i+1}] 제목: {paper.title[:70]}...") # .get() 대신 직접 속성 접근
                logger.info(f"      플랫폼: {paper.platform}, 발행일: {paper.published_date}") # .get() 대신 직접 속성 접근
        else:
            logger.warning(f"{platform_name} 크롤러 경고: 논문을 찾지 못했습니다.")
    except Exception as e:
        logger.error(f"{platform_name} 크롤러 오류: {e}", exc_info=True)
    logger.info(f"--- {platform_name} 크롤러 테스트 종료 ---\n")

if __name__ == "__main__":
    test_query_general = "machine learning"
    test_query_bio = "CRISPR"
    test_query_cs = "quantum computing"
    test_query_medicine = "cancer immunotherapy"

    # 테스트 날짜 설정 (최근 1주일)
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    # 크롤러 테스트 (플랫폼 이름을 문자열로 전달)
    test_crawler_class("arxiv", test_query_cs, max_results=3, start_date=start_date, end_date=end_date)
    test_crawler_class("biorxiv", test_query_bio, max_results=3, start_date=start_date, end_date=end_date)
    test_crawler_class("pmc", test_query_medicine, max_results=3, start_date=start_date, end_date=end_date)
    test_crawler_class("plos", test_query_general, max_results=3, start_date=start_date, end_date=end_date)
    test_crawler_class("doaj", test_query_general, max_results=3, start_date=start_date, end_date=end_date)
    test_crawler_class("arxiv_rss", "cs.AI", max_results=3, start_date=start_date, end_date=end_date)

    logger.info("모든 크롤러 테스트 완료.") 