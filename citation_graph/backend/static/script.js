document.addEventListener('DOMContentLoaded', () => {
    console.debug("DOMContentLoaded 이벤트 발생");

    const paperIdInput = document.getElementById('paperIdInput');
    const depthInput = document.getElementById('depthInput');
    const fetchGraphBtn = document.getElementById('fetchGraphBtn');
    const networkDiv = document.getElementById('network');
    const paperDetailsDiv = document.getElementById('paperDetails');
    const closeDetailsBtn = document.getElementById('closeDetailsBtn');
    const detailTitle = document.getElementById('detailTitle');
    const detailAuthors = document.getElementById('detailAuthors');
    const detailYear = document.getElementById('detailYear');
    const detailAbstract = document.getElementById('detailAbstract');
    const detailPdfUrl = document.getElementById('detailPdfUrl');

    let network = null; // Vis.js network instance
    let nodes = new vis.DataSet();
    let edges = new vis.DataSet();

    // 그래프 생성 함수
    const fetchAndRenderGraph = async (paperId) => {
        console.debug(`fetchAndRenderGraph 함수 시작 - paperId: ${paperId}`);
        if (!paperId) {
            alert('논문 ID를 입력해주세요.');
            console.debug("논문 ID가 없어 함수 종료");
            return;
        }

        const depth = depthInput.value ? parseInt(depthInput.value, 10) : 1;
        if (isNaN(depth) || depth < 1) {
            alert('탐색 깊이는 1 이상의 유효한 숫자여야 합니다.');
            console.debug("유효하지 않은 깊이 값으로 함수 종료");
            return;
        }

        try {
            console.debug(`GET 요청: /api/graph/${paperId}?depth=${depth}`);
            const response = await fetch(`/api/graph/${paperId}?depth=${depth}`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || '그래프 데이터를 가져오는 데 실패했습니다.');
            }
            const graphData = await response.json();
            console.debug("그래프 데이터 수신 완료", graphData);

            nodes.clear();
            edges.clear();

            nodes.add(graphData.nodes.map(node => ({
                id: node.id,
                label: node.label,
                group: node.group,
                year: node.year,
                title: `<b>${node.label}</b><br>(${node.year})` // Tooltip
            })));
            edges.add(graphData.edges);

            const data = {
                nodes: nodes,
                edges: edges,
            };

            const options = {
                nodes: {
                    shape: 'dot',
                    size: 16,
                    font: { size: 12, color: '#333' },
                    borderWidth: 2,
                },
                edges: {
                    arrows: 'to',
                    color: { inherit: 'from' },
                    smooth: { type: 'continuous' },
                    font: { size: 10, align: 'middle' }
                },
                physics: { 
                    enabled: true,
                    barnesHut: {
                        gravitationalConstant: -2000,
                        centralGravity: 0.3,
                        springLength: 95,
                        springConstant: 0.04,
                        damping: 0.09,
                        avoidOverlap: 0
                    },
                    solver: 'barnesHut'
                },
                interaction: {
                    tooltipDelay: 300,
                    hideEdgesOnDrag: true,
                    navigationButtons: true,
                    keyboard: true
                }
            };

            if (network) {
                network.destroy();
                console.debug("기존 네트워크 인스턴스 파괴");
            }
            network = new vis.Network(networkDiv, data, options);
            console.debug("새로운 네트워크 인스턴스 생성 및 렌더링 완료");

            // 노드 클릭 이벤트
            network.on("click", (params) => {
                console.debug("네트워크 노드 클릭 이벤트 발생", params);
                if (params.nodes.length > 0) {
                    const clickedNodeId = params.nodes[0];
                    const clickedNode = nodes.get(clickedNodeId);
                    console.debug("클릭된 노드:", clickedNode);
                    
                    // 선택된 노드의 상세 정보를 가져오기 위해 백엔드 API 호출
                    fetch(`/api/graph/${clickedNode.id}`)
                        .then(response => response.json())
                        .then(data => {
                            console.debug("노드 상세 정보 수신 완료:", data.nodes[0]);
                            const paperData = data.nodes.find(node => node.id === clickedNode.id);
                            if (paperData) {
                                detailTitle.textContent = paperData.label;
                                detailAuthors.textContent = paperData.authors ? paperData.authors.join(', ') : 'N/A';
                                detailYear.textContent = paperData.year || 'N/A';
                                detailAbstract.textContent = paperData.abstract || '초록 없음';
                                if (paperData.pdf_url) {
                                    detailPdfUrl.href = paperData.pdf_url;
                                    detailPdfUrl.style.display = 'inline';
                                } else {
                                    detailPdfUrl.style.display = 'none';
                                }
                                paperDetailsDiv.classList.add('show');
                                console.debug("논문 상세 정보 표시 완료");
                            }
                        })
                        .catch(error => {
                            console.error("노드 상세 정보를 가져오는 중 오류 발생:", error);
                            alert('논문 상세 정보를 가져오는 데 실패했습니다.');
                        });
                } else {
                    paperDetailsDiv.classList.remove('show'); // 노드 선택 해제 시 상세 정보 숨기기
                    console.debug("노드 선택 해제, 상세 정보 숨김");
                }
            });

        } catch (error) {
            console.error("그래프 렌더링 중 오류 발생:", error);
            alert(`그래프를 가져오는 데 실패했습니다: ${error.message}`);
        }
        console.debug("fetchAndRenderGraph 함수 종료");
    };

    // 이벤트 리스너
    fetchGraphBtn.addEventListener('click', () => {
        console.debug("그래프 생성 버튼 클릭");
        const selectedPaperId = paperIdInput.value;
        fetchAndRenderGraph(selectedPaperId);
    });

    closeDetailsBtn.addEventListener('click', () => {
        console.debug("상세 정보 닫기 버튼 클릭");
        paperDetailsDiv.classList.remove('show');
    });

    console.debug("DOMContentLoaded 이벤트 핸들러 종료");
}); 