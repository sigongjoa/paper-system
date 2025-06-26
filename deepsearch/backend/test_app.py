import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import requests # requests.exceptions 사용을 위해 필요
import json # JSON 응답 파싱을 위해 필요

# 프로젝트 루트 디렉토리를 sys.path에 추가하여 app 모듈을 임포트할 수 있도록 함
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from deepsearch.backend.app import app, generate_paper_shorts, generate_shorts_for_shortgpt, generate_video_script_and_scenes, text_to_speech_conceptual, assemble_video_conceptual # 새로 추가된 함수들 임포트
from deepsearch.backend.core.models import Paper # Paper 모델 임포트 (데이터베이스 모킹을 위해)

class TestShortsGeneration(unittest.TestCase):

    def setUp(self):
        # Flask 앱을 테스트 모드로 설정
        app.config['TESTING'] = True
        self.app = app.test_client()
        # 테스트 환경 변수 설정 (실제 .env 파일에 의존하지 않도록)
        os.environ["OPENAI_API_BASE"] = "http://mock-lm-studio:1234/v1"
        os.environ["OPENAI_MODEL_NAME"] = "mock-model"
        os.environ["OPENAI_API_KEY"] = "mock-key"
        os.environ["SHORTGPT_API_BASE"] = "http://mock-shortgpt:31415/api/short-video"


    def tearDown(self):
        # 테스트 후 환경 변수 정리 (선택 사항)
        del os.environ["OPENAI_API_BASE"]
        del os.environ["OPENAI_MODEL_NAME"]
        del os.environ["OPENAI_API_KEY"]
        del os.environ["SHORTGPT_API_BASE"]

    @patch('deepsearch.backend.app.OpenAI')
    def test_generate_paper_shorts_success(self, MockOpenAI):
        """
        LM Studio를 통해 논문 초록 요약이 성공적으로 생성되는지 테스트
        """
        mock_client_instance = MockOpenAI.return_value
        mock_client_instance.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="이것은 논문의 짧은 요약입니다."))]
        )

        abstract = "이것은 과학 논문에 대한 매우 긴 초록이며 요약이 필요합니다. 방법론, 결과 및 결론에 대한 중요한 세부 정보를 포함합니다."
        shorts = generate_paper_shorts(abstract)

        self.assertEqual(shorts, "이것은 논문의 짧은 요약입니다.")
        mock_client_instance.chat.completions.create.assert_called_once()
        args, kwargs = mock_client_instance.chat.completions.create.call_args
        self.assertIn("과학 논문에 대한 매우 긴 초록", kwargs['messages'][1]['content'])
        self.assertIn("핵심 내용을 담은 간결한 '쇼츠'", kwargs['messages'][1]['content'])
        self.assertEqual(kwargs['model'], "mock-model")
        print("test_generate_paper_shorts_success 통과")

    @patch('deepsearch.backend.app.OpenAI')
    def test_generate_paper_shorts_empty_abstract(self, MockOpenAI):
        """
        빈 초록이 주어졌을 때 논문 초록 요약이 '초록 없음.'을 반환하는지 테스트
        """
        shorts = generate_paper_shorts("")
        self.assertEqual(shorts, "초록 없음.")
        MockOpenAI.return_value.chat.completions.create.assert_not_called()
        print("test_generate_paper_shorts_empty_abstract 통과")

    def test_generate_shorts_for_shortgpt_format(self):
        """
        ShortGPT 입력 형식으로 올바르게 변환되는지 테스트
        """
        abstract_shorts = "이 논문은 새로운 AI 프레임워크를 소개합니다. 비디오 생성에서 최첨단 결과를 달성합니다."
        shortgpt_payload = generate_shorts_for_shortgpt(abstract_shorts)

        self.assertIsInstance(shortgpt_payload, dict)
        self.assertIn("scenes", shortgpt_payload)
        self.assertIsInstance(shortgpt_payload["scenes"], list)
        self.assertEqual(len(shortgpt_payload["scenes"]), 1)
        self.assertIn("text", shortgpt_payload["scenes"][0])
        self.assertEqual(shortgpt_payload["scenes"][0]["text"], abstract_shorts)
        self.assertIn("searchTerms", shortgpt_payload["scenes"][0])
        self.assertIsInstance(shortgpt_payload["scenes"][0]["searchTerms"], list)
        self.assertIn("scientific paper", shortgpt_payload["scenes"][0]["searchTerms"])
        self.assertIn("config", shortgpt_payload)
        self.assertIn("music", shortgpt_payload["config"])
        self.assertIn("paddingBack", shortgpt_payload["config"])
        print("test_generate_shorts_for_shortgpt_format 통과")

    @patch('deepsearch.backend.app.next') # Mocking next(get_db())
    @patch('deepsearch.backend.app.get_db') # Mocking get_db() itself
    @patch('deepsearch.backend.app.generate_paper_shorts') # Mocking LM Studio call result
    @patch('deepsearch.backend.app.requests.post') # Mocking ShortGPT API call
    def test_generate_shorts_endpoint_success(self, mock_requests_post, mock_generate_paper_shorts, mock_get_db, mock_next):
        """
        /generate_shorts 엔드포인트가 논문 조회, LM Studio 요약, ShortGPT 호출을
        성공적으로 처리하는지 테스트
        """
        # Mock database query
        mock_db_session = MagicMock()
        mock_get_db.return_value = iter([mock_db_session]) # get_db returns an iterator that yields mock_db_session
        mock_next.return_value = mock_db_session # next(get_db()) directly returns mock_db_session

        mock_paper = MagicMock(spec=Paper)
        mock_paper.paper_id = "test_paper_123"
        mock_paper.title = "테스트 논문 제목"
        mock_paper.abstract = "이것은 테스트 논문의 초록입니다."
        mock_paper.published_date = "2023-01-01" # order_by를 위해 published_date 추가

        # query().filter().first() 에 대한 모킹
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_paper
        # query().filter().limit().all() 에 대한 모킹
        mock_db_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [mock_paper]
        # query().order_by().desc().limit().all() 에 대한 모킹
        mock_db_session.query.return_value.order_by.return_value.desc.return_value.limit.return_value.all.return_value = [mock_paper]


        # LM Studio 응답 모킹
        mock_generate_paper_shorts.return_value = "LM Studio 요약."

        # ShortGPT 성공 응답 모킹
        mock_shortgpt_response = MagicMock()
        mock_shortgpt_response.status_code = 200
        mock_shortgpt_response.json.return_value = {"videoId": "mock_video_id_abc"}
        mock_shortgpt_response.raise_for_status.return_value = None # 2xx 상태에 대해 예외 발생 안 함
        mock_requests_post.return_value = mock_shortgpt_response

        # paper_id로 테스트
        response = self.app.post('/generate_shorts', json={"paper_id": "test_paper_123"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("shorts_with_videos", data)
        self.assertEqual(len(data["shorts_with_videos"]), 1)
        self.assertEqual(data["shorts_with_videos"][0]["paper_id"], "test_paper_123")
        self.assertEqual(data["shorts_with_videos"][0]["abstract_shorts"], "LM Studio 요약.")
        self.assertEqual(data["shorts_with_videos"][0]["video_status"], "Generated - Video ID: mock_video_id_abc")
        self.assertEqual(data["shorts_with_videos"][0]["video_id"], "mock_video_id_abc")
        mock_requests_post.assert_called_once() # ShortGPT가 호출되었는지 확인

        # 다음 테스트 케이스(예: query)를 위해 모킹 초기화
        mock_requests_post.reset_mock()
        mock_generate_paper_shorts.reset_mock()
        # query().filter().first()는 None을 반환하도록 설정 (특정 ID 논문 없음)
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        
        # query로 테스트 (이 경우 mock_db_session.query().filter().limit().all()이 호출됨)
        response = self.app.post('/generate_shorts', json={"query": "테스트 쿼리", "limit": 1})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("shorts_with_videos", data)
        self.assertEqual(len(data["shorts_with_videos"]), 1) # 여전히 mock_db_session.query().all()에서 반환된 모킹된 논문 1개
        mock_requests_post.assert_called_once()
        print("test_generate_shorts_endpoint_success 통과")


    @patch('deepsearch.backend.app.next')
    @patch('deepsearch.backend.app.get_db')
    @patch('deepsearch.backend.app.generate_paper_shorts')
    @patch('deepsearch.backend.app.requests.post')
    def test_generate_shorts_endpoint_shortgpt_connection_error(self, mock_requests_post, mock_generate_paper_shorts, mock_get_db, mock_next):
        """
        ShortGPT 서버 연결 오류 발생 시 /generate_shorts 엔드포인트의 동작 테스트
        """
        mock_db_session = MagicMock()
        mock_get_db.return_value = iter([mock_db_session])
        mock_next.return_value = mock_db_session

        mock_paper = MagicMock(spec=Paper)
        mock_paper.paper_id = "test_paper_conn_error"
        mock_paper.title = "연결 오류 테스트"
        mock_paper.abstract = "연결 오류 테스트를 위한 초록."
        mock_paper.published_date = "2023-01-01"

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_paper
        mock_db_session.query.return_value.order_by.return_value.desc.return_value.limit.return_value.all.return_value = [mock_paper]


        mock_generate_paper_shorts.return_value = "LM Studio 짧은 요약."
        mock_requests_post.side_effect = requests.exceptions.ConnectionError("모의 연결 오류")

        response = self.app.post('/generate_shorts', json={"paper_id": "test_paper_conn_error"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIn("shorts_with_videos", data)
        self.assertEqual(len(data["shorts_with_videos"]), 1)
        self.assertIn("ShortGPT Connection Error", data["shorts_with_videos"][0]["video_status"])
        self.assertIsNone(data["shorts_with_videos"][0]["video_id"])
        print("test_generate_shorts_endpoint_shortgpt_connection_error 통과")

    @patch('deepsearch.backend.app.next')
    @patch('deepsearch.backend.app.get_db')
    @patch('deepsearch.backend.app.generate_paper_shorts')
    @patch('deepsearch.backend.app.requests.post')
    def test_generate_shorts_endpoint_shortgpt_http_error(self, mock_requests_post, mock_generate_paper_shorts, mock_get_db, mock_next):
        """
        ShortGPT API에서 HTTP 오류 (예: 500) 발생 시 /generate_shorts 엔드포인트의 동작 테스트
        """
        mock_db_session = MagicMock()
        mock_get_db.return_value = iter([mock_db_session])
        mock_next.return_value = mock_db_session

        mock_paper = MagicMock(spec=Paper)
        mock_paper.paper_id = "test_paper_http_error"
        mock_paper.title = "HTTP 오류 테스트"
        mock_paper.abstract = "HTTP 오류 테스트를 위한 초록."
        mock_paper.published_date = "2023-01-01"

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_paper
        mock_db_session.query.return_value.order_by.return_value.desc.return_value.limit.return_value.all.return_value = [mock_paper]

        mock_generate_paper_shorts.return_value = "LM Studio 짧은 요약."
        
        mock_shortgpt_response = MagicMock()
        mock_shortgpt_response.status_code = 500
        mock_shortgpt_response.text = "Internal Server Error"
        mock_shortgpt_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_shortgpt_response)
        mock_requests_post.return_value = mock_shortgpt_response

        response = self.app.post('/generate_shorts', json={"paper_id": "test_paper_http_error"})
        self.assertEqual(response.status_code, 200) # 오류 상태가 응답 본문에 포함되므로 200
        data = response.get_json()
        self.assertIn("shorts_with_videos", data)
        self.assertEqual(len(data["shorts_with_videos"]), 1)
        self.assertIn("ShortGPT API Error", data["shorts_with_videos"][0]["video_status"])
        self.assertIsNone(data["shorts_with_videos"][0]["video_id"])
        print("test_generate_shorts_endpoint_shortgpt_http_error 통과")

    @patch('deepsearch.backend.app.next')
    @patch('deepsearch.backend.app.get_db')
    @patch('deepsearch.backend.app.generate_paper_shorts')
    @patch('deepsearch.backend.app.requests.post')
    def test_generate_shorts_endpoint_no_papers_found(self, mock_requests_post, mock_generate_paper_shorts, mock_get_db, mock_next):
        """
        데이터베이스에서 논문을 찾지 못했을 때 /generate_shorts 엔드포인트의 동작 테스트
        """
        mock_db_session = MagicMock()
        mock_get_db.return_value = iter([mock_db_session])
        mock_next.return_value = mock_db_session

        mock_db_session.query.return_value.filter.return_value.first.return_value = None # ID로 논문 없음
        mock_db_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [] # 쿼리로 논문 없음
        mock_db_session.query.return_value.order_by.return_value.desc.return_value.limit.return_value.all.return_value = [] # 최근 논문 없음

        response = self.app.post('/generate_shorts', json={"paper_id": "존재하지_않는_논문"})
        self.assertEqual(response.status_code, 404) # 특정 ID 논문 찾을 수 없음
        data = response.get_json()
        self.assertEqual(data["error"], "Paper with ID 존재하지_않는_논문 not found")
        
        # 논문이 없는 쿼리로 테스트
        response = self.app.post('/generate_shorts', json={"query": "존재하지 않는 쿼리"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["message"], "쇼츠를 생성할 논문이 없습니다.")
        self.assertNotIn("shorts_with_videos", data)
        
        # 논문이 없는 기본 요청으로 테스트
        response = self.app.post('/generate_shorts', json={})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["message"], "쇼츠를 생성할 논문이 없습니다.")
        self.assertNotIn("shorts_with_videos", data)
        
        print("test_generate_shorts_endpoint_no_papers_found 통과")

    @patch('deepsearch.backend.app.client') # LM Studio 클라이언트 모킹
    def test_generate_video_script_and_scenes_success(self, mock_client):
        logger.debug("test_generate_video_script_and_scenes_success 시작")
        mock_choice = MagicMock()
        mock_choice.message.content = json.dumps({
            "script": "테스트 대본입니다. 논문 내용은 매우 흥미롭습니다.",
            "scenes": [
                {"text": "첫 번째 장면 대사", "image_search_term": "과학 기술"},
                {"text": "두 번째 장면 대사", "image_search_term": "연구 결과"}
            ]
        })
        mock_client.chat.completions.create.return_value.choices = [mock_choice]

        test_abstract = "이것은 테스트 논문의 초록입니다. AI와 머신러닝에 대한 새로운 접근 방식을 다룹니다."
        result = generate_video_script_and_scenes(test_abstract)

        self.assertIn("script", result)
        self.assertIn("scenes", result)
        self.assertEqual(result["script"], "테스트 대본입니다. 논문 내용은 매우 흥미롭습니다.")
        self.assertEqual(len(result["scenes"]), 2)
        self.assertEqual(result["scenes"][0]["text"], "첫 번째 장면 대사")
        self.assertEqual(result["scenes"][0]["image_search_term"], "과학 기술")
        logger.debug("test_generate_video_script_and_scenes_success 종료")

    @patch('deepsearch.backend.app.client')
    def test_generate_video_script_and_scenes_empty_abstract(self, mock_client):
        logger.debug("test_generate_video_script_and_scenes_empty_abstract 시작")
        result = generate_video_script_and_scenes("")
        self.assertEqual(result["script"], "초록 없음.")
        self.assertEqual(result["scenes"], [])
        mock_client.chat.completions.create.assert_not_called() # 초록이 비면 LM Studio 호출 안함
        logger.debug("test_generate_video_script_and_scenes_empty_abstract 종료")

    def test_text_to_speech_conceptual(self):
        logger.debug("test_text_to_speech_conceptual 시작")
        test_text = "안녕하세요, 이것은 테스트 음성입니다."
        test_output_path = "test_audio.mp3"
        result = text_to_speech_conceptual(test_text, test_output_path)
        self.assertEqual(result, test_output_path)
        # 실제 파일 생성 여부는 여기서 확인하지 않음 (개념 함수이므로)
        logger.debug("test_text_to_speech_conceptual 종료")

    def test_assemble_video_conceptual(self):
        logger.debug("test_assemble_video_conceptual 시작")
        test_scenes = [
            {"scene_number": 0, "text": "장면1", "audio_path": "audio1.mp3", "image_path_conceptual": "img1.jpg"},
            {"scene_number": 1, "text": "장면2", "audio_path": "audio2.mp3", "image_path_conceptual": "img2.jpg"}
        ]
        test_output_video_path = "test_video.mp4"
        result = assemble_video_conceptual(test_scenes, test_output_video_path)
        self.assertEqual(result, test_output_video_path)
        # 실제 파일 생성 여부는 여기서 확인하지 않음 (개념 함수이므로)
        logger.debug("test_assemble_video_conceptual 종료")

    @patch('deepsearch.backend.app.get_db')
    @patch('deepsearch.backend.app.generate_video_script_and_scenes')
    @patch('deepsearch.backend.app.text_to_speech_conceptual')
    @patch('deepsearch.backend.app.assemble_video_conceptual')
    def test_generate_full_video_shorts_success(self, mock_assemble, mock_tts, mock_script_scenes, mock_get_db):
        logger.debug("test_generate_full_video_shorts_success 시작")
        # Mock Paper object
        mock_paper = MagicMock()
        mock_paper.paper_id = "test_paper_123"
        mock_paper.title = "Test Paper Title"
        mock_paper.abstract = "Test Abstract Content."
        mock_paper.published_date = "2023-01-01"

        # Mock DB session
        mock_db_session = MagicMock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_paper
        mock_db_session.query.return_value.order_by.return_value.first.return_value = mock_paper
        mock_get_db.return_value.__next__.return_value = mock_db_session

        # Mock script and scenes generation
        mock_script_scenes.return_value = {
            "script": "Generated video script.",
            "scenes": [
                {"text": "Scene 1 dialog.", "image_search_term": "research"},
                {"text": "Scene 2 dialog.", "image_search_term": "innovations"}
            ]
        }

        # Mock TTS and video assembly
        mock_tts.side_effect = lambda text, path: f"mock_audio_{text}.mp3"
        mock_assemble.return_value = "mock_final_video.mp4"

        response = self.app.post('/generate_full_video_shorts', json={'paper_id': 'test_paper_123'})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertEqual(data['paper_id'], 'test_paper_123')
        self.assertEqual(data['generated_script'], 'Generated video script.')
        self.assertIn('final_video_path', data)
        self.assertIn('processed_scenes', data)
        self.assertEqual(data['final_video_path'], 'mock_final_video.mp4')
        self.assertEqual(len(data['processed_scenes']), 2)
        self.assertIn('audio_path', data['processed_scenes'][0])
        self.assertIn('image_path_conceptual', data['processed_scenes'][0])

        mock_script_scenes.assert_called_once_with(mock_paper.abstract)
        self.assertEqual(mock_tts.call_count, 2) # Two scenes, so TTS called twice
        mock_assemble.assert_called_once() # Video assembly called once
        logger.debug("test_generate_full_video_shorts_success 종료")

    @patch('deepsearch.backend.app.get_db')
    def test_generate_full_video_shorts_no_paper_found(self, mock_get_db):
        logger.debug("test_generate_full_video_shorts_no_paper_found 시작")
        mock_db_session = MagicMock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = None
        mock_db_session.query.return_value.order_by.return_value.first.return_value = None
        mock_get_db.return_value.__next__.return_value = mock_db_session

        response = self.app.post('/generate_full_video_shorts', json={'paper_id': 'non_existent_paper'})
        self.assertEqual(response.status_code, 404)
        data = json.loads(response.data)
        self.assertIn('error', data)
        logger.debug("test_generate_full_video_shorts_no_paper_found 종료")

    @patch('deepsearch.backend.app.get_db')
    @patch('deepsearch.backend.app.generate_video_script_and_scenes')
    def test_generate_full_video_shorts_script_generation_failure(self, mock_script_scenes, mock_get_db):
        logger.debug("test_generate_full_video_shorts_script_generation_failure 시작")
        mock_paper = MagicMock()
        mock_paper.paper_id = "test_paper_fail"
        mock_paper.abstract = "Abstract for failure test."

        mock_db_session = MagicMock()
        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_paper
        mock_get_db.return_value.__next__.return_value = mock_db_session

        # Simulate script generation returning no scenes
        mock_script_scenes.return_value = {"script": "Failed script.", "scenes": []}

        response = self.app.post('/generate_full_video_shorts', json={'paper_id': 'test_paper_fail'})
        self.assertEqual(response.status_code, 500)
        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertEqual(data['error'], 'Failed to generate video script and scenes.')
        logger.debug("test_generate_full_video_shorts_script_generation_failure 종료")


if __name__ == '__main__':
    unittest.main() 