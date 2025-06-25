import unittest
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from citation_graph.models import Base, Paper, Citation
from citation_graph.database import get_engine, get_session_local, create_db_and_tables
from citation_graph.paper_crawler import save_papers_to_db
from citation_graph.data_generator import get_predefined_papers

# 로깅 설정 (테스트 시에도 디버그 로그 확인)
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestDataFlow(unittest.TestCase):

    def setUp(self):
        logger.debug("테스트 setUp 시작")
        # 테스트를 위한 인메모리 SQLite 데이터베이스 사용
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine) # 모든 테이블 생성
        self.Session = sessionmaker(bind=self.engine)
        self.session = self.Session()
        logger.debug("인메모리 데이터베이스 및 세션 설정 완료")

        # 기존 get_session_local을 임시로 오버라이드하여 테스트 세션 사용
        # 이는 테스트 환경에서만 적용되며, 실제 앱 동작에는 영향을 주지 않습니다.
        global _original_get_session_local
        if 'get_session_local' in globals() and not hasattr(self, '_original_get_session_local'):
            _original_get_session_local = get_session_local
        
        def mock_get_session_local():
            return self.session
        
        import citation_graph.database
        citation_graph.database.get_session_local = mock_get_session_local
        logger.debug("get_session_local 모의 객체 설정 완료")
        logger.debug("테스트 setUp 종료")

    def tearDown(self):
        logger.debug("테스트 tearDown 시작")
        self.session.close()
        Base.metadata.drop_all(self.engine) # 모든 테이블 삭제
        logger.debug("테스트 세션 닫고 테이블 삭제 완료")

        # get_session_local 원본으로 복원
        if '_original_get_session_local' in globals():
            import citation_graph.database
            citation_graph.database.get_session_local = _original_get_session_local
            del globals()['_original_get_session_local']
            logger.debug("get_session_local 원본으로 복원 완료")

        logger.debug("테스트 tearDown 종료")

    def test_save_and_retrieve_papers(self):
        logger.debug("test_save_and_retrieve_papers 테스트 시작")
        papers_data_to_save = get_predefined_papers()
        logger.debug(f"미리 정의된 논문 데이터 로드: {len(papers_data_to_save)}개")
        
        # 데이터 저장
        save_papers_to_db(papers_data_to_save, self.session)
        logger.debug("미리 정의된 논문 데이터베이스 저장 완료")

        # 저장된 논문 확인
        papers_in_db = self.session.query(Paper).all()
        self.assertEqual(len(papers_in_db), 6, "여섯 논문이 모두 저장되어야 합니다.")
        logger.debug(f"저장된 논문 수 확인: {len(papers_in_db)}개")

        # 특정 논문 데이터 검증 (예: paper_A)
        paper_A = self.session.query(Paper).filter_by(paper_id="paper_A").first()
        self.assertIsNotNone(paper_A)
        self.assertEqual(paper_A.title, "A Novel Approach to Citation Graph Analysis")
        self.assertEqual(paper_A.year, 2022)
        self.assertIn("Alice", paper_A.authors)
        logger.debug(f"'{paper_A.title}' 논문 데이터 검증 완료: {paper_A.title}")

        # 인용 관계 검증
        citations_in_db = self.session.query(Citation).all()
        # A->B, A->C, D->A, E->A, C->F (총 5개 예상)
        self.assertEqual(len(citations_in_db), 5, "저장된 인용 관계 수가 예상(5개)과 일치해야 합니다.")
        logger.debug(f"저장된 인용 관계 수 확인: {len(citations_in_db)}개")

        # 특정 인용 관계 검증 (예: paper_A가 인용한 논문)
        paperA_refs = [c.cited_paper_id for c in self.session.query(Citation).filter_by(citing_paper_id="paper_A").all()]
        paperA_ref_titles = [self.session.query(Paper).filter_by(paper_id=ref_id).first().title for ref_id in paperA_refs]
        
        expected_paperA_ref_ids = ["paper_B", "paper_C"]
        expected_paperA_ref_titles = [self.session.query(Paper).filter_by(paper_id=pid).first().title for pid in expected_paperA_ref_ids]

        self.assertCountEqual(paperA_ref_titles, expected_paperA_ref_titles, f"'{paper_A.title}'의 인용 논문 제목이 일치해야 합니다.")
        logger.debug(f"'{paper_A.title}' 논문의 인용 관계 검증 완료 (인용 논문 제목: {paperA_ref_titles})")
        logger.debug("test_save_and_retrieve_papers 테스트 종료")

    def test_duplicate_paper_handling(self):
        logger.debug("test_duplicate_paper_handling 테스트 시작")
        papers_data = [get_predefined_papers()[0]] # 첫 번째 미리 정의된 논문 (paper_A)만 사용
        logger.debug(f"단일 논문 데이터 로드: {len(papers_data)}개")

        save_papers_to_db(papers_data, self.session) # 첫 번째 저장 시 self.session 전달
        logger.debug("첫 번째 저장 완료")

        # 동일한 논문을 다시 저장 시도
        save_papers_to_db(papers_data, self.session) # 두 번째 저장 시도 (건너뛰어질 것) 시 self.session 전달
        logger.debug("두 번째 저장 시도 완료")

        papers_in_db = self.session.query(Paper).all()
        self.assertEqual(len(papers_in_db), 1, "중복 논문은 저장되지 않아야 합니다.")
        logger.debug(f"중복 논문 처리 확인: {len(papers_in_db)}개 논문 (제목: {papers_data[0]['title']})")

        # 인용 관계도 중복 저장되지 않는지 확인
        citations_in_db = self.session.query(Citation).all()
        # 단일 논문 (paper_A) 저장 시, paper_A가 인용하는 논문(references_ids)과
        # paper_A를 인용하는 논문(cited_by_ids)에 대한 인용 관계가 모두 생성됩니다.
        expected_citations_for_single_paper = 4 # paper_A의 references_ids (2) + cited_by_ids (2) = 4
        self.assertEqual(len(citations_in_db), expected_citations_for_single_paper, "중복 인용 관계도 저장되지 않아야 합니다.")
        logger.debug(f"중복 인용 관계 처리 확인: {len(citations_in_db)}개 인용 관계")

        logger.debug("test_duplicate_paper_handling 테스트 종료")

if __name__ == '__main__':
    unittest.main() 