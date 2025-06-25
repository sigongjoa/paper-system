import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchResults
import logging
from datetime import datetime
from sqlalchemy.orm import Session

# Import the multi_platform_crawl function
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from cawler.multi_platform_crawler import multi_platform_crawl
from deepsearch.backend.db.connection import create_db_and_tables, SessionLocal
from deepsearch.backend.core.models import Paper, Citation

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# .env 파일에서 환경 변수를 로드합니다.
load_dotenv()
logger.debug("환경 변수 로드 완료")

# Tavily API 키 확인
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
if not TAVILY_API_KEY or TAVILY_API_KEY == "tvly-xxxxxxxxxxxxxxxx":
    logger.error("TAVILY_API_KEY가 설정되지 않았거나 기본값입니다. .env 파일을 확인해주세요.")
    # 실제 운영 환경에서는 앱 시작을 중단하거나 적절한 오류 처리를 해야 합니다.

# LM Studio 설정 (환경 변수에서 자동으로 로드되므로 명시적 설정은 주석 처리)
# OPENAI_API_BASE = os.getenv("OPENAI_API_BASE")
# OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")
# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Dependency
def get_db():
    logger.debug("get_db 함수 시작")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        logger.debug("get_db 함수 종료")

# 1. 검색 도구 초기화
# Tavily API를 사용하는 검색 도구를 생성합니다.
search_tool = TavilySearchResults()
logger.debug("검색 도구 초기화 완료")

# 2. 딥 리서치 에이전트 정의
# 리서처(Researcher) 에이전트를 정의합니다.
researcher = Agent(
  role='시니어 리서치 분석가',
  goal='주어진 주제에 대한 포괄적인 최신 정보를 분석하고 보고서를 작성합니다.',
  backstory="""당신은 기술, 특히 AI와 반도체 분야의 동향을 분석하는 데 저명한 리서치 분석가입니다.
  복잡한 주제를 분해하고, 신뢰할 수 있는 출처에서 핵심 정보를 수집하여 명확한 인사이트를 제공하는 능력이 탁월합니다.""",
  verbose=True, # 에이전트의 생각 과정을 출력합니다.
  allow_delegation=False, # 다른 에이전트에게 위임하지 않습니다.
  tools=[search_tool] # 이 에이전트는 검색 도구를 사용할 수 있습니다.
  # llm 속성을 명시적으로 설정하지 않으면, CrewAI는 환경 변수(OPENAI_API_BASE 등)를 자동으로 사용합니다.
)
logger.debug("리서처 에이전트 정의 완료")

@app.route('/deep_research', methods=['POST'])
def deep_research():
    logger.debug("deep_research 엔드포인트 호출 시작")
    try:
        data = request.get_json()
        topic = data.get('topic')
        logger.debug(f"요청 주제: {topic}")

        if not topic:
            logger.debug("주제 없음 오류 발생")
            return jsonify({"error": "No topic provided"}), 400

        # 3. 리서치 태스크 정의
        # 에이전트가 수행할 작업을 정의합니다.
        research_task = Task(
          description=f"""'{topic}'에 대해 심층적으로 조사하고,
          보고서는 개요, 주요 내용, 비교 분석(필요시), 그리고 미래 전망 순으로 구성해주세요.""",
          expected_output="마크다운 형식의 상세한 리서치 보고서",
          agent=researcher
        )
        logger.debug("리서치 태스크 정의 완료")

        # 4. 크루(Crew) 구성 및 실행
        # 에이전트와 태스크를 묶어 크루를 만들고 작업을 시작합니다.
        crew = Crew(
          agents=[researcher],
          tasks=[research_task],
          process=Process.sequential # 작업을 순차적으로 실행합니다.
        )
        logger.debug("크루 구성 완료. 작업 시작 예정.")

        # 작업 시작!
        result = crew.kickoff()
        logger.debug("크루 작업 완료")
        logger.debug(f"최종 리서치 결과: {result[:200]}...") # 결과의 일부만 로깅

        return jsonify({"result": result})

    except Exception as e:
        logger.exception("deep_research 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500

@app.route('/crawl_papers', methods=['POST'])
def crawl_papers():
    logger.debug("crawl_papers 엔드포인트 호출 시작")
    try:
        data = request.get_json()
        query = data.get('query', None)
        platforms = data.get('platforms', None) # List of platforms, e.g., ["arxiv", "biorxiv"]
        max_results = data.get('max_results', None)
        start_date_str = data.get('start_date', None) # YYYY-MM-DD
        end_date_str = data.get('end_date', None)   # YYYY-MM-DD

        start_date = datetime.strptime(start_date_str, '%Y-%m-%d') if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d') if end_date_str else None

        logger.debug(f"크롤링 요청 - 쿼리: {query}, 플랫폼: {platforms}, 최대 결과: {max_results}, 시작일: {start_date_str}, 종료일: {end_date_str}")

        crawled_papers = multi_platform_crawl(
            query=query,
            platforms=platforms,
            max_results=max_results,
            start_date=start_date,
            end_date=end_date
        )

        logger.debug(f"크롤링 완료: {len(crawled_papers)}개의 논문 발견.")
        return jsonify({"papers": crawled_papers}), 200

    except Exception as e:
        logger.exception("crawl_papers 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500

@app.route('/api/graph/<string:paper_id>', methods=['GET'])
def get_citation_graph(paper_id: str):
    logger.debug(f"get_citation_graph 엔드포인트 호출 시작 - paper_id: {paper_id}")
    db_gen = get_db()
    db = next(db_gen) # Get the session object
    try:
        nodes = []
        edges = []
        node_ids = set() # Track unique node IDs to avoid duplicates

        # 1. 중심 논문 조회
        central_paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
        if not central_paper:
            logger.warning(f"Paper not found: {paper_id}")
            return jsonify({"error": "Paper not found"}), 404

        # 중심 논문 노드 추가
        nodes.append({"id": central_paper.paper_id, "label": central_paper.title, "group": "central", "year": central_paper.year})
        node_ids.add(central_paper.paper_id)
        logger.debug(f"중심 논문 노드 추가: {central_paper.paper_id}")

        # 2. 중심 논문이 인용하는 논문들 (References) 조회
        # Paper 모델의 references_ids 필드 사용 (초기에는 빈 리스트이므로 Citation 테이블에서 조회)
        citing_relations = db.query(Citation).filter(Citation.citing_paper_id == paper_id).all()
        logger.debug(f"인용 관계 조회 완료: {len(citing_relations)}개")
        
        for relation in citing_relations:
            cited_paper = db.query(Paper).filter(Paper.paper_id == relation.cited_paper_id).first()
            if cited_paper:
                if cited_paper.paper_id not in node_ids:
                    nodes.append({"id": cited_paper.paper_id, "label": cited_paper.title, "group": "cited", "year": cited_paper.year})
                    node_ids.add(cited_paper.paper_id)
                    logger.debug(f"인용된 논문 노드 추가: {cited_paper.paper_id}")
                edges.append({"from": central_paper.paper_id, "to": cited_paper.paper_id, "arrows": "to", "label": "cites"})
                logger.debug(f"인용 엣지 추가: {central_paper.paper_id} -> {cited_paper.paper_id}")

        # 3. 중심 논문을 인용한 논문들 (Cited by) 조회
        # Paper 모델의 cited_by_ids 필드 사용 (초기에는 빈 리스트이므로 Citation 테이블에서 조회)
        cited_by_relations = db.query(Citation).filter(Citation.cited_paper_id == paper_id).all()
        logger.debug(f"피인용 관계 조회 완료: {len(cited_by_relations)}개")

        for relation in cited_by_relations:
            citing_paper = db.query(Paper).filter(Paper.paper_id == relation.citing_paper_id).first()
            if citing_paper:
                if citing_paper.paper_id not in node_ids:
                    nodes.append({"id": citing_paper.paper_id, "label": citing_paper.title, "group": "citing", "year": citing_paper.year})
                    node_ids.add(citing_paper.paper_id)
                    logger.debug(f"인용한 논문 노드 추가: {citing_paper.paper_id}")
                # 여기서는 cited_by 관계를 나타내므로, 화살표 방향을 반대로 설정할 수 있음
                # 또는 label을 'cited by'로 명확히 표시
                edges.append({"from": citing_paper.paper_id, "to": central_paper.paper_id, "arrows": "to", "label": "cited by"})
                logger.debug(f"피인용 엣지 추가: {citing_paper.paper_id} -> {central_paper.paper_id}")

        logger.info(f"그래프 데이터 생성 완료. 노드: {len(nodes)}개, 엣지: {len(edges)}개")
        return jsonify({"nodes": nodes, "edges": edges}), 200

    except Exception as e:
        logger.exception("get_citation_graph 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.debug("Flask 앱 시작")
    create_db_and_tables()
    app.run(debug=True, port=5000)
    logger.debug("Flask 앱 종료") 