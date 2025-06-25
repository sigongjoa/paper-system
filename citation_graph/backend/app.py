import logging
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from sqlalchemy.orm import Session
from .models import Paper, Citation, Base
from .database import get_session_local, create_db_and_tables
from .crawling_manager import MultiPlatformCrawlingManager
# from .db_operations import save_papers_to_db # 추후 필요시 사용
# from .crawling_manager import crawl_paper_by_id # 추후 통합 크롤러로 교체

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

crawling_manager = MultiPlatformCrawlingManager() # 크롤링 매니저 인스턴스 생성

# Dependency to get database session
def get_db():
    logger.debug("get_db 함수 시작")
    db: Session = get_session_local()() # Correctly instantiate the session
    try:
        yield db
    finally:
        db.close()
        logger.debug("get_db 함수 종료")

@app.route('/')
def index():
    logger.debug("index 함수 시작 - index.html 렌더링")
    return render_template('index.html')

@app.route('/api/graph/<string:paper_id>', methods=['GET'])
def get_citation_graph(paper_id: str):
    logger.debug(f"get_citation_graph 엔드포인트 호출 시작 - paper_id: {paper_id}")
    depth = request.args.get('depth', default=1, type=int)
    logger.debug(f"요청된 깊이(depth): {depth}")

    db_gen = get_db()
    db = next(db_gen) # Get the session object
    try:
        nodes = []
        edges = []
        node_ids = set() # Track unique node IDs to avoid duplicates
        queue = [] # For BFS traversal (paper_id, current_depth)

        # 1. 중심 논문 조회
        central_paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
        
        # 논문이 데이터베이스에 없는 경우 크롤링 시도
        if not central_paper:
            logger.info(f"데이터베이스에 논문 {paper_id}이(가) 없어 arXiv에서 크롤링을 시도합니다.")
            # 기본적으로 arXiv에서 검색. 나중에 사용자로부터 플랫폼을 받을 수도 있음.
            crawled_paper_data = crawling_manager.crawl_and_save_paper_by_id(paper_id, "arxiv", db)
            
            if crawled_paper_data:
                # 새로 크롤링된 논문을 다시 조회하여 Paper 객체로 가져옴 (새로운 세션에서)
                central_paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
                if central_paper:
                    logger.info(f"논문 {paper_id}이(가) arXiv에서 성공적으로 크롤링되어 사용됩니다.")
                else:
                    # 이 경우는 발생해서는 안되지만, 만약을 대비
                    logger.error(f"크롤링 후 논문 {paper_id}을(를) 데이터베이스에서 찾을 수 없습니다.")
                    return jsonify({"error": "Failed to retrieve crawled paper from database"}), 500
            else:
                logger.warning(f"arXiv에서도 논문 ID {paper_id}을(를) 찾을 수 없습니다.")
                return jsonify({"error": "Paper not found in database or arXiv"}), 404

        # 중심 논드 노드 추가 및 큐에 추가
        nodes.append({"id": central_paper.paper_id, "label": central_paper.title, "group": "central", "year": central_paper.year})
        node_ids.add(central_paper.paper_id)
        queue.append((central_paper.paper_id, 0))
        logger.debug(f"초기 큐에 중심 논문 추가: {central_paper.title} (깊이 0)")

        # BFS 탐색
        while queue:
            current_paper_id, current_depth = queue.pop(0)
            # 현재 논문의 제목을 가져와 로그에 사용
            current_paper_in_loop = db.query(Paper).filter(Paper.paper_id == current_paper_id).first()
            current_paper_title_for_log = current_paper_in_loop.title if current_paper_in_loop else current_paper_id

            logger.debug(f"현재 논문: '{current_paper_title_for_log}' (깊이 {current_depth})")

            if current_depth >= depth:
                logger.debug(f"최대 깊이 {depth} 도달, 탐색 중단: '{current_paper_title_for_log}'")
                continue

            # 인용하는 논문들 (References) 조회
            citing_relations = db.query(Citation).filter(Citation.citing_paper_id == current_paper_id).all()
            for relation in citing_relations:
                cited_paper = db.query(Paper).filter(Paper.paper_id == relation.cited_paper_id).first()
                if cited_paper:
                    if cited_paper.paper_id not in node_ids:
                        nodes.append({"id": cited_paper.paper_id, "label": cited_paper.title, "group": "cited", "year": cited_paper.year})
                        node_ids.add(cited_paper.paper_id)
                        queue.append((cited_paper.paper_id, current_depth + 1))
                        logger.debug(f"새 노드 추가 및 큐에 추가 (인용): '{cited_paper.title}' (깊이 {current_depth + 1})")
                    
                    # 중복 엣지 방지 (Vis.js는 자동으로 중복 엣지를 처리하지만, 백엔드에서 방지하는 것이 좋음)
                    edge_exists = any(e['from'] == current_paper_id and e['to'] == cited_paper.paper_id for e in edges)
                    if not edge_exists:
                        edges.append({"from": current_paper_id, "to": cited_paper.paper_id, "arrows": "to", "label": "cites"})
                        logger.debug(f"엣지 추가 (인용): '{current_paper_title_for_log}' -> '{cited_paper.title}'")

            # 인용한 논문들 (Cited by) 조회
            cited_by_relations = db.query(Citation).filter(Citation.cited_paper_id == current_paper_id).all()
            for relation in cited_by_relations:
                citing_paper = db.query(Paper).filter(Paper.paper_id == relation.citing_paper_id).first()
                if citing_paper:
                    if citing_paper.paper_id not in node_ids:
                        nodes.append({"id": citing_paper.paper_id, "label": citing_paper.title, "group": "citing", "year": citing_paper.year})
                        node_ids.add(citing_paper.paper_id)
                        queue.append((citing_paper.paper_id, current_depth + 1))
                        logger.debug(f"새 노드 추가 및 큐에 추가 (피인용): '{citing_paper.title}' (깊이 {current_depth + 1})")

                    # 중복 엣지 방지
                    edge_exists = any(e['from'] == citing_paper.paper_id and e['to'] == current_paper_id for e in edges)
                    if not edge_exists:
                        edges.append({"from": citing_paper.paper_id, "to": current_paper_id, "arrows": "to", "label": "cited by"})
                        logger.debug(f"엣지 추가 (피인용): '{citing_paper.title}' -> '{current_paper_title_for_log}'")

        logger.info(f"그래프 데이터 생성 완료. 노드: {len(nodes)}개, 엣지: {len(edges)}개")
        return jsonify({"nodes": nodes, "edges": edges}), 200

    except Exception as e:
        logger.exception("get_citation_graph 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500
    finally:
        # Close the database session in the finally block
        # This is handled by the get_db generator's finally block
        pass

if __name__ == '__main__':
    logger.debug("Flask 앱 시작")
    create_db_and_tables() # 데이터베이스 및 테이블 생성
    app.run(debug=True, port=5001) # 포트 5001로 실행하여 다른 앱과 충돌 방지
    logger.debug("Flask 앱 종료") 