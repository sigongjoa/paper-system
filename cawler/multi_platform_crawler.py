import logging
import requests
import json
import xml.etree.ElementTree as ET
import time
import re
import feedparser
from datetime import datetime, timedelta, timezone
from typing import List, Generator
from urllib.parse import quote

# Deepsearch backend imports
from deepsearch.backend.core.models import Paper, Citation
from deepsearch.backend.db.connection import get_engine, get_session_local
from sqlalchemy.orm import Session
from deepsearch.backend.core.config import Config
from deepsearch.backend.core.embedding_manager import EmbeddingManager

logger = logging.getLogger(__name__)

# 전역으로 config 및 embedding_manager 인스턴스 생성
config = Config()
embedding_manager = EmbeddingManager()

# --- ArxivCrawler Class ---
class ArxivCrawler:
    def __init__(self, delay=None):
        logger.debug("ArxivCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.base_url = self.config.ARXIV_BASE_URL
        self.delay = delay if delay is not None else self.config.ARXIV_DELAY
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
    
    def _make_request(self, query: str, start: int = 0, max_results: int = config.ARXIV_MAX_RESULTS) -> str:
        logger.debug(f"_make_request 함수 시작 - query: {query}, start: {start}, max_results: {max_results}")
        self._wait_for_rate_limit()
        
        params = {
            'search_query': query,
            'start': start,
            'max_results': max_results,
            'sortBy': 'submittedDate',
            'sortOrder': 'descending'
        }
        
        full_url = f"{self.base_url}?" + "&".join([f"{k}={v}" for k, v in params.items()])
        logger.debug(f"URL: {full_url}")
        logger.debug(f"Requesting arXiv API - query: {query}, start={start}, max={max_results}")
        
        response = requests.get(self.base_url, params=params)
        self.last_request_time = time.time()
        
        logger.debug(f"API response status: {response.status_code}, length={len(response.text)}")
        logger.debug("_make_request 함수 종료")
        return response.text
    
    def _parse_entry(self, entry) -> Paper:
        logger.debug("_parse_entry 함수 시작")
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        arxiv_id = entry.find('atom:id', ns).text.split('/')[-1]
        title = entry.find('atom:title', ns).text.strip()
        abstract = entry.find('atom:summary', ns).text.strip()
        
        authors = []
        for author in entry.findall('atom:author', ns):
            name = author.find('atom:name', ns).text
            authors.append(name)
        
        categories = []
        for category in entry.findall('atom:category', ns):
            categories.append(category.get('term'))
        
        pdf_link = None
        for link in entry.findall('atom:link', ns):
            if link.get('type') == 'application/pdf':
                pdf_link = link.get('href')
                break
        
        published = datetime.fromisoformat(entry.find('atom:published', ns).text.replace('Z', '+00:00'))
        updated = datetime.fromisoformat(entry.find('atom:updated', ns).text.replace('Z', '+00:00'))
        
        raw_published = entry.find('atom:published', ns).text
        raw_updated = entry.find('atom:updated', ns).text
        logger.debug(f"XML: {arxiv_id} - 원본 published='{raw_published}', updated='{raw_updated}'")
        
        text_to_embed = f"{title}. {abstract}"
        embedding = self.embedding_manager.get_embedding(text_to_embed)

        # 논문 발행 연도 추출
        year = published.year if published else None
        logger.debug(f"논문 ID: {arxiv_id}, 발행 연도: {year}")

        paper = Paper(
            paper_id=arxiv_id,
            platform='arxiv',
            title=title,
            abstract=abstract,
            authors=authors,
            categories=categories,
            pdf_url=pdf_link,
            published_date=published,
            updated_date=updated,
            embedding=embedding if embedding is not None else None,
            year=year,
            references_ids=[],
            cited_by_ids=[],
        )
        logger.debug(f"_parse_entry 함수 종료 - paper_id: {paper.paper_id}")
        return paper
    
    def crawl_papers(self, query: str, start_date: datetime, end_date: datetime, batch_size: int = None, limit: int = config.ARXIV_DEFAULT_LIMIT) -> Generator[Paper, None, None]:
        logger.debug(f"crawl_papers 함수 시작 - query: {query}, start_date: {start_date}, end_date: {end_date}, limit: {limit}")
        logger.debug(f"Original query='{query}'")
        logger.debug(f"Full query (WORKING): {query}")
        logger.debug(f"Getting latest {limit} papers (no date filtering)")
        
        if batch_size is None:
            batch_size = min(limit * 2, 50)
        
        start_index = 0
        total_found = 0
        papers_yielded = 0
        
        while papers_yielded < limit:
            api_batch_size = min(batch_size, limit * 2)
            xml_response = self._make_request(query, start_index, api_batch_size)
            
            logger.debug(f"XML Response preview: {xml_response[:500]}...")
            
            root = ET.fromstring(xml_response)
            
            ns = {'atom': 'http://www.w3.org/2005/Atom', 'opensearch': 'http://a9.com/-/spec/opensearch/1.1/'}
            
            total_results = int(root.find('opensearch:totalResults', ns).text)
            start_result = int(root.find('opensearch:startIndex', ns).text)
            items_per_page = int(root.find('opensearch:itemsPerPage', ns).text)
            
            logger.debug(f"PAGING: Batch {start_index//batch_size + 1} - start_index={start_index}, batch_size={batch_size}")
            logger.debug(f"Batch {start_index//batch_size + 1} - Total: {total_results}, Items: {items_per_page}")
            
            entries = root.findall('atom:entry', ns)
            if not entries:
                logger.debug("No more entries found")
                break
            
            for entry in entries:
                if papers_yielded >= limit:
                    logger.debug(f"Reached limit ({limit}) papers")
                    break
                    
                paper = self._parse_entry(entry)
                total_found += 1
                papers_yielded += 1
                
                arxiv_year_month = paper.paper_id[:4] if len(paper.paper_id) >= 4 else 'unknown'
                if arxiv_year_month.startswith('250'):
                    logger.debug(f"LATEST: Found 2025 paper: {paper.paper_id}")
                
                logger.debug(f"Paper {papers_yielded}/{limit}: {paper.paper_id} - 발행일:{paper.published_date.date()}, 출판일:{paper.updated_date.date()}, 제목:{paper.title[:30]}...")
                
                if end_date and paper.published_date.date() > datetime.strptime(end_date, '%Y-%m-%d').date():
                    logger.debug(f"Skipping paper {paper.paper_id} due to future published_date: {paper.published_date.date()} > {end_date}")
                    continue
                
                yield paper
            
            if papers_yielded >= limit:
                logger.debug(f"Found {papers_yielded} papers - Stop crawling")
                break
            
            start_index += batch_size
            if start_index >= total_results:
                logger.debug(f"Stopping at start_index={start_index} (no more results)")
                break
        
        logger.debug(f"Crawling completed. Total processed: {total_found}, Yielded: {papers_yielded}")
        logger.debug("crawl_papers 함수 종료")

# --- BioRxivCrawler Class ---
class BioRxivCrawler:
    def __init__(self):
        logger.debug("BioRxivCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.base_url = self.config.BIORXIV_API_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logging.info("BioRxiv crawler initialized")
        logger.debug("BioRxivCrawler __init__ 함수 종료")

    def crawl_papers(self, query: str, start_date=None, end_date=None, limit=20):
        logger.debug(f"BioRxiv: crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        try:
            logging.info(f"BioRxiv: Starting crawl - query='{query}', limit={limit}")
            papers = []
            
            servers = ['biorxiv', 'medrxiv']

            # 날짜 범위 설정
            if start_date is None or end_date is None:
                # 기본값: 오늘부터 7일 전까지
                end_date_obj = datetime.now()
                start_date_obj = end_date_obj - timedelta(days=7)
                start_date_str = start_date_obj.strftime('%Y-%m-%d')
                end_date_str = end_date_obj.strftime('%Y-%m-%d')
            else:
                start_date_str = start_date.strftime('%Y-%m-%d') if isinstance(start_date, datetime) else start_date
                end_date_str = end_date.strftime('%Y-%m-%d') if isinstance(end_date, datetime) else end_date

            interval = f"{start_date_str}/{end_date_str}"
            cursor = 0 # 페이지네이션 커서
            
            for server in servers:
                if len(papers) >= limit:
                    break
                    
                logging.info(f"BioRxiv: Crawling {server}: latest {limit} papers (date range: {interval})")
                
                # API URL을 날짜 범위 형식으로 변경
                url = f"{self.base_url}/details/{server}/{interval}/{cursor}"
                
                # 쿼리 매개변수로 검색어 추가 (BioRxiv API가 검색어를 지원하는 경우)
                params = {}
                if query: # 쿼리가 있는 경우에만 category 파라미터 추가 시도
                    # BioRxiv API는 category 파라미터를 지원합니다.
                    # 실제 API 문서에 따르면 query가 아닌 category 파라미터로 사용
                    params['category'] = query.replace(' ', '_') # 공백은 언더스코어로 대체

                logging.info(f"BioRxiv: API URL: {url}, Params: {params}")
                
                response = self.session.get(url, params=params, timeout=60)
                response.raise_for_status()
                
                data = response.json()
                logging.info(f"BioRxiv: API response - status={response.status_code}, data_keys={list(data.keys())}")
                
                if 'collection' in data and data['collection']:
                    logging.info(f"BioRxiv: Found {len(data['collection'])} papers from {server}")
                    for item in data['collection']:
                        if len(papers) >= limit:
                            break
                            
                        paper = self._parse_paper(item, server)
                        if paper:
                            papers.append(paper)
                            logging.info(f"BioRxiv: Yielding paper: {paper.title[:50]}...")
                            yield paper
                else:
                    logging.warning(f"BioRxiv: No 'collection' key in response from {server} or collection is empty.")
                            
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"BioRxiv crawl error: {e}")
            import traceback
            traceback.print_exc()
        logger.debug("BioRxiv: crawl_papers 함수 종료")

    def _parse_paper(self, item, server):
        logger.debug(f"BioRxiv: _parse_paper 함수 시작 - server: {server}")
        try:
            paper_id = f"{server}_{item.get('doi', '').replace('/', '_')}"
            title = item.get('title', '')
            abstract = item.get('abstract', '')
            authors_str = item.get('authors', '')
            authors = authors_str.split(';') if authors_str else []
            category = item.get('category', server)
            pdf_url = f"https://www.{server}.org/content/10.1101/{item.get('doi', '').split('/')[-1]}v1.full.pdf" if item.get('doi') else None
            published_date = datetime.strptime(item.get('date', ''), '%Y-%m-%d') if item.get('date') else datetime.now()
            
            text_to_embed = f"{title}. {abstract}"
            embedding = self.embedding_manager.get_embedding(text_to_embed) # self.embedding_manager 사용

            paper = Paper(
                paper_id=paper_id,
                external_id=item.get('doi', ''),
                platform=server, 
                title=title,
                abstract=abstract,
                authors=authors,
                categories=[category],
                pdf_url=pdf_url,
                embedding=embedding if embedding is not None else None,
                published_date=published_date,
                updated_date=published_date
            )
            logger.debug(f"BioRxiv: _parse_paper 함수 종료 - paper_id: {paper.paper_id}")
            return paper
            
        except Exception as e:
            logging.error(f"BioRxiv parse error: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- PMCCrawler Class ---
class PMCCrawler:
    def __init__(self):
        logger.debug("PMCCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.esearch_base_url = self.config.PMC_ESEARCH_BASE_URL
        self.efetch_base_url = self.config.PMC_EFETCH_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logging.info("PMC crawler initialized")
        logger.debug("PMCCrawler __init__ 함수 종료")

    def crawl_papers(self, query: str, start_date=None, end_date=None, limit=20):
        logger.debug(f"PMC: crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        try:
            logging.info(f"PMC: Starting crawl - query='{query}', limit={limit}")
            papers = []
            
            query_terms = []
            
            if query:
                query_terms.append(f'({query})')
            
            if start_date and end_date:
                date_filter = f'("{start_date}"[Publication Date] : "{end_date}"[Publication Date])'
                query_terms.append(date_filter)
            
            if not query_terms:
                query_terms.append('medicine[MeSH Terms] OR biology[MeSH Terms]')
            
            search_query = ' AND '.join(query_terms)
            
            logging.info(f"PMC: Search query: {search_query}")
            
            search_url = f"{self.esearch_base_url}"
            search_params = {
                'db': 'pmc',
                'term': search_query,
                'retmax': limit,
                'retmode': 'xml',
                'sort': 'pub_date',
                'tool': 'arxiv_system',
                'email': self.config.PMC_API_EMAIL # self.config 사용
            }
            
            logging.info(f"PMC: API URL: {search_url}")
            response = self.session.get(search_url, params=search_params, timeout=60)
            response.raise_for_status()
            
            try:
                root = ET.fromstring(response.content)
                id_list = root.findall('.//Id')
                ids = [id_elem.text for id_elem in id_list]
                logging.info(f"PMC: Found {len(ids)} paper IDs")
                
                if ids:
                    for paper_id in ids[:limit]:
                        try:
                            paper = self._fetch_paper_details(paper_id)
                            if paper:
                                papers.append(paper)
                                logger.debug(f"PMC: Yielding paper: {paper.title[:50]}...")
                                yield paper
                        except Exception as e:
                            logging.error(f"PMC: Error processing paper {paper_id}: {e}")
                            continue
                            
                        time.sleep(0.5)
                else:
                    logging.warning("PMC: No paper IDs found")
                        
            except ET.ParseError as e:
                logging.error(f"PMC: XML parse error: {e}")
                logging.error(f"PMC: Response content: {response.text[:500]}")
                return
                        
        except Exception as e:
            logging.error(f"PMC crawl error: {e}")
            import traceback
            traceback.print_exc()
        logger.debug("PMC: crawl_papers 함수 종료")

    def _fetch_paper_details(self, paper_id):
        logger.debug(f"PMC: _fetch_paper_details 함수 시작 - paper_id: {paper_id}")
        try:
            fetch_url = f"{self.efetch_base_url}"
            fetch_params = {
                'db': 'pmc',
                'id': paper_id,
                'rettype': 'xml',
                'tool': 'arxiv_system',
                'email': self.config.PMC_API_EMAIL # self.config 사용
            }
            
            response = self.session.get(fetch_url, params=fetch_params, timeout=60)
            response.raise_for_status()
            
            root = ET.fromstring(response.content)
            
            title = ''
            title_elem = root.find('.//article-title')
            if title_elem is not None:
                title = title_elem.text or ''
            
            abstract = ''
            abstract_elem = root.find('.//abstract/p')
            if abstract_elem is None:
                abstract_elem = root.find('.//abstract')
            if abstract_elem is not None:
                abstract = abstract_elem.text or ''
            
            authors = []
            for contrib in root.findall('.//contrib[@contrib-type="author"]'):
                given_names = contrib.find('.//given-names')
                surname = contrib.find('.//surname')
                if given_names is not None and surname is not None:
                    authors.append(f"{given_names.text} {surname.text}")
            
            subjects = []
            for subj in root.findall('.//subject'):
                if subj.text:
                    subjects.append(subj.text)
            
            pub_date = root.find('.//pub-date[@pub-type="epub"]')
            if pub_date is None:
                pub_date = root.find('.//pub-date')
                
            published_date = datetime.now()
            if pub_date is not None:
                year = pub_date.find('year')
                month = pub_date.find('month')
                day = pub_date.find('day')
                
                if year is not None:
                    try:
                        published_date = datetime(
                            int(year.text),
                            int(month.text) if month is not None else 1,
                            int(day.text) if day is not None else 1
                        )
                    except:
                        published_date = datetime.now()
            
            text_to_embed = f"{title}. {abstract}"
            embedding = self.embedding_manager.get_embedding(text_to_embed) # self.embedding_manager 사용

            paper = Paper(
                paper_id=f"PMC{paper_id}",
                external_id=paper_id,
                platform='pmc',
                title=title,
                abstract=abstract,
                authors=authors,
                categories=subjects if subjects else ['Medicine'],
                pdf_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{paper_id}/pdf/",
                embedding=embedding if embedding is not None else None,
                published_date=published_date,
                updated_date=published_date
            )
            logger.debug(f"PMC: _fetch_paper_details 함수 종료 - paper_id: {paper.paper_id}")
            return paper
            
        except Exception as e:
            logging.error(f"PMC fetch error for {paper_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- PLOSCrawler Class ---
class PLOSCrawler:
    def __init__(self):
        logger.debug("PLOSCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.base_url = self.config.PLOS_API_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logging.info("PLOS crawler initialized")
        logger.debug("PLOSCrawler __init__ 함수 종료")

    def crawl_papers(self, query: str, start_date=None, end_date=None, limit=20):
        logger.debug(f"PLOS: crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        try:
            logging.info(f"PLOS: Starting crawl - query='{query}', limit={limit}")
            papers = []
            
            query_parts = []
            
            if query:
                query_parts.append(f'everything:"{query}"')
            
            if start_date and end_date:
                date_filter = f'publication_date:[{start_date}T00:00:00Z TO {end_date}T23:59:59Z]'
                query_parts.append(date_filter)
            
            if not query_parts:
                query_parts.append('everything:"science"')
            
            search_query = ' AND '.join(query_parts)
            
            logging.info(f"PLOS: Search query: {search_query}")
            
            params = {
                'q': search_query,
                'fl': 'id,title_display,abstract,author_display,publication_date,journal,subject,article_type',
                'wt': 'json',
                'rows': limit,
                'sort': 'publication_date desc',
                'fq': 'article_type:"Research Article" OR article_type:"Review"'
            }
            
            logging.info(f"PLOS: API URL: {self.base_url}")
            response = self.session.get(self.base_url, params=params, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            logging.debug(f"PLOS: API response - status={response.status_code}, keys={list(data.keys())}")
            
            if 'response' in data and 'docs' in data['response']:
                docs = data['response']['docs']
                logging.info(f"PLOS: Found {len(docs)} papers")
                for doc in docs:
                    paper = self._parse_paper(doc)
                    if paper:
                        papers.append(paper)
                        logger.debug(f"PLOS: Yielding paper: {paper.title[:50]}...")
                        yield paper
                        
                    if len(papers) >= limit:
                        break
            else:
                logging.warning(f"PLOS: No 'response' or 'docs' in API response")
                        
        except Exception as e:
            logging.error(f"PLOS crawl error: {e}")
            import traceback
            traceback.print_exc()
        logger.debug("PLOS: crawl_papers 함수 종료")

    def _parse_paper(self, doc):
        logger.debug("PLOS: _parse_paper 함수 시작")
        try:
            paper_id = f"PLOS_{doc.get('id', '').replace('/', '_')}"
            title = doc.get('title_display', [''])[0] if isinstance(doc.get('title_display'), list) else doc.get('title_display', '')
            
            abstract_list = doc.get('abstract', [])
            abstract = abstract_list[0] if abstract_list and isinstance(abstract_list, list) else str(abstract_list) if abstract_list else ''
            
            authors_raw = doc.get('author_display', [])
            authors = []
            if isinstance(authors_raw, list):
                for author_item in authors_raw:
                    if isinstance(author_item, str):
                        authors.append(author_item.strip())
                    elif isinstance(author_item, dict) and 'name' in author_item:
                        authors.append(author_item['name'].strip())
            else:
                authors.append(str(authors_raw).strip())
            
            subjects = doc.get('subject', [])
            if isinstance(subjects, list):
                categories = [s.strip() for s in subjects[:3]]
            else:
                categories = [str(subjects).strip()] if subjects else ['Science']
            
            doi = doc.get('id', '')
            pdf_url = f"https://journals.plos.org/plosone/article/file?id={doi}&type=printable" if doi else None
            
            pub_date = doc.get('publication_date')
            published_date = datetime.now()
            if pub_date:
                try:
                    if isinstance(pub_date, list):
                        pub_date = pub_date[0]
                    published_date = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                except:
                    published_date = datetime.now()
            
            text_to_embed = f"{title}. {abstract}"
            embedding = self.embedding_manager.get_embedding(text_to_embed) # self.embedding_manager 사용

            paper = Paper(
                paper_id=paper_id,
                external_id=doi,
                platform='plos',
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                pdf_url=pdf_url,
                embedding=embedding if embedding is not None else None,
                published_date=published_date,
                updated_date=published_date
            )
            logger.debug(f"PLOS: _parse_paper 함수 종료 - paper_id: {paper.paper_id}")
            return paper
            
        except Exception as e:
            logging.error(f"PLOS parse error: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- DOAJCrawler Class ---
class DOAJCrawler:
    def __init__(self):
        logger.debug("DOAJCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.base_url = self.config.DOAJ_API_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logging.info("DOAJ crawler initialized")
        logger.debug("DOAJCrawler __init__ 함수 종료")

    def crawl_papers(self, query: str, start_date=None, end_date=None, limit=20):
        logger.debug(f"DOAJ: crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        try:
            logging.info(f"DOAJ: Starting crawl - query='{query}', limit={limit}")
            papers = []
            
            query_parts = []
            
            if query:
                query_parts.append(f'bibjson.title:"{query}" OR bibjson.abstract:"{query}"')
            
            if start_date and end_date:
                start_year = start_date.split('-')[0]
                end_year = end_date.split('-')[0]
                date_filter = f'bibjson.year:[{start_year} TO {end_year}]'
                query_parts.append(date_filter)
            
            if not query_parts:
                query_parts.append('science OR research OR article')
            
            search_query = ' AND '.join(query_parts)
            
            logging.info(f"DOAJ: Search query: {search_query}")
            
            encoded_query = quote(search_query)
            url = f"{self.base_url}/search/articles/{encoded_query}"
            params = {
                'pageSize': limit,
                'sort': 'created_date:desc'
            }
            
            logging.info(f"DOAJ: API URL: {url}")
            response = self.session.get(url, params=params, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            logging.debug(f"DOAJ: API response - status={response.status_code}, keys={list(data.keys())}")
            
            if 'results' in data:
                results = data['results']
                logging.info(f"DOAJ: Found {len(results)} papers")
                for item in results:
                    paper = self._parse_paper(item)
                    if paper:
                        papers.append(paper)
                        logger.debug(f"DOAJ: Yielding paper: {paper.title[:50]}...")
                        yield paper
                        
                    if len(papers) >= limit:
                        break
            else:
                logging.warning(f"DOAJ: No 'results' in API response")
                        
        except Exception as e:
            logging.error(f"DOAJ crawl error: {e}")
            import traceback
            traceback.print_exc()
        logger.debug("DOAJ: crawl_papers 함수 종료")

    def _parse_paper(self, item):
        logger.debug("DOAJ: _parse_paper 함수 시작")
        try:
            bibjson = item.get('bibjson', {})
            
            paper_id = f"DOAJ_{item.get('id', '').replace('/', '_')}"
            title = bibjson.get('title', '')
            abstract = bibjson.get('abstract', '')
            
            authors = []
            for author in bibjson.get('author', []):
                name = author.get('name', '')
                if name:
                    authors.append(name)
            
            subjects = []
            for subj in bibjson.get('subject', []):
                term = subj.get('term', '')
                if term:
                    subjects.append(term)
            categories = subjects[:3] if subjects else ['General']
            
            links = bibjson.get('link', [])
            pdf_url = None
            for link in links:
                if link.get('type') == 'fulltext' and 'pdf' in link.get('content_type', '').lower():
                    pdf_url = link.get('url', '')
                    break
            
            if not pdf_url:
                for link in links:
                    if link.get('type') == 'fulltext':
                        pdf_url = link.get('url', '')
                        break
            
            year = bibjson.get('year')
            month = bibjson.get('month')
            
            published_date = datetime.now()
            if year:
                try:
                    published_date = datetime(
                        int(year),
                        int(month) if month else 1,
                        1
                    )
                except:
                    published_date = datetime.now()
            
            text_to_embed = f"{title}. {abstract}"
            embedding = self.embedding_manager.get_embedding(text_to_embed) # self.embedding_manager 사용

            paper = Paper(
                paper_id=paper_id,
                external_id=item.get('id', ''),
                platform='doaj',
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                pdf_url=pdf_url,
                embedding=embedding if embedding is not None else None,
                published_date=published_date,
                updated_date=published_date
            )
            logger.debug(f"DOAJ: _parse_paper 함수 종료 - paper_id: {paper.paper_id}")
            return paper
            
        except Exception as e:
            logging.error(f"DOAJ parse error: {e}")
            import traceback
            traceback.print_exc()
            return None

# --- ArxivRSSCrawler Class ---
class ArxivRSSCrawler:
    def __init__(self):
        logger.debug("ArxivRSSCrawler __init__ 함수 시작")
        self.config = config # 전역 config를 인스턴스 변수로 할당
        self.embedding_manager = embedding_manager # 전역 embedding_manager를 인스턴스 변수로 할당
        self.base_rss_url = self.config.ARXIV_RSS_BASE_URL
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        logging.info("ArxivRSSCrawler initialized")
        logger.debug("ArxivRSSCrawler __init__ 함수 종료")
    
    def _parse_rss_entry(self, entry) -> Paper:
        logger.debug(f"_parse_rss_entry 함수 시작 - entry: {getattr(entry, 'title', 'No Title')}")
        try:
            arxiv_id = getattr(entry, 'link', '').split('/')[-1] if getattr(entry, 'link', '') else None
            if not arxiv_id:
                raise ValueError("Missing arxiv_id in RSS entry.")

            title = getattr(entry, 'title', '').strip()
            if not title:
                raise ValueError("Missing title in RSS entry.")
            
            summary = getattr(entry, 'summary', '')
            abstract = ""
            if "Abstract: " in summary:
                try:
                    abstract = summary.split("Abstract: ", 1)[1].strip()
                except IndexError:
                    logger.warning(f"Abstract split failed for entry {arxiv_id}. Using full summary as abstract.")
                    abstract = summary.strip()
            else:
                abstract = summary.strip()
            
            authors = []
            if "Authors: " in summary:
                try:
                    author_part = summary.split("Authors: ")[1].split("Abstract:")[0].strip()
                    authors = [name.strip() for name in author_part.split(',') if name.strip()]
                except (IndexError, AttributeError):
                    logger.warning(f"Authors parse failed for entry {arxiv_id}. Setting to 'Unknown'.")
                    authors = ['Unknown']
            else:
                authors = ['Unknown']
            
            categories = [getattr(entry, 'category', 'cs.AI').strip()]
            
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                try:
                    published_date = datetime(*entry.published_parsed[:6])
                except (TypeError, ValueError, IndexError) as e:
                    logging.warning(f"Failed to parse published_date for entry {arxiv_id}: {e}. Using current time.")
                    published_date = datetime.now()
            else:
                published_date = datetime.now()
            
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            
            text_to_embed = f"{title}. {abstract}"
            embedding = self.embedding_manager.get_embedding(text_to_embed) # self.embedding_manager 사용

            logger.debug(f"RSS parsed: {arxiv_id} - {title[:50]}...")
            
            paper = Paper(
                paper_id=arxiv_id,
                external_id=arxiv_id,
                platform='arxiv',
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                pdf_url=pdf_url,
                embedding=embedding if embedding is not None else None,
                published_date=published_date,
                updated_date=published_date
            )
            logger.debug(f"_parse_rss_entry 함수 종료 - paper_id: {paper.paper_id}")
            return paper
            
        except Exception as e:
            entry_id = getattr(entry, 'link', 'N/A').split('/')[-1] if hasattr(entry, 'link') else 'N/A'
            logging.error(f"RSS parsing error for entry {entry_id}: {str(e)}", exc_info=True)
            return None
    
    def crawl_papers(self, query: str = None, start_date=None, end_date=None, limit: int = 50) -> Generator[Paper, None, None]:
        logger.debug(f"ArxivRSSCrawler: crawl_papers 함수 시작 - query: {query}, limit: {limit}")
        papers_count = 0
        
        if query:
            categories_to_crawl = [query] if '.' in query else ['cs.AI']
        else:
            categories_to_crawl = ['cs.AI', 'math.CO']

        logging.info(f"ArxivRSSCrawler: Crawling categories: {categories_to_crawl} for query='{query}'")

        for category in categories_to_crawl:
            if papers_count >= limit:
                break
            rss_url = f"{self.base_rss_url}/{category}"
            logging.info(f"Fetching RSS: {rss_url}")
            
            try:
                response = self.session.get(rss_url, timeout=15)
                response.raise_for_status()
                
                logger.debug(f"HTTP 상태: {response.status_code}, 응답 길이: {len(response.text)}")
                
                feed = feedparser.parse(response.text)
                
                logger.debug(f"Feed version: {feed.version}, Encoding: {feed.encoding}")
                logger.debug(f"Feed title: {feed.feed.get('title', 'No title')}")
                logger.debug(f"Entries found: {len(feed.entries)}")
                
                if not feed.entries:
                    logging.warning(f"No entries for {category}")
                    continue
                
                for i, entry in enumerate(feed.entries):
                    if papers_count >= limit:
                        break
                    
                    logger.debug(f"Processing entry {i+1}/{len(feed.entries)}: keys={entry.keys()}, published_parsed={getattr(entry, 'published_parsed', 'N/A')}")
                    paper = self._parse_rss_entry(entry)
                    if paper: # paper가 None이 아닌 경우에만 처리
                        logger.debug(f"Parsed paper from entry {i+1}: {paper.paper_id}")
                        if start_date and paper.published_date < datetime.strptime(start_date, '%Y-%m-%d'):
                            logger.debug(f"Skipping paper {paper.paper_id} due to old published_date: {paper.published_date.date()} < {start_date}")
                            continue
                        if end_date and paper.published_date.date() > datetime.strptime(end_date, '%Y-%m-%d').date():
                            logger.debug(f"Skipping paper {paper.paper_id} due to future published_date: {paper.published_date.date()} > {end_date}")
                            continue

                        papers_count += 1
                        logger.debug(f"RSS paper {papers_count}/{limit}: {paper.paper_id}")
                        yield paper
                    else:
                        logger.warning(f"Skipping malformed RSS entry {i}.")
                        continue
                        
            except Exception as e:
                logging.error(f"RSS fetch error for {category}: {str(e)}")
                continue
        
        logging.info(f"RSS crawling completed: {papers_count} papers total")
        logger.debug("ArxivRSSCrawler: crawl_papers 함수 종료")


# --- Original multi_platform_crawler functions ---

def save_papers_to_db(papers_data: list):
    logger.debug("save_papers_to_db 함수 시작")
    engine = get_engine()
    session = Session(bind=engine)
    try:
        saved_count = 0
        skipped_count = 0
        logger.debug(f"Processing {len(papers_data)} papers for database save.")
        for data in papers_data:
            logger.debug(f"Checking paper with ID: {data.get('paper_id', 'N/A')}")
            existing_paper = session.query(Paper).filter_by(paper_id=data['paper_id']).first()
            if existing_paper:
                logger.info(f"Paper with ID {data['paper_id']} already exists. Skipping.")
                skipped_count += 1
                continue

            if "platform_metadata" not in data:
                data["platform_metadata"] = None
            
            logger.debug(f"Adding new paper: {data['title'][:50]}...")
            new_paper = Paper(
                paper_id=data['paper_id'],
                external_id=data.get('external_id', None),
                platform=data['platform'],
                title=data['title'],
                abstract=data['abstract'],
                authors=data['authors'],
                categories=data['categories'],
                pdf_url=data['pdf_url'],
                embedding=data['embedding'],
                published_date=data['published_date'],
                updated_date=data['updated_date'],
                year=data.get('year', None),
                references_ids=data.get('references_ids', []),
                cited_by_ids=data.get('cited_by_ids', []),
            )
            session.add(new_paper)
            saved_count += 1

            # 인용 관계 저장
            current_paper_id = data['paper_id']
            logger.debug(f"Processing citations for paper: {current_paper_id}")

            # 이 논문이 인용하는 논문들 (references_ids)
            for cited_paper_id in data.get('references_ids', []):
                if cited_paper_id and current_paper_id != cited_paper_id:
                    citation = Citation(citing_paper_id=current_paper_id, cited_paper_id=cited_paper_id)
                    session.add(citation)
                    logger.debug(f"Added citation: {current_paper_id} cites {cited_paper_id}")

            # 이 논문을 인용한 논문들 (cited_by_ids)
            for citing_paper_id in data.get('cited_by_ids', []):
                if citing_paper_id and current_paper_id != citing_paper_id:
                    citation = Citation(citing_paper_id=citing_paper_id, cited_paper_id=current_paper_id)
                    session.add(citation)
                    logger.debug(f"Added citation: {citing_paper_id} cites {current_paper_id}")

        session.commit()
        logger.info(f"Successfully processed {len(papers_data)} papers. Saved {saved_count} new papers, Skipped {skipped_count} existing papers to the database.")
    except Exception as e:
        session.rollback()
        logger.error(f"Error saving papers to database: {e}", exc_info=True)
    finally:
        session.close()
    logger.debug("save_papers_to_db 함수 종료")

def get_crawler(platform: str):
    logger.debug(f"get_crawler 함수 시작 - platform: {platform}")

    if platform.lower() == "arxiv":
        crawler = ArxivCrawler()
    elif platform.lower() == "biorxiv":
        crawler = BioRxivCrawler()
    elif platform.lower() == "pmc":
        crawler = PMCCrawler()
    elif platform.lower() == "plos":
        crawler = PLOSCrawler()
    elif platform.lower() == "doaj":
        crawler = DOAJCrawler()
    elif platform.lower() == "arxiv_rss":
        crawler = ArxivRSSCrawler()
    else:
        logger.error(f"지원하지 않는 크롤러 플랫폼: {platform}")
        raise ValueError(f"Unsupported crawler platform: {platform}")
    logger.debug(f"get_crawler 함수 종료 - crawler: {crawler.__class__.__name__}")
    return crawler

def multi_platform_crawl(query: str, platforms: list = None, max_results: int = config.DEFAULT_CRAWLER_MAX_RESULTS, start_date=None, end_date=None):
    logger.debug(f"multi_platform_crawl 함수 시작 - query: {query}, platforms: {platforms}, max_results: {max_results}, start_date: {start_date}, end_date: {end_date}")
    all_papers = []
    if not platforms:
        platforms = config.SUPPORTED_CRAWLER_PLATFORMS
    
    for platform in platforms:
        logger.info(f"[{platform.upper()}] 크롤링 시작...")
        try:
            crawler = get_crawler(platform)
            papers_from_platform = []
            for paper in crawler.crawl_papers(query=query, start_date=start_date, end_date=end_date, limit=max_results):
                papers_from_platform.append(paper.to_dict())
            
            logger.info(f"[{platform.upper()}] {len(papers_from_platform)}개 논문 크롤링 완료.")
            all_papers.extend(papers_from_platform)
        except Exception as e:
            logger.error(f"[{platform.upper()}] 크롤링 중 오류 발생: {e}", exc_info=True)
            continue
            
    logger.info(f"모든 플랫폼에서 총 {len(all_papers)}개 논문 크롤링 완료.")
    
    unique_papers = {paper['paper_id']: paper for paper in all_papers}.values()
    logger.info(f"중복 제거 후 {len(unique_papers)}개 논문 남음.")

    return list(unique_papers)