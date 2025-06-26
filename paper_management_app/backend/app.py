import os
import argparse
import datetime
import logging
import re
import requests
import json
from flask import Flask, request, jsonify, send_file
from sqlalchemy import create_engine, Column, String, Text, DateTime, JSON, Integer, ForeignKey
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.declarative import declarative_base
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageBreak, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import tempfile

app = Flask(__name__)

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LM Studio API 설정
LM_STUDIO_API_URL = "http://127.0.0.1:1234/v1/chat/completions"
LM_STUDIO_MODEL = "lgai-exaone.exaone-3.5-7.8b-instruct"

# 데이터베이스 경로 설정 (daily_crawler_app/papers.db를 참조)
DATABASE_URL = "sqlite:///../daily_crawler_app/papers.db"

# 한글 폰트 등록
try:
    # 폰트 파일 경로를 현재 스크립트의 디렉토리를 기준으로 절대 경로로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    malgun_ttf_path = os.path.join(script_dir, 'malgun.ttf')
    malgunbd_ttf_path = os.path.join(script_dir, 'malgunbd.ttf')

    pdfmetrics.registerFont(TTFont('MalgunGothic', malgun_ttf_path))
    pdfmetrics.registerFont(TTFont('MalgunGothicBd', malgunbd_ttf_path))
    logger.debug("MalgunGothic 폰트 등록 성공")
except Exception as e:
    logger.error(f"MalgunGothic 폰트 등록 실패: {e}. 폰트 파일이 스크립트와 같은 경로에 있는지 확인하세요.")

# SQLAlchemy 모델 정의
Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'

    paper_id = Column(String, primary_key=True)
    external_id = Column(String)
    platform = Column(String)
    title = Column(Text)
    abstract = Column(Text)
    summarized_abstract = Column(Text, nullable=True) # 추가된 필드
    authors = Column(JSON)
    categories = Column(JSON)
    pdf_url = Column(String)
    embedding = Column(JSON, nullable=True)
    published_date = Column(DateTime)
    updated_date = Column(DateTime)
    crawled_date = Column(DateTime, nullable=True)
    year = Column(Integer)
    references_ids = Column(JSON, nullable=True)
    cited_by_ids = Column(JSON, nullable=True)

    def to_dict(self):
        return {
            "paper_id": self.paper_id,
            "external_id": self.external_id,
            "platform": self.platform,
            "title": self.title,
            "abstract": self.abstract,
            "summarized_abstract": self.summarized_abstract,
            "authors": self.authors,
            "categories": self.categories,
            "pdf_url": self.pdf_url,
            "embedding": self.embedding,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "updated_date": self.updated_date.isoformat() if self.updated_date else None,
            "crawled_date": self.crawled_date.isoformat() if self.crawled_date else None,
            "year": self.year,
            "references_ids": self.references_ids,
            "cited_by_ids": self.cited_by_ids,
        }

class Citation(Base):
    __tablename__ = 'citations'

    citing_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)

# 데이터베이스 세션 설정
engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)

# 텍스트 정리 함수: HTML 태그 제거 및 ReportLab에 안전한 문자열로 변환 (유효하지 않은 XML 문자 제거 포함)
def sanitize_text_for_pdf(text):
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # 유효하지 않은 XML 1.0 문자 (제어 문자) 제거
    invalid_xml_chars = re.compile(u'[\x00-\x08\x0b\x0c\x0e-\x1f]')
    text = invalid_xml_chars.sub('', text)

    # HTML 태그 제거
    clean_tags = re.compile('<.*?>')
    text = re.sub(clean_tags, '', text)

    # ReportLab 파서에 민감한 문자들을 HTML 엔티티로 변환
    text = text.replace('&', '&amp;')
    text = text.replace('<', '&lt;')
    text = text.replace('>', '&gt;')
    text = text.replace('"', '&quot;')
    text = text.replace("'", '&apos;')

    return text

# LLM을 통한 초록 요약 (LM Studio 연동)
def summarize_abstract_with_llm(abstract: str) -> str:
    logger.debug("summarize_abstract_with_llm 함수 시작")
    if not abstract:
        logger.debug("초록 내용이 없어 요약 건너뛰기")
        return "요약할 초록 내용이 없습니다."

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that summarizes academic paper abstracts concisely."},
            {"role": "user", "content": f"Summarize the following abstract concisely in Korean: {abstract}"}
        ],
        "temperature": 0.3,
        "max_tokens": 150
    }

    try:
        response = requests.post(LM_STUDIO_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        completion = response.json()
        if completion and 'choices' in completion and completion['choices']:
            summarized_text = completion['choices'][0]['message']['content'].strip()
            logger.debug(f"LLM 요약 성공: {summarized_text[:50]}...")
            return summarized_text
        else:
            logger.warning("LM Studio API 응답에서 유효한 요약 결과를 찾을 수 없습니다.")
            return abstract
    except requests.exceptions.RequestException as e:
        logger.error(f"LM Studio API 요청 중 오류 발생: {e}")
        return abstract
    except json.JSONDecodeError as e:
        logger.error(f"LM Studio API 응답 JSON 파싱 오류: {e}")
        return abstract
    finally:
        logger.debug("summarize_abstract_with_llm 함수 종료")

# ReportLab 스타일 설정
def get_reportlab_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleStyle',
                             parent=styles['h1'],
                             fontName='MalgunGothicBd',
                             fontSize=24,
                             leading=28,
                             alignment=1,
                             spaceAfter=20,
                             textColor=colors.HexColor('#2C3E50'))) # Dark Blue Grey

    styles.add(ParagraphStyle(name='SubtitleStyle',
                             parent=styles['h2'],
                             fontName='MalgunGothicBd',
                             fontSize=16,
                             leading=18,
                             alignment=0,
                             spaceBefore=12,
                             spaceAfter=6,
                             textColor=colors.HexColor('#34495E'))) # Dark Grey

    styles.add(ParagraphStyle(name='BodyText',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=10,
                             leading=12,
                             spaceAfter=6,
                             textColor=colors.HexColor('#34495E')))

    styles.add(ParagraphStyle(name='LinkStyle',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=10,
                             textColor=colors.HexColor('#3498DB'), # Bright Blue
                             underline=1,
                             spaceAfter=6))
    
    styles.add(ParagraphStyle(name='CardTitle',
                             fontName='MalgunGothicBd',
                             fontSize=14,
                             leading=16,
                             spaceAfter=6,
                             textColor=colors.HexColor('#2C3E50')))

    styles.add(ParagraphStyle(name='CardBody',
                             fontName='MalgunGothic',
                             fontSize=10,
                             leading=12,
                             spaceAfter=3,
                             textColor=colors.HexColor('#34495E')))

    styles.add(ParagraphStyle(name='CategoryBadge',
                             fontName='MalgunGothicBd',
                             fontSize=8,
                             leading=9,
                             textColor=colors.white,
                             backColor=colors.HexColor('#3498DB'), # Bright Blue
                             borderPadding=3,
                             borderRadius=5,
                             alignment=1)) # Center align text within badge

    styles.add(ParagraphStyle(name='PdfUrl',
                             fontName='MalgunGothic',
                             fontSize=9,
                             textColor=colors.HexColor('#3498DB'),
                             underline=1))

    styles.add(ParagraphStyle(name='AdCircle',
                             fontName='MalgunGothicBd',
                             fontSize=18,
                             textColor=colors.HexColor('#E74C3C'), # Alizarin Red
                             alignment=1, # Center align
                             spaceBefore=10,
                             spaceAfter=5))

    styles.add(ParagraphStyle(name='AdText',
                             fontName='MalgunGothic',
                             fontSize=10,
                             textColor=colors.HexColor('#34495E'),
                             alignment=1)) # Center align

    return styles

def generate_pdf_report(output_filename, papers, report_date, category=None):
    logger.debug("generate_pdf_report 함수 시작")
    doc = SimpleDocTemplate(output_filename, pagesize=letter)
    styles = get_reportlab_styles()
    elements = []

    # Report Title
    report_title = f"AI 논문 보고서 - {report_date.strftime('%Y년 %m월 %d일')}"
    if category:
        report_title += f" ({sanitize_text_for_pdf(category)} 카테고리)"
    elements.append(Paragraph(report_title, styles['TitleStyle']))
    elements.append(Spacer(1, 0.2 * inch))

    if not papers:
        elements.append(Paragraph("지정된 날짜 및 카테고리에 해당하는 논문이 없습니다.", styles['BodyText']))
        doc.build(elements)
        logger.info("생성할 논문이 없어 빈 보고서 생성.")
        return

    # Header with report info
    header_data = [
        [Paragraph(f"<b>보고서 생성일:</b> {datetime.datetime.now().strftime('%Y년 %m월 %d일 %H시 %M분')}", styles['BodyText'])],
        [Paragraph(f"<b>대상 날짜:</b> {report_date.strftime('%Y년 %m월 %d일')}", styles['BodyText'])]
    ]
    if category:
        header_data.append([Paragraph(f"<b>카테고리:</b> {sanitize_text_for_pdf(category)}", styles['BodyText'])])
    
    # Create a table for the header to give it a card-like appearance
    header_table_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#ECF0F1')), # Light Grey background
        ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#2C3E50')),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('ROUNDEDCORNERS', (0,0), (-1,-1), 8), # Rounded corners
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#BDC3C7')), # Light border
    ])
    header_table = Table(header_data, colWidths=[6.5 * inch])
    header_table.setStyle(header_table_style)
    elements.append(header_table)
    elements.append(Spacer(1, 0.3 * inch))

    # Papers Section
    for i, paper in enumerate(papers):
        title = sanitize_text_for_pdf(paper.get('title', 'N/A'))
        abstract = sanitize_text_for_pdf(paper.get('abstract', 'N/A'))
        summarized_abstract = sanitize_text_for_pdf(paper.get('summarized_abstract', 'N/A'))
        authors = sanitize_text_for_pdf(", ".join(paper.get('authors', [])))
        platform = sanitize_text_for_pdf(paper.get('platform', 'N/A'))
        published_date = paper.get('published_date')
        if isinstance(published_date, str):
            try:
                published_date = datetime.datetime.fromisoformat(published_date)
            except ValueError:
                published_date = None
        
        categories = paper.get('categories', [])
        pdf_url = sanitize_text_for_pdf(paper.get('pdf_url', 'N/A'))

        elements.append(Paragraph(f"<b>논문 {i+1}.</b> {title}", styles['CardTitle']))
        elements.append(Spacer(1, 0.05 * inch))

        # Metadata table (Platform, Date, Categories)
        metadata_table_data = []
        
        # Row 1: Platform and Date
        platform_date_cells = []
        platform_date_cells.append(Paragraph(f"<b>플랫폼:</b> {platform}", styles['CardBody']))
        if published_date:
            platform_date_cells.append(Paragraph(f"<b>발행일:</b> {published_date.strftime('%Y-%m-%d')}", styles['CardBody']))
        metadata_table_data.append(platform_date_cells)

        # Row 2: Categories (as badges)
        if categories:
            category_badges = []
            for cat in categories:
                # Create a mini-table for each badge to apply background and border
                badge_content = Paragraph(sanitize_text_for_pdf(cat), styles['CategoryBadge'])
                badge_table = Table([[badge_content]],
                                    style=TableStyle([
                                        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#3498DB')),
                                        ('TEXTCOLOR', (0,0), (0,0), colors.white),
                                        ('ALIGN', (0,0), (0,0), 'CENTER'),
                                        ('VALIGN', (0,0), (0,0), 'MIDDLE'),
                                        ('LEFTPADDING', (0,0), (0,0), 5),
                                        ('RIGHTPADDING', (0,0), (0,0), 5),
                                        ('TOPPADDING', (0,0), (0,0), 2),
                                        ('BOTTOMPADDING', (0,0), (0,0), 2),
                                        ('ROUNDEDCORNERS', (0,0), (0,0), 5),
                                        ('NOSPLIT', (0,0), (-1,-1)) # Keep badge on one line
                                    ]),
                                    rowHeights=[0.2*inch]) # Fixed height for badges
                category_badges.append(badge_table)
                category_badges.append(Spacer(0.1*inch, 0)) # Small space between badges
            
            # Wrap badges in a table for horizontal layout
            metadata_table_data.append([Table([category_badges], colWidths=[(inch * 7.0 / len(category_badges))] * len(category_badges) if category_badges else [0])]) # Adjust colWidths dynamically
        
        metadata_table = Table(metadata_table_data, colWidths=[None, None]) # Auto-adjust column widths
        metadata_table.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('SPAN', (0,1), (-1,1)) if categories else ('NOBACKGROUND', (0,0),(0,0)), # Span categories row if present
        ]))
        elements.append(metadata_table)
        elements.append(Spacer(1, 0.1 * inch))

        elements.append(Paragraph(f"<b>저자:</b> {authors}", styles['CardBody']))
        elements.append(Paragraph(f"<b>PDF URL:</b> <font color="#3498DB">{pdf_url}</font>", styles['PdfUrl']))
        
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(Paragraph("<b>초록:</b>", styles['BodyText']))
        elements.append(Paragraph(abstract, styles['BodyText']))

        # Summarized Abstract (if available)
        if summarized_abstract and summarized_abstract != abstract: # Only show if different from original
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(Paragraph("<b>LLM 요약:</b>", styles['BodyText']))
            elements.append(Paragraph(summarized_abstract, styles['BodyText']))
        
        elements.append(Spacer(1, 0.3 * inch)) # Space after each paper

        if i < len(papers) - 1:
            # Add a subtle separator for readability between papers, mimic card spacing
            elements.append(Spacer(1, 0.1 * inch))
            elements.append(PageBreak()) # Start new paper on new page for better layout control


    # Advertisement Section (at the end)
    elements.append(PageBreak()) # New page for ads
    elements.append(Paragraph("오늘의 추천", styles['TitleStyle']))
    elements.append(Spacer(1, 0.2 * inch))

    ad_styles = TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ])

    ad_text_style = styles['AdText']
    ad_circle_style = styles['AdCircle']

    ad_data = [
        [
            Table([
                [Paragraph("AD", ad_circle_style)],
                [Paragraph("광고 1: 혁신적인 연구 도구", ad_text_style)]
            ], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#FADBD8')), # Light red background
                ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#E74C3C')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('ROUNDEDCORNERS', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E74C3C')),
            ]), colWidths=[2.1*inch], rowHeights=[0.5*inch, 0.8*inch]),
            
            Table([
                [Paragraph("AD", ad_circle_style)],
                [Paragraph("광고 2: 학술 정보 플랫폼", ad_text_style)]
            ], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#D5F5E3')), # Light green background
                ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#27AE60')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('ROUNDEDCORNERS', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#27AE60')),
            ]), colWidths=[2.1*inch], rowHeights=[0.5*inch, 0.8*inch]),
            
            Table([
                [Paragraph("AD", ad_circle_style)],
                [Paragraph("광고 3: 온라인 강좌 할인", ad_text_style)]
            ], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#D6EAF8')), # Light blue background
                ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#3498DB')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 8),
                ('RIGHTPADDING', (0,0), (-1,-1), 8),
                ('TOPPADDING', (0,0), (-1,-1), 8),
                ('BOTTOMPADDING', (0,0), (-1,-1), 8),
                ('ROUNDEDCORNERS', (0,0), (-1,-1), 8),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#3498DB')),
            ]), colWidths=[2.1*inch], rowHeights=[0.5*inch, 0.8*inch]),
        ]
    ]

    ad_table = Table(ad_data, colWidths=[2.3*inch, 2.3*inch, 2.3*inch])
    ad_table.setStyle(ad_styles)
    elements.append(ad_table)

    try:
        doc.build(elements)
        logger.info(f"보고서 '{output_filename}' 생성이 완료되었습니다.")
    except Exception as e:
        logger.error(f"PDF 보고서 생성 중 오류 발생: {e}")
        raise

    logger.debug("generate_pdf_report 함수 종료")

# API 엔드포인트
@app.route('/api/papers', methods=['GET'])
def get_papers():
    session = Session()
    try:
        date_str = request.args.get('date')
        category = request.args.get('category')
        top_n = request.args.get('top_n', type=int)

        query = session.query(Paper)
        if date_str:
            target_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date()
            query = query.filter(Paper.published_date >= target_date,
                                 Paper.published_date < target_date + datetime.timedelta(days=1))
        if category:
            query = query.filter(Paper.categories.like(f'%"{category}"%'))

        papers = query.all()

        # LLM 요약 적용 (여기서 LLM 요약을 수행하고 DB에 저장)
        for paper in papers:
            if not paper.summarized_abstract: # 요약되지 않은 논문만 요약
                summarized_text = summarize_abstract_with_llm(paper.abstract)
                paper.summarized_abstract = summarized_text
                session.add(paper) # 변경 사항을 세션에 추가
        session.commit() # 변경 사항 커밋

        # to_dict를 사용하여 JSON 직렬화
        papers_data = [p.to_dict() for p in papers]

        if top_n:
            papers_data = papers_data[:top_n]

        return jsonify(papers_data)
    except Exception as e:
        logger.error(f"논문 조회 중 오류 발생: {e}")
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/generate_report', methods=['POST'])
def generate_report_api():
    data = request.get_json()
    paper_ids = data.get('paper_ids', [])
    report_date_str = data.get('report_date')
    category = data.get('category')
    
    if not report_date_str:
        return jsonify({"error": "report_date is required"}), 400

    report_date = datetime.datetime.strptime(report_date_str, '%Y-%m-%d').date()

    session = Session()
    try:
        selected_papers = session.query(Paper).filter(Paper.paper_id.in_(paper_ids)).all()
        
        # 임시 파일에 PDF 생성
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            temp_pdf_path = tmp_file.name
            generate_pdf_report(temp_pdf_path, [p.to_dict() for p in selected_papers], report_date, category)
        
        return send_file(temp_pdf_path, as_attachment=True, download_name=f"report_{report_date_str}.pdf")
    except Exception as e:
        logger.error(f"리포트 생성 중 오류 발생: {e}")
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

if __name__ == '__main__':
    Base.metadata.create_all(engine) # 이 부분은 `papers.db`가 이미 존재하고 스키마가 정의되어 있으므로 실제로는 필요 없을 수 있습니다.
    app.run(debug=True)
