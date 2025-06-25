## 딥 리서치 에이전트 API 명세서

이 문서는 딥 리서치 에이전트 백엔드 API (`deepsearch/backend/app.py`)의 명세를 정의합니다. 이 API는 Flask 서버에서 호스팅되며, CrewAI 에이전트를 활용하여 주어진 주제에 대한 심층적인 웹 리서치를 수행합니다.

### 1. 기본 정보

*   **기본 URL**: `http://localhost:5000`
*   **인증**: 필요 없음 (개발 환경 기준)
*   **콘텐츠 타입**: `application/json` (요청 및 응답)

### 2. 엔드포인트: `/deep_research`

주어진 주제에 대해 딥 리서치를 수행하고, 마크다운 형식의 보고서를 반환합니다.

*   **URL**: `/deep_research`
*   **메서드**: `POST`

#### 2.1. 요청 (Request)

*   **헤더**:
    *   `Content-Type: application/json`
*   **바디 (JSON)**:
    `topic` 필드는 리서치할 주제를 포함하는 문자열입니다.

    ```json
    {
      "topic": "인공지능 칩 시장의 최신 동향"
    }
    ```

    *   **필드 설명**:
        *   `topic` (string, **필수**): 딥 리서치를 수행할 주제. 복잡하고 상세한 질문일수록 에이전트가 더 깊이 있는 리서치 계획을 수립할 수 있습니다.

#### 2.2. 응답 (Response)

*   **성공 (200 OK)**:
    리서치가 성공적으로 완료되면, 마크다운 형식의 리서치 보고서를 포함하는 JSON 객체를 반환합니다.

    *   **바디 (JSON)**:

        ```json
        {
          "result": "## 인공지능 칩 시장의 최신 동향\n\n### 1. 개요\n2024년 2분기 현재, 인공지능(AI) 칩 시장은...\n\n### 2. 주요 기업별 동향\n#### NVIDIA\nNVIDIA는 AI 칩 시장에서 압도적인 선두를 달리고 있으며...\n\n#### AMD\nAMD는 MI300X 시리즈를 통해 AI 가속기 시장에서...\n
#### Intel\nIntel은 가우디(Gaudi) 시리즈와 신경망 처리 장치(NPU)를 통해...\n\n### 3. 비교 분석\n...\n\n### 4. 미래 전망\n..."
        }
        ```

    *   **필드 설명**:
        *   `result` (string): 요청된 주제에 대한 심층 리서치 결과가 포함된 마크다운 형식의 보고서입니다.

*   **오류 (400 Bad Request)**:
    요청 바디에 `topic`이 누락되었거나 유효하지 않은 경우.

    *   **바디 (JSON)**:

        ```json
        {
          "error": "No topic provided"
        }
        ```

*   **서버 오류 (500 Internal Server Error)**:
    백엔드 처리 중 예기치 않은 오류가 발생한 경우.

    *   **바디 (JSON)**:

        ```json
        {
          "error": "deep_research 처리 중 오류 발생"
        }
        ```
        또는
        ```json
        {
          "error": "TAVILY_API_KEY가 설정되지 않았거나 기본값입니다. .env 파일을 확인해주세요."
        }
        ```
        (Tavily API 키 문제의 경우)

--- 