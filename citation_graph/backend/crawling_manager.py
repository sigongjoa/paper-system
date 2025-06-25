import logging
import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Generator

from .models import Paper, Citation
from .db_operations import save_papers_to_db # 논문 저장 함수 임포트
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# arXiv API 기본 설정
ARXIV_BASE_URL = "http://export.arxiv.org/api/query"
ARXIV_DEFAULT_LIMIT = 20
ARXIV_DELAY = 3.0 # 초당 요청 제한 방지를 위한 딜레이

# Semantic Scholar API 설정
SEMANTIC_SCHOLAR_BASE_URL = "https://api.semanticscholar.org/graph/v1"
SEMANTIC_SCHOLAR_DELAY = 40.0 # Rate limit: 1000 requests/second for unauthenticated, 1 RPS for authenticated. Let's start with a small delay.

# --- ArxivCrawler Class ---
class ArxivCrawler:
    def __init__(self, delay: Optional[float] = None):
        logger.debug("ArxivCrawler __init__ 함수 시작")
        self.base_url = ARXIV_BASE_URL
        self.delay = delay if delay is not None else ARXIV_DELAY
        self.last_request_time = 0
        logger.debug(f"ArxivCrawler initialized with {self.delay}s delay")
        logger.debug("ArxivCrawler __init__ 함수 종료")
    
    def _wait_for_rate_limit(self):
        logger.debug("_wait_for_rate_limit 함수 시작")
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            logger.debug(f"Rate limiting - sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        logger.debug("_wait_for_rate_limit 함수 종료")
    
    def _make_request(self, query: str, start: int = 0, max_results: int = ARXIV_DEFAULT_LIMIT) -> str:
        logger.debug(f"_make_request 함수 시작 - query: {query}, start: {start}, max_results: {max_results}")
        self._wait_for_rate_limit()
        
        params = {
            'search_query': query,
            'start': start,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        # full_url = f"{self.base_url}?" + "&".join([f"{k}={v}" for k, v in params.items()]) # 기존 코드, params를 직접 전달
        logger.debug(f"Requesting arXiv API - query: {query}, start={start}, max={max_results}")
        
        response = requests.get(self.base_url, params=params)
        self.last_request_time = time.time()
        
        logger.debug(f"API response status: {response.status_code}, length={len(response.text)}")
        logger.debug("_make_request 함수 종료")
        return response.text
    
    def _parse_entry(self, entry) -> Optional[dict]: # Paper 객체 대신 dict 반환
        logger.debug("_parse_entry 함수 시작")
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        try:
            arxiv_id_full = entry.find('atom:id', ns).text
            arxiv_id_with_version = arxiv_id_full.split('/')[-1]
            # 버전 정보(vX) 제거: 예를 들어, '1706.03762v7' -> '1706.03762'
            arxiv_id = arxiv_id_with_version.split('v')[0] if 'v' in arxiv_id_with_version else arxiv_id_with_version
            title = entry.find('atom:title', ns).text.strip()
            abstract = entry.find('atom:summary', ns).text.strip()
            
            authors = [author.find('atom:name', ns).text for author in entry.findall('atom:author', ns)]
            categories = [category.get('term') for category in entry.findall('atom:category', ns)]
            
            pdf_link = None
            for link in entry.findall('atom:link', ns):
                if link.get('type') == 'application/pdf':
                    pdf_link = link.get('href')
                    break
            
            published_str = entry.find('atom:published', ns).text
            updated_str = entry.find('atom:updated', ns).text
            
            published_date = datetime.fromisoformat(published_str.replace('Z', '+00:00'))
            updated_date = datetime.fromisoformat(updated_str.replace('Z', '+00:00'))
            
            year = published_date.year

            # arXiv 네임스페이스 정의 및 DOI 추출
            arxiv_ns = {'arxiv': 'http://arxiv.org/schemas/atom'}
            doi_element = entry.find('arxiv:doi', arxiv_ns)
            doi = doi_element.text if doi_element is not None else None
            
            paper_data = {
                "paper_id": arxiv_id,
                "external_id": None, # arXiv ID 자체가 external_id 역할을 함
                "platform": 'arxiv',
                "title": title,
                "abstract": abstract,
                "authors": authors,
                "categories": categories,
                "pdf_url": pdf_link,
                "published_date": published_date,
                "updated_date": updated_date,
                "year": year,
                "references_ids": [], # Semantic Scholar에서 가져올 예정
                "cited_by_ids": [], # Semantic Scholar에서 가져올 예정
                "embedding": None, # 현재는 임베딩 생성 안함
                "doi": doi # DOI 필드 추가
            }
            logger.debug(f"_parse_entry 함수 종료 - paper_id: {paper_data['paper_id']}")
            return paper_data
        except Exception as e:
            logger.error(f"arXiv 엔트리 파싱 중 오류 발생: {e}", exc_info=True)
            return None
    
    def crawl_papers(self, query: str, limit: int = ARXIV_DEFAULT_LIMIT) -> Generator[dict, None, None]:
        logger.debug(f"crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        
        start_index = 0
        papers_yielded = 0
        
        while papers_yielded < limit:
            api_batch_size = min(ARXIV_DEFAULT_LIMIT, limit - papers_yielded)
            xml_response = self._make_request(query, start_index, api_batch_size)
            
            root = ET.fromstring(xml_response)
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'}
            
            entries = root.findall('atom:entry', ns)
            if not entries:
                logger.debug("No more entries found")
                break
            
            for entry in entries:
                if papers_yielded >= limit:
                    logger.debug(f"Reached limit ({limit}) papers")
                    break
                    
                paper_data = self._parse_entry(entry)
                if paper_data:
                    papers_yielded += 1
                    logger.debug(f"Paper {papers_yielded}/{limit}: {paper_data['paper_id']} - 제목:{paper_data['title'][:30]}...")
                    yield paper_data
            
            if papers_yielded >= limit:
                logger.debug(f"Found {papers_yielded} papers - Stop crawling")
                break
            
            start_index += api_batch_size # start_index는 요청한 max_results만큼 증가
            
            # OpenSearch totalResults를 사용하여 전체 결과 수와 현재 진행 상황 비교
            # arXiv API의 경우, totalResults와 startIndex, itemsPerPage를 사용하여 페이징을 관리.
            # 하지만 간단하게 limit까지만 가져오도록 구현
            total_results_element = root.find('opensearch:totalResults', ns)
            if total_results_element is not None:
                total_results = int(total_results_element.text)
                if start_index >= total_results:
                    logger.debug(f"Stopping at start_index={start_index} (no more results based on totalResults)")
                    break

        logger.debug(f"Crawling completed. Yielded: {papers_yielded}")
        logger.debug("crawl_papers 함수 종료")

class SemanticScholarCrawler:
    def __init__(self, delay: Optional[float] = None):
        logger.debug("SemanticScholarCrawler __init__ 함수 시작")
        self.base_url = SEMANTIC_SCHOLAR_BASE_URL
        self.delay = delay if delay is not None else SEMANTIC_SCHOLAR_DELAY
        self.last_request_time = 0
        logger.debug(f"SemanticScholarCrawler initialized with {self.delay}s delay")
        logger.debug("SemanticScholarCrawler __init__ 함수 종료")

    def _wait_for_rate_limit(self):
        logger.debug("SemanticScholarCrawler _wait_for_rate_limit 함수 시작")
        elapsed = time.time() - self.last_request_time
        if elapsed < self.delay:
            sleep_time = self.delay - elapsed
            logger.debug(f"SemanticScholarCrawler Rate limiting - sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        logger.debug("SemanticScholarCrawler _wait_for_rate_limit 함수 종료")

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        logger.debug(f"SemanticScholarCrawler _make_request 함수 시작 - endpoint: {endpoint}, params: {params}")
        self._wait_for_rate_limit()
        
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"Requesting Semantic Scholar API - URL: {url}, Params: {params}")
        
        try:
            response = requests.get(url, params=params)
            self.last_request_time = time.time()
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
            logger.debug(f"Semantic Scholar API response status: {response.status_code}, length={len(response.text)}")
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Semantic Scholar API 요청 중 오류 발생: {e}", exc_info=True)
            if response is not None:
                logger.error(f"Semantic Scholar API 응답 본문: {response.text}")
            return None
        finally:
            logger.debug("SemanticScholarCrawler _make_request 함수 종료")

    def get_semantic_scholar_paper_id(self, arxiv_id: str, title: str, doi: Optional[str] = None) -> Optional[str]:
        logger.debug(f"get_semantic_scholar_paper_id 함수 시작 - arXiv ID: {arxiv_id}, 제목: {title}, DOI: {doi}")

        # 1. DOI로 직접 조회 시도
        if doi:
            try:
                direct_lookup_data = self._make_request(f"paper/{doi}", params={"fields": "paperId"})
                if direct_lookup_data and "paperId" in direct_lookup_data:
                    s2_paper_id = direct_lookup_data["paperId"]
                    logger.info(f"Semantic Scholar에서 DOI {doi}로 Paper ID {s2_paper_id}를 직접 찾았습니다.")
                    return s2_paper_id
            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 404:
                    logger.warning(f"Semantic Scholar에서 DOI {doi}를 직접 찾지 못했습니다. arXiv ID로 검색을 시도합니다.")
                else:
                    logger.error(f"Semantic Scholar API DOI 직접 조회 중 오류 발생: {e}", exc_info=True)
            except Exception as e:
                logger.error(f"Semantic Scholar API DOI 직접 조회 중 예상치 못한 오류 발생: {e}", exc_info=True)

        # 2. arXiv ID로 직접 조회 시도 (기존 로직 유지)
        try:
            direct_lookup_data = self._make_request(f"paper/{arxiv_id}", params={"fields": "paperId"})
            if direct_lookup_data and "paperId" in direct_lookup_data:
                s2_paper_id = direct_lookup_data["paperId"]
                logger.info(f"Semantic Scholar에서 arXiv ID {arxiv_id}로 Paper ID {s2_paper_id}를 직접 찾았습니다.")
                return s2_paper_id
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Semantic Scholar에서 arXiv ID {arxiv_id}를 직접 찾지 못했습니다. 제목으로 검색을 시도합니다.")
            else:
                logger.error(f"Semantic Scholar API arXiv ID 직접 조회 중 오류 발생: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Semantic Scholar API arXiv ID 직접 조회 중 예상치 못한 오류 발생: {e}", exc_info=True)

        # 3. 제목으로 검색 시도 (기존 로직 유지)
        search_query = f'"{title}"' # 정확한 구문 검색을 위해 따옴표 추가
        search_params = {
            "query": search_query,
            "fields": "paperId,title",
            "limit": 5 # 상위 5개 결과만 확인
        }
        logger.debug(f"Semantic Scholar 제목 검색 시도 - 쿼리: {search_query}")
        search_results = self._make_request("paper/search/bulk", search_params)

        if search_results and "data" in search_results:
            for result in search_results["data"]:
                # 제목 일치율이 높은 논문을 선택
                if result and "paperId" in result and "title" in result and title.lower() == result["title"].lower():
                    s2_paper_id = result["paperId"]
                    logger.info("Semantic Scholar에서 제목 %s으로 Paper ID %s를 찾았습니다. 검색된 제목: %s" % (repr(title), s2_paper_id, repr(result["title"])))
                    return s2_paper_id
            logger.warning(f"Semantic Scholar에서 제목 '{title}'으로 적절한 Paper ID를 찾지 못했습니다.")
        else:
            logger.warning(f"Semantic Scholar에서 제목 '{title}'으로 검색 결과가 없거나 오류가 발생했습니다.")
        
        logger.debug("get_semantic_scholar_paper_id 함수 종료")
        return None

    def get_paper_citations_and_references(self, s2_paper_id: str) -> dict:
        logger.debug(f"SemanticScholarCrawler get_paper_citations_and_references 함수 시작 - S2 Paper ID: {s2_paper_id}")
        # fields: paperId, title for references and citations
        # To get the full citation data for references/citations, we need to query them separately.
        # Here we are just getting their IDs.
        params = {
            "fields": "references.paperId,citations.paperId"
        }
        data = self._make_request(f"paper/{s2_paper_id}", params)
        
        references_ids = []
        cited_by_ids = []
        
        if data:
            if "references" in data and data["references"]:
                references_ids = [ref["paperId"] for ref in data["references"] if ref and "paperId" in ref]
                logger.debug(f"SemanticScholarCrawler 찾은 인용 (references): {len(references_ids)}개")
            if "citations" in data and data["citations"]:
                cited_by_ids = [cit["paperId"] for cit in data["citations"] if cit and "paperId" in cit]
                logger.debug(f"SemanticScholarCrawler 찾은 피인용 (citations): {len(cited_by_ids)}개")

        logger.debug(f"SemanticScholarCrawler get_paper_citations_and_references 함수 종료 - S2 Paper ID: {s2_paper_id}")
        return {
            "references_ids": references_ids,
            "cited_by_ids": cited_by_ids
        }

    def get_paper_title(self, paper_id: str) -> Optional[str]:
        logger.debug(f"SemanticScholarCrawler get_paper_title 함수 시작 - paper_id: {paper_id}")
        params = {"fields": "title"}
        data = self._make_request(f"paper/{paper_id}", params)
        if data and "title" in data:
            logger.debug(f"SemanticScholarCrawler get_paper_title 함수 종료 - title: {data['title']}")
            return data["title"]
        logger.debug(f"SemanticScholarCrawler get_paper_title 함수 종료 - title not found for {paper_id}")
        return None

class MultiPlatformCrawlingManager:
    def __init__(self):
        logger.debug("MultiPlatformCrawlingManager __init__ 함수 시작")
        self.crawlers = {
            "arxiv": ArxivCrawler(),
            "semantic_scholar": SemanticScholarCrawler(), # Add SemanticScholarCrawler
        }
        logger.debug("MultiPlatformCrawlingManager __init__ 함수 종료")

    def crawl_and_save_paper_by_id(self, paper_id: str, platform: str, db: Session) -> Optional[dict]:
        logger.debug(f"crawl_and_save_paper_by_id 함수 시작 - paper_id: {paper_id}, platform: {platform}")
        
        arxiv_paper_data = None
        
        # 1. arXiv에서 논문 기본 정보 크롤링
        if "arxiv" in self.crawlers:
            arxiv_crawler = self.crawlers["arxiv"]
            query = f"id:{paper_id}"
            crawled_papers_generator = arxiv_crawler.crawl_papers(query, limit=1)
            paper_data_list = list(crawled_papers_generator)
            
            if paper_data_list:
                arxiv_paper_data = paper_data_list[0]
                logger.info(f"arXiv에서 논문 {paper_id}의 기본 정보 크롤링 성공.")
            else:
                logger.warning(f"arXiv에서 논문 ID {paper_id}을(를) 찾을 수 없습니다.")
        else:
            logger.warning("arXiv 크롤러가 MultiPlatformCrawlingManager에 없습니다.")

        if not arxiv_paper_data:
            logger.error(f"arXiv에서 논문 {paper_id}을(를) 찾지 못했습니다. Semantic Scholar로 대체 시도.")
            return None # If not found from arXiv, we cannot proceed to save a "Paper" object yet.


        # 2. Semantic Scholar에서 인용 관계 정보 가져오기
        semantic_scholar_crawler = self.crawlers["semantic_scholar"]

        s2_paper_id = semantic_scholar_crawler.get_semantic_scholar_paper_id(
            arxiv_id=arxiv_paper_data["paper_id"],
            title=arxiv_paper_data["title"],
            doi=arxiv_paper_data["doi"]
        )

        if s2_paper_id:
            # Use the obtained Semantic Scholar paper_id for fetching citations
            citation_data = semantic_scholar_crawler.get_paper_citations_and_references(s2_paper_id)

            # 3. 크롤링된 데이터에 인용 관계 정보 병합
            arxiv_paper_data["references_ids"] = citation_data["references_ids"]
            arxiv_paper_data["cited_by_ids"] = citation_data["cited_by_ids"]
            logger.info(f"Semantic Scholar에서 논문 {s2_paper_id}의 인용/피인용 정보 크롤링 성공 및 병합.")
        else:
            logger.warning(f"Semantic Scholar에서 논문 {arxiv_paper_data['paper_id']}의 Semantic Scholar ID를 찾을 수 없어 인용/피인용 정보를 가져오지 못했습니다.")

        # 4. 데이터베이스에 저장 (save_papers_to_db는 이미 중복 처리 로직 포함)
        try:
            save_papers_to_db([arxiv_paper_data], db)
            logger.info(f"논문 {arxiv_paper_data['paper_id']}이(가) 성공적으로 크롤링되어 저장되었습니다 (arXiv 및 Semantic Scholar 데이터 병합).")
            logger.debug(f"crawl_and_save_paper_by_id 함수 종료 (저장 완료) - paper_id: {arxiv_paper_data['paper_id']}")

            # REFERENCES (인용 논문) 제목 로깅
            for ref_id in arxiv_paper_data["references_ids"]:
                ref_title = semantic_scholar_crawler.get_paper_title(ref_id)
                if ref_title:
                    logger.debug(f"참조 논문: ID={ref_id}, 제목='{ref_title}'")
                else:
                    logger.debug(f"참조 논문: ID={ref_id}, 제목을 찾을 수 없습니다.")

            # CITED_BY (피인용 논문) 제목 로깅
            for cited_id in arxiv_paper_data["cited_by_ids"]:
                cited_title = semantic_scholar_crawler.get_paper_title(cited_id)
                if cited_title:
                    logger.debug(f"피인용 논문: ID={cited_id}, 제목='{cited_title}'")
                else:
                    logger.debug(f"피인용 논문: ID={cited_id}, 제목을 찾을 수 없습니다.")

            return arxiv_paper_data
        except Exception as e:
            logger.error(f"크롤링된 논문 {arxiv_paper_data['paper_id']} 저장 중 오류 발생: {e}", exc_info=True)
            return None 