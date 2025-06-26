import os
import sys
from datetime import datetime, timedelta
import logging

# 모든 로거의 레벨을 DEBUG로 설정
logging.basicConfig(level=logging.DEBUG)

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 현재 스크립트의 디렉토리를 sys.path에 추가하여 상대 경로 임포트 문제 해결
# if __name__ == '__main__': 일 때만 필요
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from crawler_src.models import Paper, Base # 이제 절대 경로로 임포트
from crawler_src.multi_platform_crawler import multi_platform_crawl, save_papers_to_db # 이제 절대 경로로 임포트
from crawler_src.config import Config # Config 클래스 임포트

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DATABASE_URL = "sqlite:///papers.db"

def init_db():
    logger.debug("init_db 함수 진입")
    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    logger.debug("데이터베이스 초기화 완료")
    logger.debug("init_db 함수 종료")

@app.route('/')
def index():
    logger.debug("index 함수 진입")
    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    papers = session.query(Paper).order_by(Paper.published_date.desc()).all()
    
    # 가장 최근에 크롤링된 날짜를 가져와서 템플릿으로 전달
    latest_crawled_paper = session.query(Paper).order_by(Paper.crawled_date.desc()).first()
    latest_crawled_date = latest_crawled_paper.crawled_date.isoformat() if latest_crawled_paper and latest_crawled_paper.crawled_date else None

    session.close()
    logger.debug("index 함수 종료")
    return render_template('index.html',
                           papers=papers,
                           latest_crawled_date=latest_crawled_date
                          )

@app.route('/crawl', methods=['POST'])
def crawl_data():
    logger.debug("crawl_data 함수 진입")

    request_data = request.json
    start_date_str = request_data.get('start_date')
    end_date_str = request_data.get('end_date')
    is_initial_crawl = request_data.get('is_initial_crawl', False) # 기본값은 False
    max_papers = request_data.get('max_papers', 0) # 기본값은 0 (제한 없음)

    logger.debug(f"Received crawl request: start_date={start_date_str}, end_date={end_date_str}, is_initial_crawl={is_initial_crawl}, max_papers={max_papers}")

    if not start_date_str or not end_date_str:
        logger.debug("시작 날짜 또는 종료 날짜가 제공되지 않았습니다.")
        return jsonify({"status": "error", "message": "시작 날짜와 종료 날짜를 모두 제공해야 합니다."})

    try:
        start_date_obj = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date_obj = datetime.strptime(end_date_str, '%Y-%m-%d').replace(hour=23, minute=59, second=59) # 종료일의 끝 시간으로 설정
        logger.debug(f"대상 날짜 범위: {start_date_obj.date()} ~ {end_date_obj.date()}")
    except ValueError:
        logger.debug("잘못된 날짜 형식입니다.")
        return jsonify({"status": "error", "message": "잘못된 날짜 형식입니다. YYYY-MM-DD 형식이어야 합니다."})

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    if is_initial_crawl:
        logger.debug(f"{start_date_str}부터 {end_date_str}까지의 데이터 크롤링 시작 (초기화)")
        # 기존 데이터 삭제 (초기화 요청 시)
        session.query(Paper).delete()
        session.commit()
        session.close() # 세션을 닫고 다시 열어 초기화된 DB를 반영
        session = Session() # 새 세션 시작

    else:
        logger.debug(f"{start_date_str}부터 {end_date_str}까지의 데이터 추가 크롤링 시작")

    try:
        logger.debug(f"multi_platform_crawl 함수 호출 직전 (날짜 범위: {start_date_obj.date()} ~ {end_date_obj.date()}, 최대 논문 수: {max_papers})")
        crawled_papers_generator = multi_platform_crawl(
            query="research",
            platforms=Config.SUPPORTED_CRAWLER_PLATFORMS, # 모든 플랫폼 사용
            start_date=start_date_obj,
            end_date=end_date_obj,
            max_results=max_papers if max_papers > 0 else Config.DEFAULT_CRAWLER_MAX_RESULTS # max_papers가 0보다 크면 그 값을 사용, 아니면 config 값 사용
        )
        logger.debug(f"multi_platform_crawl 함수 호출 직후 (날짜 범위: {start_date_obj.date()} ~ {end_date_obj.date()})")
        crawled_papers = list(crawled_papers_generator)
        logger.debug(f"크롤링된 논문 수 (날짜 범위: {start_date_obj.date()} ~ {end_date_obj.date()}): {len(crawled_papers)}")
        save_papers_to_db(crawled_papers)
        logger.debug(f"{start_date_str}부터 {end_date_str}까지의 데이터 크롤링 및 저장 완료")
        return jsonify({"status": "success", "message": f"{start_date_str}부터 {end_date_str}까지 데이터 크롤링 및 저장 완료. 총 {len(crawled_papers)}개의 논문이 추가되었습니다."})
    except Exception as e:
        session.rollback() # 오류 발생 시 롤백
        logger.error(f"크롤링 중 오류 발생 ({start_date_str} ~ {end_date_str}): {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"데이터 크롤링 중 오류 발생: {str(e)}"})

if __name__ == '__main__':
    logger.debug("애플리케이션 시작")
    init_db()
    app.run(debug=True)
    logger.debug("애플리케이션 종료") 