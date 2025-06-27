# 딥 리서치 에이전트 (LM Studio, CrewAI 기반)

이 프로젝트는 프론티어 LLM의 '딥 리서치' 기능을 개인 PC 환경(LM Studio, 16GB RAM)에서 구현하는 가이드와 실제 동작하는 애플리케이션 코드를 제공합니다. LM Studio의 로컬 LLM 서버와 CrewAI 프레임워크를 활용하여 복잡한 질문에 대한 심층적인 정보를 검색하고 분석하는 에이전트를 구축합니다.

## 🚀 프로젝트 구조

```
deepsearch/
├── backend/               # Flask 기반 백엔드 (CrewAI 에이전트 실행)
│   ├── app.py             # 메인 Flask 애플리케이션 및 딥 리서치 API 엔드포인트
│   ├── requirements.txt   # Python 의존성 목록
│   └── .env               # 환경 변수 (Tavily API 키, LM Studio 설정)
└── frontend/              # HTML, CSS, JavaScript 기반 프론트엔드
    ├── index.html         # 사용자 인터페이스 (주제 입력 및 결과 표시)
    ├── style.css          # UI 스타일 시트
    └── script.js          # 프론트엔드 로직 (API 호출 및 UI 업데이트)
```

## 📋 필요 구성 요소

*   **하드웨어**: 16GB RAM 이상의 PC
*   **소프트웨어**:
    *   **LM Studio**: 로컬 LLM 구동 환경 ([다운로드 링크](https://lmstudio.ai/))
    *   **Python 3.8+**: 백엔드 실행을 위한 프로그래밍 언어
    *   **Node.js (선택 사항)**: 프론트엔드 개발 시 필요할 수 있으나, 이 프로젝트에서는 직접 실행 가능합니다.
*   **API 키**:
    *   **Tavily AI**: LLM 에이전트 전용 검색 API ([API 키 발급 링크](https://tavily.com/)). 무료 플랜으로도 충분히 테스트 가능합니다.

*   **추천 모델 (7B/8B)**:
    *   `katanemo/Arch-Function-7B-GGUF` 또는 `TheBloke/Mistral-7B-Instruct-v0.2-GGUF` 등 CrewAI와 호환되는 7B/8B GGUF 모델

## 📝 설정 및 실행 가이드

### STEP 1: LM Studio에 추천 모델 설치 및 서버 실행

1.  **LM Studio 실행**: 애플리케이션을 실행합니다.
2.  **모델 검색**: 상단의 검색 아이콘(🔍)을 클릭하고, 추천 모델(`katanemo/Arch-Function-7B-GGUF` 또는 `TheBloke/Mistral-7B-Instruct-v0.2-GGUF`)을 검색합니다.
3.  **모델 다운로드**: 검색 결과에서 해당 모델을 찾아 오른쪽에 있는 `Download` 버튼을 클릭합니다. (Q4_K_M 또는 Q5_K_M 같이 성능과 용량의 균형이 맞는 파일을 추천합니다.)
4.  **모델 로드**: 왼쪽의 대화 아이콘(💬)을 클릭하고, 상단에서 다운로드한 모델을 선택하여 로드합니다. 모델이 성공적으로 로드되면 "Model is ready" 메시지를 확인할 수 있습니다.
5.  **로컬 서버 실행**: 왼쪽의 양방향 화살표 아이콘(↔️)을 클릭하여 'Local Server' 탭으로 이동한 후 `Start Server` 버튼을 누릅니다. 이제 `http://localhost:1234/v1` 주소에서 OpenAI와 호환되는 API 서버가 실행됩니다.

### STEP 2: Tavily 검색 API 키 발급

1.  [Tavily AI 웹사이트](https://tavily.com/)에 접속하여 회원가입/로그인합니다.
2.  대시보드에서 API 키를 복사하여 안전한 곳에 보관합니다.

### STEP 3: 백엔드 설정

1.  **`.env` 파일 생성 (수동)**: `deepsearch/backend/` 폴더에 `.env` 파일을 생성하고 다음 내용을 붙여넣으세요. `TAVILY_API_KEY`에는 발급받은 Tavily API 키를 입력합니다.

    ```dotenv
    # Tavily API 키를 여기에 붙여넣으세요
    TAVILY_API_KEY="tvly-YOUR_TAVILY_API_KEY_HERE"

    # CrewAI가 LM Studio 서버를 사용하도록 설정합니다
    OPENAI_API_BASE='http://localhost:1234/v1'
    OPENAI_MODEL_NAME='TheBloke/Mistral-7B-Instruct-v0.2-GGUF' # LM Studio에서 사용하는 모델 이름과 일치시키세요.
    OPENAI_API_KEY='not-needed' # LM Studio는 API 키가 필요 없습니다.
    ```

2.  **Python 의존성 설치**: 터미널을 열고 `deepsearch/backend/` 디렉토리로 이동한 후 다음 명령어를 실행하여 필요한 라이브러리를 설치합니다.

    ```bash
    pip install -r requirements.txt
    ```

3.  **백엔드 서버 실행**: 같은 터미널에서 다음 명령어를 실행하여 Flask 백엔드 서버를 시작합니다.

    ```bash
    python app.py
    ```

    서버가 성공적으로 시작되면 `http://127.0.0.1:5000/`에서 실행 중이라는 메시지를 확인할 수 있습니다. (`debug=True`로 설정되어 있습니다.)

### STEP 4: 프론트엔드 실행

프론트엔드는 별도의 서버 실행 없이 웹 브라우저에서 직접 `index.html` 파일을 열어 실행할 수 있습니다.

1.  파일 탐색기에서 `deepsearch/frontend/` 디렉토리로 이동합니다.
2.  `index.html` 파일을 웹 브라우저(Chrome, Firefox 등)로 엽니다. (파일을 더블 클릭하거나, 브라우저에 `file:///path/to/your/project/deepsearch/frontend/index.html` 형식으로 경로를 입력하여 접근할 수 있습니다.)

## 🧪 사용 방법

1.  LM Studio 로컬 서버가 실행 중인지 확인합니다.
2.  백엔드 Flask 서버(`app.py`)가 실행 중인지 확인합니다.
3.  웹 브라우저에서 `index.html`을 엽니다.
4.  텍스트 입력 필드에 리서치하고 싶은 주제를 입력합니다. (예: `2024년 2분기 반도체 시장 동향과 주요 기업들의 실적을 비교 분석해줘`)
5.  `리서치 시작` 버튼을 클릭합니다.
6.  '리서치 중입니다...' 메시지와 함께 로딩 스피너가 표시되고, 백엔드에서 CrewAI 에이전트가 동작하여 웹 검색 및 분석을 수행합니다.
7.  리서치가 완료되면, `리서치 결과:` 섹션에 마크다운 형식의 상세한 보고서가 표시됩니다.

## ✅ 테스트 방법

본 프로젝트는 구현된 논문 쇼츠 생성 파이프라인의 핵심 로직을 검증하기 위한 단위 및 통합 테스트 코드를 포함하고 있습니다. 이 테스트들은 외부 서비스(LM Studio, 데이터베이스, TTS/비디오 라이브러리)를 모킹(mocking)하여 실제 환경 없이도 실행할 수 있습니다.

1.  **테스트 실행:**
    *   터미널을 열고 `deepsearch/backend/` 디렉토리로 이동합니다.
    *   다음 명령어를 실행하여 테스트를 수행합니다:
        ```bash
        python -m unittest test_app.py
        ```
    *   (선택 사항) `pytest`가 설치되어 있다면 (더 상세한 결과 확인 가능):
        ```bash
        pytest test_app.py
        ```
2.  **테스트 결과 확인:**
    *   모든 테스트 케이스가 성공적으로 통과(`OK` 메시지)되어야 합니다.

## 🚀 실제 동영상 쇼츠 생성 환경 구축 (선택 사항)

실제 동영상 쇼츠 파일(`mp3`, `mp4`)을 생성하고 싶다면, 다음 추가 단계를 수행해야 합니다. 현재 구현된 코드의 TTS 및 동영상 조합 부분은 개념적인 플레이스홀더 함수입니다.

1.  **LM Studio 서버 실행 확인:**
    *   LM Studio 애플리케이션이 실행 중이고, `http://127.0.0.1:1234`에서 `lgai-exaone.exaone-3.5-7.8b-instruct` (또는 `.env`에 설정된 모델) 모델이 로드되어 있는지 확인합니다.

2.  **환경 변수 설정:**
    *   프로젝트 루트(`.env` 파일)에 다음 환경 변수들이 정확하게 설정되어 있는지 확인합니다:
        ```dotenv
        OPENAI_API_BASE=http://127.0.0.1:1234/v1
        OPENAI_MODEL_NAME=lgai-exaone.exaone-3.5-7.8b-instruct # LM Studio에 로드된 모델 이름과 일치
        OPENAI_API_KEY=not-needed
        # ShortGPT를 연동했다면 (이전 구현), ShortGPT API BASE도 설정
        # SHORTGPT_API_BASE=http://localhost:31415/api
        ```

3.  **TTS 및 동영상 편집 라이브러리 설치:**
    *   `deepsearch/backend/requirements.txt` 파일에 다음 라이브러리를 추가하고 설치합니다:
        ```
        # deepsearch/backend/requirements.txt
        # ... 기존 라이브러리 ...
        gTTS
        moviepy
        ```
    *   `deepsearch/backend/` 디렉토리에서 다음 명령어로 설치합니다:
        ```bash
        pip install -r requirements.txt
        ```

4.  **FFmpeg 설치:**
    *   `moviepy`가 동영상 처리를 위해 `FFmpeg`을 사용하므로, 시스템에 `FFmpeg`을 설치하고 PATH 환경 변수에 추가해야 합니다. ([FFmpeg 공식 웹사이트](https://ffmpeg.org/download.html) 참조).

5.  **개념적 함수 실제 구현으로 대체:**
    *   `deepsearch/backend/app.py` 파일 내의 `text_to_speech_conceptual` 및 `assemble_video_conceptual` 함수 내부의 주석 처리된 `gTTS` 및 `moviepy` 관련 코드를 활성화하고 필요한 실제 구현으로 변경합니다.

6.  **Flask 애플리케이션 실행:**
    *   `deepsearch/backend/` 디렉토리에서 다음 명령어로 Flask 서버를 시작합니다:
        ```bash
        python app.py
        ```

7.  **API 엔드포인트 호출:**
    *   Postman, `curl` 등의 도구를 사용하여 `/generate_full_video_shorts` 엔드포인트에 POST 요청을 보냅니다. 예를 들어:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{ "paper_id": "your_paper_id_here" }' http://localhost:5000/generate_full_video_shorts
        ```
        또는 최신 논문에 대해 생성하려면:
        ```bash
        curl -X POST -H "Content-Type: application/json" -d '{}' http://localhost:5000/generate_full_video_shorts
        ```
    *   요청이 성공하면, `generated_videos/` 및 `generated_audio/` 디렉토리 아래에 실제 동영상 및 오디오 파일이 생성될 것입니다.

## 🛠️ 개발 고려사항 및 확장

*   **GGUF 모델 사용**: 16GB RAM 환경에서는 CPU와 RAM만으로 LLM을 효율적으로 실행할 수 있는 GGUF 모델 형식이 필수적입니다.
*   **모델 양자화 수준**: 모델 다운로드 시 Q4_K_M 또는 Q5_K_M과 같이 성능과 용량의 균형이 맞는 양자화 수준을 선택하는 것이 좋습니다.
*   **메모리 오프로드**: LM Studio의 모델 설정에서 'GPU Offload' 옵션을 조절하여 VRAM이 있는 경우 일부 레이어를 GPU로 오프로드하여 RAM 사용량을 줄이고 속도를 높일 수 있습니다.
*   **확장성**: CrewAI 외에 LangChain을 사용해서도 유사한 에이전트를 구축할 수 있으며, 검색 도구 외에도 계산기, 파일 읽기/쓰기 등 다양한 도구를 추가하여 에이전트의 능력을 확장할 수 있습니다.
*   **CORS**: 백엔드와 프론트엔드가 다른 포트에서 실행되므로 (기본적으로 Flask는 5000, 프론트엔드는 file://), 실제 배포 환경에서는 CORS (Cross-Origin Resource Sharing) 설정이 필요할 수 있습니다. 개발 환경에서는 브라우저 보안 정책에 따라 문제가 발생할 수 있지만, 일반적으로 `file://` 프로토콜에서는 크게 문제되지 않습니다. 만약 문제가 발생하면 Flask 앱에 `flask_cors` 라이브러리를 추가하여 CORS를 허용해야 합니다. (예: `pip install Flask-Cors` 후 `CORS(app)`) 