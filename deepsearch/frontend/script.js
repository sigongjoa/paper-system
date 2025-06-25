document.addEventListener('DOMContentLoaded', () => {
    console.debug("DOM Content Loaded");

    const topicInput = document.getElementById('topicInput');
    const researchButton = document.getElementById('researchButton');
    const researchResult = document.getElementById('researchResult');
    const loadingIndicator = document.getElementById('loadingIndicator');

    const crawlQueryInput = document.getElementById('crawlQueryInput');
    const crawlPlatformsSelect = document.getElementById('crawlPlatformsSelect');
    const crawlMaxResultsInput = document.getElementById('crawlMaxResultsInput');
    const crawlStartDateInput = document.getElementById('crawlStartDateInput');
    const crawlEndDateInput = document.getElementById('crawlEndDateInput');
    const crawlButton = document.getElementById('crawlButton');
    const crawlLoadingIndicator = document.getElementById('crawlLoadingIndicator');
    const crawlResult = document.getElementById('crawlResult');

    researchButton.addEventListener('click', async () => {
        console.debug("리서치 버튼 클릭됨");
        const topic = topicInput.value.trim();
        if (!topic) {
            alert('리서치할 주제를 입력해주세요.');
            console.debug("주제 입력 안 됨");
            return;
        }

        researchResult.textContent = ''; // 이전 결과 지우기
        loadingIndicator.classList.remove('hidden'); // 로딩 인디케이터 표시
        researchButton.disabled = true; // 버튼 비활성화
        topicInput.disabled = true; // 입력창 비활성화
        console.debug("리서치 시작: 로딩 표시 및 UI 비활성화");

        try {
            const response = await fetch('http://localhost:5000/deep_research', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ topic: topic }),
            });
            console.debug("Fetch 요청 완료");

            const data = await response.json();
            console.debug("JSON 응답 파싱 완료");

            if (response.ok) {
                researchResult.textContent = data.result;
                console.debug("리서치 결과 표시 완료");
            } else {
                researchResult.textContent = `오류: ${data.error || '알 수 없는 오류'}`;
                console.error("API 오류 발생:", data.error);
            }
        } catch (error) {
            researchResult.textContent = `네트워크 오류: ${error.message}`;
            console.error("네트워크 오류 발생:", error);
        } finally {
            loadingIndicator.classList.add('hidden'); // 로딩 인디케이터 숨기기
            researchButton.disabled = false; // 버튼 활성화
            topicInput.disabled = false; // 입력창 활성화
            console.debug("리서치 종료: 로딩 숨김 및 UI 활성화");
        }
    });

    crawlButton.addEventListener('click', async () => {
        console.debug("크롤링 버튼 클릭됨");
        const query = crawlQueryInput.value.trim();
        const selectedPlatforms = Array.from(crawlPlatformsSelect.selectedOptions).map(option => option.value);
        const maxResults = parseInt(crawlMaxResultsInput.value, 10);
        const startDate = crawlStartDateInput.value; // YYYY-MM-DD
        const endDate = crawlEndDateInput.value;     // YYYY-MM-DD

        if (!query && selectedPlatforms.length === 0) {
            alert('크롤링할 키워드 또는 플랫폼을 하나 이상 선택해주세요.');
            console.debug("키워드 또는 플랫폼 입력 안 됨");
            return;
        }

        crawlResult.textContent = '';
        crawlLoadingIndicator.classList.remove('hidden');
        crawlButton.disabled = true;
        crawlQueryInput.disabled = true;
        crawlPlatformsSelect.disabled = true;
        crawlMaxResultsInput.disabled = true;
        crawlStartDateInput.disabled = true;
        crawlEndDateInput.disabled = true;
        console.debug("크롤링 시작: 로딩 표시 및 UI 비활성화");

        try {
            const response = await fetch('http://localhost:5000/crawl_papers', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    platforms: selectedPlatforms.length > 0 ? selectedPlatforms : null,
                    max_results: isNaN(maxResults) ? null : maxResults,
                    start_date: startDate || null,
                    end_date: endDate || null
                }),
            });
            console.debug("Fetch 요청 완료");

            const data = await response.json();
            console.debug("JSON 응답 파싱 완료");

            if (response.ok) {
                if (data.papers && data.papers.length > 0) {
                    const formattedPapers = data.papers.map(paper => {
                        return `[${paper.platform}] ${paper.title} (by ${paper.authors.join(', ')}) - ${paper.published_date.split('T')[0]}`;
                    }).join('\n');
                    crawlResult.textContent = formattedPapers;
                } else {
                    crawlResult.textContent = '크롤링된 논문이 없습니다.';
                }
                console.debug("크롤링 결과 표시 완료");
            } else {
                crawlResult.textContent = `오류: ${data.error || '알 수 없는 오류'}`;
                console.error("API 오류 발생:", data.error);
            }
        } catch (error) {
            crawlResult.textContent = `네트워크 오류: ${error.message}`;
            console.error("네트워크 오류 발생:", error);
        } finally {
            crawlLoadingIndicator.classList.add('hidden');
            crawlButton.disabled = false;
            crawlQueryInput.disabled = false;
            crawlPlatformsSelect.disabled = false;
            crawlMaxResultsInput.disabled = false;
            crawlStartDateInput.disabled = false;
            crawlEndDateInput.disabled = false;
            console.debug("크롤링 종료: 로딩 숨김 및 UI 활성화");
        }
    });
}); 