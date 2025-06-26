import argparse
import datetime
import logging
import re
import os
import requests
import json
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

# 로깅 설정
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LM Studio API 설정
LM_STUDIO_API_URL = "http://127.0.0.1:1234/v1/chat/completions"
LM_STUDIO_MODEL = "lgai-exaone.exaone-3.5-7.8b-instruct"

# 텍스트 정리 함수: HTML 태그 제거 및 ReportLab에 안전한 문자열로 변환 (유효하지 않은 XML 문자 제거 포함)
def sanitize_text_for_pdf(text):
    if text is None:
        return "N/A"
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
        "max_tokens": 150 # 요약 길이 제한
    }

    try:
        response = requests.post(LM_STUDIO_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status() # HTTP 오류 발생 시 예외 발생
        completion = response.json()
        if completion and 'choices' in completion and completion['choices']:
            summarized_text = completion['choices'][0]['message']['content'].strip()
            logger.debug(f"LLM 요약 성공: {summarized_text[:50]}...")
            return summarized_text
        else:
            logger.warning("LM Studio API 응답에서 유효한 요약 결과를 찾을 수 없습니다.")
            return abstract # LLM 응답이 없으면 원본 반환
    except requests.exceptions.RequestException as e:
        logger.error(f"LM Studio API 요청 중 오류 발생: {e}")
        return abstract # 오류 발생 시 원본 초록 반환
    except json.JSONDecodeError as e:
        logger.error(f"LM Studio API 응답 JSON 파싱 오류: {e}")
        return abstract # JSON 파싱 오류 발생 시 원본 초록 반환
    finally:
        logger.debug("summarize_abstract_with_llm 함수 종료")

# LLM을 통한 페르소나 기반 논문 중요도 판단
def judge_paper_importance_with_llm(paper: dict, persona: str) -> bool:
    logger.debug(f"judge_paper_importance_with_llm 함수 시작 - 논문: {paper.get('title')}, 페르소나: {persona}")
    
    if not persona:
        logger.warning("페르소나 정보가 없어 중요도 판단 건너뛰기")
        return True # 페르소나 없으면 일단 중요하다고 가정

    headers = {"Content-Type": "application/json"}
    payload = {
        "model": LM_STUDIO_MODEL,
        "messages": [
            {"role": "system", "content": f"You are an AI assistant that evaluates the importance of academic papers for a specific persona. Respond with 'YES' if the paper is highly relevant and important to the persona, and 'NO' otherwise. Provide a brief reason."},
            {"role": "user", "content": f"Persona: '{persona}'. Paper Title: '{paper.get('title')}', Abstract: '{paper.get('abstract')}', Categories: '{', '.join(paper.get('categories', []))}'. Is this paper important to the persona? (YES/NO)"}
        ],
        "temperature": 0.2,
        "max_tokens": 50 # 짧은 답변 (YES/NO + 이유)
    }

    try:
        response = requests.post(LM_STUDIO_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        completion = response.json()
        if completion and 'choices' in completion and completion['choices']:
            llm_response = completion['choices'][0]['message']['content'].strip().upper()
            # LLM 응답 시작 부분의 마크다운 볼드체 제거 (예: **YES** -> YES)
            if llm_response.startswith('**'):
                llm_response = llm_response.lstrip('*').strip() # Leading ** 제거 및 공백 정리
            
            is_important = llm_response.startswith("YES")
            logger.debug(f"LLM 중요도 판단 결과: {llm_response} -> 중요도: {is_important}")
            return is_important
        else:
            logger.warning("LM Studio API 응답에서 유효한 중요도 판단 결과를 찾을 수 없습니다.")
            return True # 응답 없으면 기본적으로 중요하다고 가정
    except requests.exceptions.RequestException as e:
        logger.error(f"LM Studio API 요청 중 오류 발생: {e}")
        return True # 오류 발생 시 기본적으로 중요하다고 가정
    except json.JSONDecodeError as e:
        logger.error(f"LM Studio API 응답 JSON 파싱 오류: {e}")
        return True # JSON 파싱 오류 발생 시 기본적으로 중요하다고 가정
    finally:
        logger.debug("judge_paper_importance_with_llm 함수 종료")

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

# SQLAlchemy 모델 정의 (daily_crawler_app/crawler_src/models.py와 동일하게 유지)
Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'

    paper_id = Column(String, primary_key=True)
    external_id = Column(String)
    platform = Column(String)
    title = Column(Text)
    abstract = Column(Text)
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

    citing_papers = relationship("Citation", foreign_keys="Citation.cited_paper_id", backref="cited_paper", primaryjoin="Paper.paper_id == Citation.cited_paper_id")
    cited_papers = relationship("Citation", foreign_keys="Citation.citing_paper_id", backref="citing_paper", primaryjoin="Paper.paper_id == Citation.citing_paper_id")

    def __repr__(self):
        return f"<Paper(title=''{self.title[:20]}...'', platform=''{self.platform}'', year={self.year})>"

    def to_dict(self):
        logger.debug(f"Paper 모델 to_dict 함수 시작 - paper_id: {self.paper_id}")
        result = {
            "paper_id": self.paper_id,
            "external_id": self.external_id,
            "platform": self.platform,
            "title": self.title,
            "abstract": self.abstract,
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
        logger.debug(f"Paper 모델 to_dict 함수 종료 - paper_id: {self.paper_id}")
        return result

class Citation(Base):
    __tablename__ = 'citations'

    citing_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.paper_id'), primary_key=True)

    def __repr__(self):
        return f"<Citation(citing_paper_id=''{self.citing_paper_id}'', cited_paper_id=''{self.cited_paper_id}'')>"

# 데이터베이스 설정
# DATABASE_URL = "sqlite:///../daily_crawler_app/papers.db" # daily_crawler_app 폴더의 papers.db 사용
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # paper_system 디렉토리
DATABASE_URL = f"sqlite:///{os.path.join(base_dir, 'daily_crawler_app', 'papers.db')}"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_papers_by_date_and_category(session, target_date, category=None):
    logger.debug(f"get_papers_by_date_and_category 함수 시작 - target_date: {target_date}, category: {category}")
    query = session.query(Paper).filter(
        Paper.crawled_date >= target_date,
        Paper.crawled_date < target_date + datetime.timedelta(days=1)
    )
    if category:
        query = query.filter(Paper.categories.contains([category])) # JSONB Contains
    papers = query.all()
    logger.debug(f"get_papers_by_date_and_category 함수 종료 - 찾은 논문 수: {len(papers)}")
    return papers

def generate_pdf_report(output_filename, papers, report_date, category=None, persona=None):
    logger.debug(f"generate_pdf_report 함수 시작 - output_filename: {output_filename}, 논문 수: {len(papers)}, 페르소나: {persona}")
    doc = SimpleDocTemplate(output_filename, pagesize=letter,
                            rightMargin=inch/2, leftMargin=inch/2,
                            topMargin=inch/2, bottomMargin=inch/2)
    styles = getSampleStyleSheet()

    # 한글 폰트 스타일 추가 및 업데이트
    styles.add(ParagraphStyle(name='TitleKorean',
                             parent=styles['Title'],
                             fontName='MalgunGothicBd',
                             fontSize=24,
                             leading=28,
                             alignment=1,
                             spaceAfter=20)) # CENTER, 간격 추가
    styles.add(ParagraphStyle(name='H1Korean',
                             parent=styles['h1'],
                             fontName='MalgunGothicBd',
                             fontSize=18,
                             leading=22,
                             spaceAfter=15)) # 간격 추가
    styles.add(ParagraphStyle(name='HeaderDate',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=14,
                             leading=16,
                             textColor=colors.HexColor('#4b5563')))
    styles.add(ParagraphStyle(name='NormalKorean',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=10,
                             leading=14,
                             alignment=1))
    styles.add(ParagraphStyle(name='AbstractKorean',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=9,
                             leading=11,
                             spaceBefore=6,
                             spaceAfter=6,
                             leftIndent=10,
                             rightIndent=10,
                             alignment=4)) # JUSTIFY
    styles.add(ParagraphStyle(name='AdSpaceKorean', # 광고 카드 전체 스타일 (배경, 테두리 등)
                             parent=styles['Normal'],
                             backColor=colors.white, # 개별 광고 카드에서 배경색 설정
                             borderWidth=0.5,
                             borderColor=colors.HexColor('#d1d5db'), # Tailwind gray-300
                             borderRadius=8,
                             spaceBefore=0,
                             spaceAfter=0,
                             leftIndent=0,
                             rightIndent=0,
                             topIndent=0,
                             bottomIndent=0))
    styles.add(ParagraphStyle(name='CardTitle',
                             parent=styles['h2'],
                             fontName='MalgunGothicBd',
                             fontSize=14,
                             leading=16,
                             spaceAfter=5,
                             textColor=colors.HexColor('#1f2937')))
    styles.add(ParagraphStyle(name='CardBody',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=9,
                             leading=11,
                             spaceAfter=3,
                             textColor=colors.HexColor('#4b5563')))
    styles.add(ParagraphStyle(name='CategoryBadge',
                             parent=styles['Normal'],
                             fontName='MalgunGothicBd',
                             fontSize=8,
                             backColor=colors.HexColor('#e0e7ff'), # 파스텔 블루
                             textColor=colors.HexColor('#4361ee'), # 진한 파랑
                             borderPadding=2,
                             borderRadius=4,
                             leading=10,
                             alignment=1, # 중앙 정렬
                             leftIndent=0, # 배지 내부 텍스트 정렬
                             rightIndent=0)) # 배지 내부 텍스트 정렬
    styles.add(ParagraphStyle(name='PdfUrl',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=9,
                             leading=11,
                             textColor=colors.HexColor('#2563eb'), # 파란색 링크
                             underline=1)) # 밑줄 추가
    styles.add(ParagraphStyle(name='AdCircle',
                             parent=styles['Normal'],
                             fontName='MalgunGothicBd',
                             fontSize=24,
                             leading=28,
                             textColor=colors.HexColor('#6b7280'), # Tailwind gray-500
                             backColor=colors.HexColor('#e5e7eb'), # Tailwind gray-200
                             borderPadding=5, # 패딩으로 원형 효과
                             borderRadius=25, # 원형으로 만들기
                             spaceAfter=10)) # AD 텍스트 아래 간격
    styles.add(ParagraphStyle(name='AdText',
                             parent=styles['Normal'],
                             fontName='MalgunGothic',
                             fontSize=11,
                             leading=14,
                             alignment=1, # CENTER
                             textColor=colors.HexColor('#4b5563')))

    story = []

    # Header Section
    header_content = [
        [Paragraph("논문 요약 보고서", styles['TitleKorean'])],
        [Spacer(1, 0.1 * inch)], # 제목과 날짜 사이 간격
        [Paragraph(f"📅 날짜: {sanitize_text_for_pdf(report_date.strftime('%Y년 %m월 %d일'))}", styles['HeaderDate'])]
    ]
    if category:
        header_content.append([Paragraph(f"카테고리: {sanitize_text_for_pdf(category)}", styles['HeaderDate'])]) # 카테고리도 같은 스타일

    header_table_style = TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.white),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')), # Tailwind gray-200 border
        ('ROUNDEDCORNERS', [8,8,8,8]), # 둥근 모서리
        ('LEFTPADDING', (0,0), (-1,-1), 20),
        ('RIGHTPADDING', (0,0), (-1,-1), 20),
        ('TOPPADDING', (0,0), (-1,-1), 20),
        ('BOTTOMPADDING', (0,0), (-1,-1), 20),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ])

    header_table = Table(header_content, colWidths=[letter[0] - inch]) # 페이지 너비 - 좌우 여백
    header_table.setStyle(header_table_style)
    story.append(header_table)
    story.append(Spacer(1, 0.2 * inch)) # 간격 줄임
    story.append(PageBreak())

    # Papers Content Section (Card Layout)
    # 페르소나 기반으로 논문 필터링
    if persona:
        logger.debug(f"페르소나 '{persona}'에 따라 논문 필터링 시작")
        filtered_papers = []
        for paper in papers:
            # Paper 객체를 dict로 변환하여 judge_paper_importance_with_llm에 전달
            paper_dict = {
                "title": paper.title,
                "abstract": paper.abstract,
                "categories": paper.categories
            }
            if judge_paper_importance_with_llm(paper_dict, persona):
                filtered_papers.append(paper)
            else:
                logger.debug(f"논문 '{paper.title}'은(는) 페르소나 '{persona}'에게 중요하지 않아 제외됨.")
        papers = filtered_papers # 필터링된 논문으로 대체
        logger.debug(f"페르소나 필터링 후 남은 논문 수: {len(papers)}")
        if not papers:
            logger.warning(f"페르소나 '{persona}'에 해당하는 논문이 없어 PDF 보고서를 생성할 수 없습니다.")
            return # 논문이 없으면 함수 종료

    for i, paper in enumerate(papers):
        logger.debug(f"PDF에 논문 추가 중 (카드 형식): {paper.title}")

        sanitized_title = sanitize_text_for_pdf(paper.title)
        sanitized_abstract = sanitize_text_for_pdf(summarize_abstract_with_llm(paper.abstract))
        sanitized_pdf_url = sanitize_text_for_pdf(paper.pdf_url)
        sanitized_authors = sanitize_text_for_pdf(', '.join(paper.authors) if paper.authors else None)
        sanitized_platform = sanitize_text_for_pdf(paper.platform)
        sanitized_categories = sanitize_text_for_pdf(', '.join(paper.categories) if paper.categories else None)

        # 플랫폼, 발행일, 카테고리를 위한 중첩 테이블 데이터
        # 이미지와 최대한 유사하게 텍스트와 배지를 같은 줄에 표현
        platform_date_category_data = [[
            Paragraph(f"<font face='MalgunGothicBd'>플랫폼:</font> {sanitized_platform}", styles['CardBody']),
            Paragraph(f"<font face='MalgunGothicBd'>발행일:</font> {paper.published_date.strftime('%Y-%m-%d') if paper.published_date else 'N/A'}", styles['CardBody']),
            Paragraph(f"<font face='MalgunGothicBd'>카테고리:</font>", styles['CardBody']),
            Paragraph(sanitized_categories, styles['CategoryBadge'])
        ]]
        
        # 컬럼 너비를 유동적으로 설정. 카테고리 배지가 고정 너비를 갖도록 조정
        # colWidths=[None, None, None, styles['CategoryBadge'].width if hasattr(styles['CategoryBadge'], 'width') else 1.5*inch]
        # 위 방식은 CategoryBadge가 Paragraph로 들어가기 때문에 width 속성이 없을 수 있음
        # 대신, 상대적인 너비를 사용하고 ReportLab이 자동으로 조절하도록 합니다.
        platform_date_category_col_widths = [0.25 * (letter[0] - inch - 40), 0.25 * (letter[0] - inch - 40), 0.2 * (letter[0] - inch - 40), 0.3 * (letter[0] - inch - 40)] # 대략적인 비율

        meta_data_table = Table(platform_date_category_data, colWidths=platform_date_category_col_widths, hAlign='LEFT')
        meta_data_table.setStyle(TableStyle([
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))


        # 카드 내용을 위한 메인 테이블 데이터
        card_content_data = [
            [Paragraph(sanitized_title, styles['CardTitle'])],
            [Spacer(1, 0.05 * inch)], # 제목 아래 간격
            [Paragraph(f"👤 저자: {sanitized_authors}", styles['CardBody'])],
            [Spacer(1, 0.1 * inch)], # 저자 아래 간격
            [meta_data_table], # 메타데이터 중첩 테이블
            [Spacer(1, 0.1 * inch)], # 플랫폼/날짜/카테고리 아래 간격
            [Paragraph(f"🔗 PDF URL: {sanitized_pdf_url} ↗️", styles['PdfUrl'])],
            [Spacer(1, 0.2 * inch)], # URL 아래 간격
            [Paragraph("<font face='MalgunGothicBd'>초록:</font>", styles['NormalKorean'])], # 초록 레이블 굵게
            [Paragraph(sanitized_abstract, styles['AbstractKorean'])]
        ]

        # 카드 테이블 스타일
        card_table_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#e5e7eb')), # Tailwind gray-200 border
            ('ROUNDEDCORNERS', [8,8,8,8]), # 둥근 모서리
            ('LEFTPADDING', (0,0), (-1,-1), 20),
            ('RIGHTPADDING', (0,0), (-1,-1), 20),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ])

        card_table = Table(card_content_data, colWidths=[letter[0] - inch])
        card_table.setStyle(card_table_style)

        story.append(card_table)
        story.append(Spacer(1, 0.2 * inch)) # 카드 간 간격 줄임

    # Advertisement Section (at the very end)
    story.append(PageBreak()) # Start ads on a new page
    story.append(Paragraph("광고 섹션", styles['TitleKorean']))
    story.append(Spacer(1, 0.2 * inch)) # 간격 줄임

    # 광고 카드 데이터 (3열)
    ad_card_1_content = [
        Paragraph("AD", styles['AdCircle']),
        Paragraph("이곳에 광고가 들어갈 자리입니다.<br/>광고 문의: your_ad_contact@example.com", styles['AdText']),
    ]
    ad_card_2_content = [
        Paragraph("AD", styles['AdCircle']),
        Paragraph("또 다른 광고 자리입니다.<br/>자세한 정보는 웹사이트를 방문하세요.", styles['AdText']),
    ]
    ad_card_3_content = [
        Paragraph("AD", styles['AdCircle']),
        Paragraph("마지막 광고 자리입니다.<br/>파트너십 문의 환영합니다.", styles['AdText']),
    ]

    # 각 광고 카드들을 개별 테이블로 정의하여 배경색과 테두리 적용
    ad_table_data = [
        [
            Table([ad_card_1_content], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#e0e7ff')), # from-blue-50 to-blue-100 근사치
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#a7c4ff')), # border-blue-200 근사치
                ('ROUNDEDCORNERS', [8,8,8,8]),
                ('LEFTPADDING', (0,0), (-1,-1), 5),
                ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ]), colWidths=[None]), # colWidths를 None으로 설정하여 컨텐츠에 맞게 조절
            Table([ad_card_2_content], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#d0f0d0')), # from-green-50 to-green-100 근사치
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#90ee90')), # border-green-200 근사치
                ('ROUNDEDCORNERS', [8,8,8,8]),
                ('LEFTPADDING', (0,0), (-1,-1), 5),
                ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ]), colWidths=[None]),
            Table([ad_card_3_content], style=TableStyle([
                ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f0e0ff')), # from-purple-50 to-purple-100 근사치
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor('#d8bfd8')), # border-purple-200 근사치
                ('ROUNDEDCORNERS', [8,8,8,8]),
                ('LEFTPADDING', (0,0), (-1,-1), 5),
                ('RIGHTPADDING', (0,0), (-1,-1), 5),
                ('TOPPADDING', (0,0), (-1,-1), 5),
                ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ]), colWidths=[None])
        ]
    ]

    # 바깥쪽 광고 테이블의 컬럼 너비 계산. 각 광고 카드 테이블은 내부에서 스스로 너비를 조절합니다.
    ad_col_width = (letter[0] - inch - 40) / 3 # 페이지 너비 - 좌우 여백 (각 0.5인치) - 테이블 내부 여백 (총 20 * 2) / 3열

    # 각 광고 카드 테이블의 colWidths를 명시적으로 설정
    for row in ad_table_data:
        for ad_card_table in row:
            # 이전에 colWidths=[ad_col_width] 로 설정된 부분을 None으로 변경 (내부 테이블 자동 조절)
            # 하지만 바깥쪽 테이블은 여전히 고정 너비를 가져야 함.
            # 이 부분은 ReportLab의 Table이 중첩될 때 약간 복잡할 수 있습니다.
            # 일단은 None으로 두고, 필요하면 다시 조정합니다.
            pass # 이미 위에서 colWidths=[None] 으로 설정했으므로 추가 설정 불필요

    ad_table_outer_style = TableStyle([
        ('LEFTPADDING', (0,0), (-1,-1), 0), # 이전에 10으로 설정했는데, 이미지에 맞춰 0으로
        ('RIGHTPADDING', (0,0), (-1,-1), 0), # 이전에 10으로 설정했는데, 이미지에 맞춰 0으로
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ])

    ad_table = Table(ad_table_data, colWidths=[ad_col_width, ad_col_width, ad_col_width])
    ad_table.setStyle(ad_table_outer_style)
    story.append(ad_table)
    story.append(Spacer(1, 0.2 * inch)) # 간격 줄임

    # Footer
    story.append(Paragraph("© 2025 논문 요약 보고서. All rights reserved.", styles['NormalKorean']))

    try:
        doc.build(story)
        logger.info(f"PDF 보고서 ''{output_filename}'' 생성이 완료되었습니다.")
    except Exception as e:
        logger.error(f"PDF 보고서 생성 중 오류 발생: {e}")

def main():
    logger.debug("main 함수 시작")
    parser = argparse.ArgumentParser(description="Generate a PDF report of papers for a specific date and category.")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD format (e.g., 2023-01-01)")
    parser.add_argument("--category", type=str, help="Optional: Specific category to filter papers by (e.g., 'Computer Science')")
    parser.add_argument("--output", type=str, default="paper_report.pdf", help="Output PDF filename. Default is paper_report.pdf")
    parser.add_argument("--top_n", type=int, help="Optional: Number of top papers to include in the report (e.g., 10). If not specified, all papers for the date/category will be included. Currently, this selects the first N papers from the query results.")
    parser.add_argument("--persona", type=str, help="Optional: Specific persona to filter papers by")

    args = parser.parse_args()

    try:
        report_date = datetime.datetime.strptime(args.date, '%Y-%m-%d')
        category = args.category if args.category != 'all' else None
        output_path = args.output
        top_n = args.top_n
        persona = args.persona
    except ValueError:
        logger.error("잘못된 날짜 형식입니다. YYYY-MM-DD 형식을 사용하세요.")
        return

    session = SessionLocal()
    try:
        logger.debug("데이터베이스 세션 시작")
        papers = get_papers_by_date_and_category(session, report_date, category)

        # LLM 기반 중요도 정렬 또는 랜덤 선택 (추후 구현)
        if top_n:
            logger.debug(f"상위 {top_n}개 논문 선택 (현재는 조회 순서대로).")
            papers = papers[:top_n]

        if not papers:
            logger.info(f"지정된 날짜 ({args.date}) 및 카테고리 ({args.category if args.category else '모든 카테고리'})에 해당하는 논문이 없습니다.")
            return

        generate_pdf_report(output_path, papers, report_date, category, persona)
    except Exception as e:
        logger.error(f"보고서 생성 중 예외 발생: {e}")
    finally:
        session.close()
        logger.debug("데이터베이스 세션 종료")
    logger.debug("main 함수 종료")

if __name__ == "__main__":
    logger.debug("__main__ 진입")
    main()
    logger.debug("__main__ 종료") 