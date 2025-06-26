import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from crewai import Agent, Task, Crew, Process
from crewai_tools import TavilySearchResults
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from openai import OpenAI
from deepsearch.backend.core.models import Paper, Citation
import requests # Added import for making HTTP requests to ShortGPT
import json # json 파싱을 위해 추가

# Import the multi_platform_crawl function
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from cawler.multi_platform_crawler import multi_platform_crawl
from deepsearch.backend.db.connection import create_db_and_tables, SessionLocal

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

# OpenAI 클라이언트 초기화 (LM Studio와 호환)
client = OpenAI(
    base_url=os.getenv("OPENAI_API_BASE", "http://localhost:1234/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "not-needed")
)
LLM_MODEL = os.getenv("OPENAI_MODEL_NAME", "lmstudio-community/qwen2.5-7b-instruct") # LM Studio에서 로드된 모델 이름

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

def generate_paper_shorts(abstract: str) -> str:
    logger.debug(f"generate_paper_shorts 함수 시작 - abstract 길이: {len(abstract)}")
    try:
        if not abstract:
            logger.warning("초록이 비어 있어 쇼츠를 생성할 수 없습니다.")
            return "초록 없음."

        prompt = (
            f"다음 논문의 초록을 읽고, 3~5줄 분량의 핵심 내용을 담은 간결한 '쇼츠'(요약)를 작성해주세요. "
            f"주요 발견, 방법론, 결론을 포함하되, 비전문가도 이해하기 쉽게 작성해야 합니다.\n\n"
            f"초록:\n{abstract}\n\n쇼츠:"
        )

        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "당신은 논문 초록을 요약하여 간결한 '쇼츠'를 생성하는 전문가입니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )
        shorts = response.choices[0].message.content.strip()
        logger.debug(f"generate_paper_shorts 함수 종료 - 생성된 쇼츠 길이: {len(shorts)}")
        return shorts
    except Exception as e:
        logger.error(f"쇼츠 생성 중 오류 발생: {e}")
        return f"쇼츠 생성 오류: {e}"

def generate_shorts_for_shortgpt(abstract_shorts: str) -> dict:
    """
    LM Studio에서 생성된 논문 쇼츠 텍스트를 ShortGPT가 이해할 수 있는
    장면(scenes) 배열 형식으로 변환합니다.
    간단화를 위해 전체 쇼츠 텍스트를 단일 장면으로 처리하고
    관련 검색어는 일단 빈 리스트로 둡니다.
    """
    logger.debug(f"generate_shorts_for_shortgpt 함수 시작 - 쇼츠 길이: {len(abstract_shorts)}")
    # 여기서 abstract_shorts를 문장 단위로 나누어 여러 장면으로 만들 수도 있습니다.
    # 예시: sentences = abstract_shorts.split('. ')
    # scenes = [{"text": s.strip(), "searchTerms": []} for s in sentences if s.strip()]

    # 간단하게 전체 요약을 한 장면으로 구성
    scenes = [{"text": abstract_shorts, "searchTerms": ["scientific paper", "research", "abstract"]}]
    
    # ShortGPT 설정 (예: 음악, 패딩 등) - 필요시 추가 조정
    config = {
        "music": "chill", # ShortGPT가 지원하는 음악 태그
        "paddingBack": 1500 # 동영상 끝 부분 패딩 (밀리초)
    }
    
    logger.debug("generate_shorts_for_shortgpt 함수 종료 - ShortGPT 입력 형식 생성 완료")
    return {"scenes": scenes, "config": config}

@app.route('/generate_shorts', methods=['POST'])
def generate_shorts():
    logger.debug("generate_shorts 엔드포인트 호출 시작")
    try:
        data = request.get_json()
        paper_id = data.get('paper_id')
        query = data.get('query')
        limit = data.get('limit', 10) # Default to 10 papers

        db_gen = get_db()
        db = next(db_gen)

        papers_to_process = []
        if paper_id:
            paper = db.query(Paper).filter(Paper.paper_id == paper_id).first()
            if paper:
                papers_to_process.append(paper)
                logger.debug(f"단일 논문 ID로 쇼츠 생성 요청: {paper_id}")
            else:
                logger.warning(f"Paper ID를 찾을 수 없음: {paper_id}")
                return jsonify({"error": f"Paper with ID {paper_id} not found"}), 404
        elif query:
            # Implement search logic if needed, for now just fetch recent papers
            papers = db.query(Paper).filter(
                (Paper.title.contains(query)) |
                (Paper.abstract.contains(query))
            ).limit(limit).all()
            papers_to_process.extend(papers)
            logger.debug(f"쿼리 '{query}'로 논문 검색 및 쇼츠 생성 요청. {len(papers_to_process)}개 논문 발견.")
        else:
            # Fetch recent papers if no specific paper_id or query
            papers = db.query(Paper).order_by(Paper.published_date.desc()).limit(limit).all()
            papers_to_process.extend(papers)
            logger.debug(f"특정 요청 없이 최근 논문 {limit}개에 대해 쇼츠 생성 요청.")

        results = []
        if not papers_to_process:
            logger.info("쇼츠를 생성할 논문이 없습니다.")
            return jsonify({"message": "No papers found to generate shorts for."}), 200

        for paper in papers_to_process:
            shorts_text = generate_paper_shorts(paper.abstract)
            
            # ShortGPT 호출을 위한 데이터 준비
            shortgpt_payload = generate_shorts_for_shortgpt(shorts_text)
            
            video_status = "Not Generated"
            video_id = None
            try:
                # ShortGPT 서버 호출
                # ShortGPT는 기본적으로 31415 포트를 사용한다고 가정
                shortgpt_url = os.getenv("SHORTGPT_API_BASE", "http://localhost:31415/api/short-video")
                logger.debug(f"ShortGPT API 호출 시도: {shortgpt_url}")
                shortgpt_response = requests.post(shortgpt_url, json=shortgpt_payload, timeout=300) # 5분 타임아웃
                shortgpt_response.raise_for_status() # HTTP 오류 발생 시 예외 발생
                
                shortgpt_result = shortgpt_response.json()
                video_id = shortgpt_result.get("videoId")
                video_status = f"Generated - Video ID: {video_id}"
                logger.info(f"ShortGPT 동영상 생성 요청 성공. Video ID: {video_id}")

            except requests.exceptions.ConnectionError as e:
                logger.error(f"ShortGPT 서버 연결 오류: {e}. ShortGPT가 실행 중인지 확인하세요.")
                video_status = f"ShortGPT Connection Error: {e}"
            except requests.exceptions.Timeout as e:
                logger.error(f"ShortGPT 응답 타임아웃 오류: {e}. 동영상 생성 시간이 오래 걸릴 수 있습니다.")
                video_status = f"ShortGPT Timeout Error: {e}"
            except requests.exceptions.RequestException as e:
                logger.error(f"ShortGPT API 요청 중 오류 발생: {e}. 응답: {shortgpt_response.text if shortgpt_response else 'N/A'}")
                video_status = f"ShortGPT API Error: {e}"
            except Exception as e:
                logger.exception("ShortGPT 호출 중 예상치 못한 오류 발생")
                video_status = f"Unexpected ShortGPT Error: {e}"

            results.append({
                "paper_id": paper.paper_id,
                "title": paper.title,
                "abstract_shorts": shorts_text,
                "video_status": video_status,
                "video_id": video_id # 동영상 ID도 포함하여 나중에 상태 조회 가능하도록
            })
            logger.debug(f"논문 ID {paper.paper_id}에 대한 동영상 쇼츠 생성 처리 완료.")

        logger.info(f"{len(results)}개의 논문에 대한 쇼츠 생성 파이프라인 처리 완료.")
        return jsonify({"shorts_with_videos": results}), 200

    except Exception as e:
        logger.exception("generate_shorts 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500

def generate_video_script_and_scenes(abstract: str) -> dict:
    """
    LM Studio를 사용하여 논문 초록에서 동영상 쇼츠 대본과 장면 설명을 생성합니다.
    LM Studio가 JSON 포맷을 직접 출력하도록 프롬프트 엔지니어링을 시도합니다.
    """
    logger.debug(f"generate_video_script_and_scenes 함수 시작 - 초록 길이: {len(abstract)}")
    try:
        if not abstract:
            logger.warning("초록이 비어 있어 동영상 대본/장면 생성을 할 수 없습니다.")
            return {"script": "초록 없음.", "scenes": []}

        prompt = (
            f"다음 논문의 초록을 읽고, 이 논문의 내용을 기반으로 1분 이내의 "
            f"동영상 쇼츠 대본과 각 장면에 필요한 시각적 설명을 JSON 형식으로 생성해주세요. "
            f"각 장면은 5초 이내로 구성하며, 주요 내용은 대본(script) 필드에, "
            f"각 장면은 scenes 배열에 {{{\"text\": \"장면 대사\", \"image_search_term\": \"이미지 검색어\"}}} 형식으로 포함해주세요. "
            f"최대 10개 장면을 생성해주세요.\n\n"
            f"초록:\n{abstract}\n\nJSON 형식의 대본 및 장면:"
        )

        # LM Studio 호출 (OpenAI API 호환)
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": "당신은 논문 초록을 기반으로 동영상 쇼츠 대본과 장면 설명을 생성하는 전문가입니다. 응답은 엄격하게 JSON 형식이어야 합니다."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000, # 대본 및 장면 생성을 위해 충분한 토큰 할당
            response_format={"type": "json_object"} # JSON 형식 응답 요청
        )
        
        # LM Studio 응답 파싱
        try:
            generated_content = response.choices[0].message.content.strip()
            # generated_content가 JSON 문자열임을 가정하고 파싱
            parsed_json = json.loads(generated_content)
            logger.debug(f"generate_video_script_and_scenes 함수 종료 - JSON 파싱 완료")
            return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"LM Studio 응답 JSON 파싱 오류: {e} - 원본 응답: {generated_content[:500]}...")
            return {"script": "JSON 파싱 오류.", "scenes": []}

    except Exception as e:
        logger.error(f"동영상 대본/장면 생성 중 오류 발생: {e}")
        return {"script": f"대본 생성 오류: {e}", "scenes": []}

def text_to_speech_conceptual(text: str, output_path: str) -> str:
    """
    개념적인 TTS 함수. 실제로는 외부 TTS 라이브러리/API (예: gTTS, ElevenLabs)를 사용해야 합니다.
    여기서는 플레이스홀더 오디오 파일 경로를 반환합니다.
    """
    logger.debug(f"text_to_speech_conceptual 함수 시작 - 텍스트 길이: {len(text)}, 출력 경로: {output_path}")
    # 실제 TTS 로직이 여기에 들어갑니다.
    # 예시:
    # from gtts import gTTS
    # tts = gTTS(text=text, lang='ko')
    # tts.save(output_path)
    # logger.debug(f"TTS 생성 완료: {output_path}")

    # 실제 오디오 파일을 생성했다고 가정하고 경로 반환
    logger.debug(f"text_to_speech_conceptual 함수 종료 - 가상 오디오 파일 경로: {output_path}")
    return output_path

def assemble_video_conceptual(scenes_with_audio_and_images: list, output_video_path: str) -> str:
    """
    개념적인 동영상 조합 함수. 실제로는 MoviePy와 같은 비디오 편집 라이브러리를 사용해야 합니다.
    여기서는 플레이스홀더 비디오 파일 경로를 반환합니다.
    scenes_with_audio_and_images는 각 장면에 대한 텍스트, 오디오 파일 경로, 이미지/영상 검색어 등을 포함할 수 있습니다.
    """
    logger.debug(f"assemble_video_conceptual 함수 시작 - 장면 수: {len(scenes_with_audio_and_images)}, 출력 경로: {output_video_path}")
    # 실제 동영상 편집 및 렌더링 로직이 여기에 들어갑니다.
    # 예시:
    # from moviepy.editor import VideoFileClip, AudioFileClip, CompositeVideoClip, TextClip, concatenate_videoclips
    # clips = []
    # for scene in scenes_with_audio_and_images:
    #     # 이미지/영상 소싱 (ShortGPT Asset Sourcing과 유사)
    #     # audio_clip = AudioFileClip(scene["audio_path"])
    #     # image_clip = ImageClip(scene["image_path"]).set_duration(audio_clip.duration)
    #     # final_clip = image_clip.set_audio(audio_clip)
    #     # clips.append(final_clip)
    # # final_video = concatenate_videoclips(clips)
    # # final_video.write_videofile(output_video_path, fps=24)
    # logger.debug(f"동영상 조합 완료: {output_video_path}")

    # 실제 비디오 파일을 생성했다고 가정하고 경로 반환
    logger.debug(f"assemble_video_conceptual 함수 종료 - 가상 동영상 파일 경로: {output_video_path}")
    return output_video_path

@app.route('/generate_full_video_shorts', methods=['POST'])
def generate_full_video_shorts():
    logger.debug("generate_full_video_shorts 엔드포인트 호출 시작")
    try:
        data = request.get_json()
        paper_id = data.get('paper_id')
        query = data.get('query')
        limit = data.get('limit', 1) # Full video는 일단 1개만 생성하도록 제한

        db_gen = get_db()
        db = next(db_gen)

        paper_to_process = None
        if paper_id:
            paper_to_process = db.query(Paper).filter(Paper.paper_id == paper_id).first()
            if not paper_to_process:
                logger.warning(f"Paper ID를 찾을 수 없음: {paper_id}")
                return jsonify({"error": f"Paper with ID {paper_id} not found"}), 404
            logger.debug(f"단일 논문 ID로 동영상 쇼츠 생성 요청: {paper_id}")
        elif query:
            paper_to_process = db.query(Paper).filter(
                (Paper.title.contains(query)) |
                (Paper.abstract.contains(query))
            ).first() # 첫 번째 검색 결과만 사용
            if not paper_to_process:
                logger.warning(f"쿼리 '{query}'로 논문을 찾을 수 없습니다.")
                return jsonify({"message": f"No papers found for query '{query}'."}), 200
            logger.debug(f"쿼리 '{query}'로 논문 검색 및 동영상 쇼츠 생성 요청. 논문: {paper_to_process.paper_id}")
        else:
            paper_to_process = db.query(Paper).order_by(Paper.published_date.desc()).first() # 최신 논문 1개
            if not paper_to_process:
                logger.info("동영상 쇼츠를 생성할 논문이 없습니다.")
                return jsonify({"message": "No papers found to generate full video shorts for."}), 200
            logger.debug(f"특정 요청 없이 최근 논문 1개에 대해 동영상 쇼츠 생성 요청. 논문: {paper_to_process.paper_id}")

        # 1. LM Studio를 통해 대본 및 장면 설명 생성
        script_and_scenes = generate_video_script_and_scenes(paper_to_process.abstract)
        script_text = script_and_scenes.get("script", "대본 생성 실패")
        scenes_data = script_and_scenes.get("scenes", [])
        
        if not scenes_data:
            logger.error(f"장면 데이터 생성 실패: {script_text}")
            return jsonify({"error": "Failed to generate video script and scenes."}), 500

        processed_scenes = []
        video_output_base_dir = "generated_videos"
        audio_output_base_dir = "generated_audio"
        os.makedirs(video_output_base_dir, exist_ok=True) # 폴더 생성
        os.makedirs(audio_output_base_dir, exist_ok=True) # 폴더 생성
        video_output_path = os.path.join(video_output_base_dir, f"shorts_{paper_to_process.paper_id}.mp4")

        # 2. 각 장면에 대해 TTS 및 이미지/영상 소싱 (개념적)
        for i, scene in enumerate(scenes_data):
            scene_text = scene.get("text", "")
            image_search_term = scene.get("image_search_term", "")
            
            audio_path = os.path.join(audio_output_base_dir, f"scene_{paper_to_process.paper_id}_{i}.mp3")
            
            # 개념적인 TTS 호출
            try:
                actual_audio_path = text_to_speech_conceptual(scene_text, audio_path)
            except Exception as e:
                logger.error(f"장면 {i} TTS 오류: {e}")
                actual_audio_path = "TTS_ERROR"

            # 개념적인 이미지/영상 소싱 (ShortGPT의 Pexels/Bing Image 기능과 유사)
            # 여기서는 실제 이미지를 다운로드하지 않고 경로만 가정
            image_path_conceptual = f"generated_images/scene_{image_search_term.replace(' ', '_')}_{i}.jpg"
            # 실제 구현에서는 image_search_term을 사용하여 Pexels/Bing Image API를 호출하고
            # 이미지를 다운로드하거나, AI 이미지 생성 API를 호출해야 합니다.

            processed_scenes.append({
                "scene_number": i,
                "text": scene_text,
                "image_search_term": image_search_term,
                "audio_path": actual_audio_path,
                "image_path_conceptual": image_path_conceptual # 실제 이미지가 아님
            })
        
        # 3. 개념적인 동영상 조합
        final_video_path = assemble_video_conceptual(processed_scenes, video_output_path)

        logger.info(f"동영상 쇼츠 생성 파이프라인 처리 완료. 최종 동영상: {final_video_path}")
        return jsonify({
            "paper_id": paper_to_process.paper_id,
            "title": paper_to_process.title,
            "generated_script": script_text,
            "processed_scenes": processed_scenes,
            "final_video_path": final_video_path,
            "status": "Conceptual Video Pipeline Completed (requires external tools for actual files)"
        }), 200

    except Exception as e:
        logger.exception("generate_full_video_shorts 처리 중 오류 발생")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    logger.debug("Flask 앱 시작")
    create_db_and_tables()
    app.run(debug=True, host='0.0.0.0', port=5000)
    logger.debug("Flask 앱 종료") 