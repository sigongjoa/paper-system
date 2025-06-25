from flask import Flask, render_template, request, send_from_directory, jsonify
import os
import datetime
import logging

from generate_report import get_papers_by_date_and_category, generate_pdf_report, SessionLocal

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='templates', static_folder='static')

# PDF 파일이 저장될 디렉토리 (웹 서버에서 접근 가능해야 함)
PDF_REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'reports')
os.makedirs(PDF_REPORTS_DIR, exist_ok=True)

@app.route('/')
def index():
    logger.debug("Serving index.html")
    return render_template('index.html')

@app.route('/generate_report', methods=['POST'])
def generate_report_web():
    logger.debug("generate_report_web 함수 시작")
    report_date_str = request.form.get('report_date')
    top_n_str = request.form.get('top_n')

    if not report_date_str:
        logger.error("날짜가 제공되지 않았습니다.")
        return jsonify({"error": "날짜를 입력해주세요."}), 400

    try:
        report_date = datetime.datetime.strptime(report_date_str, "%Y-%m-%d").date()
    except ValueError:
        logger.error(f"잘못된 날짜 형식입니다: {report_date_str}")
        return jsonify({"error": "날짜 형식이 올바르지 않습니다 (YYYY-MM-DD)."}), 400

    top_n = int(top_n_str) if top_n_str and top_n_str.isdigit() else None

    output_filename = f"paper_report_{report_date.strftime('%Y%m%d')}"
    if top_n:
        output_filename += f"_top{top_n}"
    output_filename += ".pdf"

    pdf_filepath = os.path.join(PDF_REPORTS_DIR, output_filename)

    # TODO: generate_report.py에서 함수 임포트 및 사용
    session = SessionLocal()
    try:
        papers = get_papers_by_date_and_category(session, report_date)
        if top_n:
            papers = papers[:top_n]

        if not papers:
            logger.info(f"지정된 날짜에 논문이 없습니다: {report_date_str}")
            return jsonify({"message": f"지정된 날짜 ({report_date_str})에 해당하는 논문이 없습니다."})

        generate_pdf_report(pdf_filepath, papers, report_date)
        logger.info(f"PDF 보고서 생성 완료: {pdf_filepath}")
        return jsonify({"pdf_url": f"/view_pdf/{output_filename}"})
    except Exception as e:
        logger.error(f"보고서 생성 중 오류 발생: {e}")
        return jsonify({"error": f"보고서 생성 중 오류 발생: {e}"}), 500
    finally:
        session.close()

@app.route('/view_pdf/<filename>')
def view_pdf(filename):
    logger.debug(f"view_pdf 함수 시작 - filename: {filename}")
    try:
        return send_from_directory(PDF_REPORTS_DIR, filename, as_attachment=False)
    except FileNotFoundError:
        logger.error(f"파일을 찾을 수 없습니다: {filename}")
        return jsonify({"error": "PDF 파일을 찾을 수 없습니다."}), 404

if __name__ == '__main__':
    logger.debug("__main__ 진입 (web_app.py)")
    app.run(debug=True, host='0.0.0.0', port=5000)
    logger.debug("__main__ 종료 (web_app.py)") 