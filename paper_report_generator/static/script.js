document.addEventListener('DOMContentLoaded', function() {
    const reportForm = document.getElementById('reportForm');
    const messageDiv = document.getElementById('message');
    const pdfViewerDiv = document.getElementById('pdfViewer');

    reportForm.addEventListener('submit', async function(event) {
        event.preventDefault(); // 기본 폼 제출 방지

        messageDiv.textContent = '보고서를 생성 중입니다... 잠시 기다려 주세요.';
        messageDiv.style.color = 'blue';
        pdfViewerDiv.innerHTML = ''; // 이전 PDF 뷰어 초기화

        const formData = new FormData(reportForm);

        try {
            const response = await fetch('/generate_report', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok) {
                if (result.pdf_url) {
                    messageDiv.textContent = '보고서가 성공적으로 생성되었습니다.';
                    messageDiv.style.color = 'green';
                    pdfViewerDiv.innerHTML = `<iframe src="${result.pdf_url}" width="100%" height="600px"></iframe>`;
                } else {
                    messageDiv.textContent = result.message || 'PDF URL을 찾을 수 없습니다.';
                    messageDiv.style.color = 'orange';
                }
            } else {
                messageDiv.textContent = result.error || '보고서 생성에 실패했습니다.';
                messageDiv.style.color = 'red';
            }
        } catch (error) {
            console.error('Error:', error);
            messageDiv.textContent = `오류 발생: ${error.message}`;
            messageDiv.style.color = 'red';
        }
    });
}); 