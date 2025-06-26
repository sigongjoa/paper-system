// script.js

document.addEventListener('DOMContentLoaded', () => {
    console.debug("DOM Content Loaded");

    const initStartDateInput = document.getElementById('initStartDate');
    const initEndDateInput = document.getElementById('initEndDate');
    const initializeRangeButton = document.getElementById('initializeRangeButton');
    
    const addStartDateInput = document.getElementById('addStartDate');
    const addEndDateInput = document.getElementById('addEndDate');
    const addRangeButton = document.getElementById('addRangeButton');
    
    const maxPapersInput = document.getElementById('maxPapers');
    const messageDiv = document.getElementById('message');
    const clearDisplayButton = document.getElementById('clearDisplayButton');
    const paperListDiv = document.querySelector('.paper-list');

    // 오늘 날짜로 기본값 설정
    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0'); // Months are 0-indexed
    const dd = String(today.getDate()).padStart(2, '0');
    const formattedToday = `${yyyy}-${mm}-${dd}`;

    initStartDateInput.value = formattedToday;
    initEndDateInput.value = formattedToday;
    addStartDateInput.value = formattedToday;
    addEndDateInput.value = formattedToday;

    function showMessage(msg, type) {
        console.debug(`Showing message: ${msg} with type ${type}`);
        messageDiv.textContent = msg;
        messageDiv.className = `message ${type}`;
        messageDiv.style.display = 'block';
        setTimeout(() => {
            messageDiv.style.display = 'none';
            messageDiv.textContent = '';
        }, 3000);
        console.debug("Message display set.");
    }

    async function sendCrawlRequest(startDate, endDate, isInitialCrawl) {
        if (!startDate || !endDate) {
            showMessage('시작 날짜와 종료 날짜를 모두 선택해주세요.', 'error');
            return;
        }

        messageDiv.textContent = isInitialCrawl ?
                                 `선택된 날짜 범위 (${startDate} ~ ${endDate}) 데이터로 초기화 중...` :
                                 `선택된 날짜 범위 (${startDate} ~ ${endDate}) 데이터 추가 크롤링 중...`;
        messageDiv.className = 'message';
        messageDiv.style.display = 'block';

        try {
            const response = await fetch('/crawl', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    start_date: startDate,
                    end_date: endDate,
                    is_initial_crawl: isInitialCrawl,
                    max_papers: parseInt(maxPapersInput.value)
                }),
            });
            console.debug(`Fetch request sent: start=${startDate}, end=${endDate}, initial=${isInitialCrawl}`);

            const data = await response.json();
            console.debug("Response received:", data);

            if (data.status === 'success') {
                showMessage(data.message, 'success');
                setTimeout(() => {
                    window.location.reload();
                    console.debug("Page reloaded after successful crawl.");
                }, 1000);
            } else {
                showMessage(data.message, 'error');
            }
        } catch (error) {
            console.error("Error during crawl request:", error);
            showMessage('크롤링 중 오류가 발생했습니다.', 'error');
        }
        console.debug("Crawl request handler finished.");
    }

    if (initializeRangeButton) {
        initializeRangeButton.addEventListener('click', () => {
            const startDate = initStartDateInput.value;
            const endDate = initEndDateInput.value;
            sendCrawlRequest(startDate, endDate, true);
        });
    }

    if (addRangeButton) {
        addRangeButton.addEventListener('click', () => {
            const startDate = addStartDateInput.value;
            const endDate = addEndDateInput.value;
            sendCrawlRequest(startDate, endDate, false);
        });
    }

    if (clearDisplayButton) {
        clearDisplayButton.addEventListener('click', () => {
            console.debug("Clear Display button clicked.");
            if (paperListDiv) {
                paperListDiv.innerHTML = '<p>화면의 논문 목록이 초기화되었습니다.</p>';
                console.debug("Paper list cleared.");
            }
        });
    }

    console.debug("DOM Content Loaded event listener finished.");
}); 