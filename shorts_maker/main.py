import logging
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from moviepy.config import change_settings
import os

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# MoviePy가 ImageMagick을 찾도록 경로를 설정합니다.
# ImageMagick이 PATH에 없거나 moviepy가 인식하지 못할 경우 필요합니다.
IMAGEMAGICK_BINARY = r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
os.environ["IMAGEMAGICK_BINARY"] = IMAGEMAGICK_BINARY
change_settings({"IMAGEMAGICK_BINARY": IMAGEMAGICK_BINARY})

Base = declarative_base()

class Paper(Base):
    __tablename__ = 'papers'
    id = Column(String, primary_key=True) # DOI or unique ID
    title = Column(String, nullable=False)
    authors = Column(String) # Comma separated authors
    year = Column(Integer)
    abstract = Column(String)

    # Relationship for papers cited by this paper (references)
    citations_made = relationship(
        "Citation",
        foreign_keys="Citation.citing_paper_id",
        back_populates="citing_paper"
    )
    # Relationship for papers that cite this paper (cited by)
    citations_received = relationship(
        "Citation",
        foreign_keys="Citation.cited_paper_id",
        back_populates="cited_paper"
    )

    def __repr__(self):
        return f"<Paper(id='{self.id}', title='{self.title}')>"

class Citation(Base):
    __tablename__ = 'citations'
    citing_paper_id = Column(String, ForeignKey('papers.id'), primary_key=True)
    cited_paper_id = Column(String, ForeignKey('papers.id'), primary_key=True)

    citing_paper = relationship("Paper", foreign_keys=[citing_paper_id])
    cited_paper = relationship("Paper", foreign_keys=[cited_paper_id])

    def __repr__(self):
        return f"<Citation(citing='{self.citing_paper_id}', cited='{self.cited_paper_id}')>"

DATABASE_URL = "sqlite:///./papers.db" # SQLite database file

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    logger.debug("get_db 함수 진입")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        logger.debug("get_db 함수 종료")

def get_papers_from_db(db_session, limit=5):
    logger.debug(f"get_papers_from_db 함수 진입 (limit: {limit})")
    papers = db_session.query(Paper).limit(limit).all()
    logger.debug(f"데이터베이스에서 {len(papers)}개의 논문을 가져왔습니다.")
    logger.debug("get_papers_from_db 함수 종료")
    return papers

def generate_short_script(paper_abstract):
    logger.debug("generate_short_script 함수 진입")
    # short-gpt를 사용하여 스크립트를 생성하는 로직을 여기에 추가합니다.
    # 이 예시에서는 초록의 처음 몇 문장을 사용합니다.
    sentences = paper_abstract.split('.')
    script = ". ".join(sentences[:3]) + "." if len(sentences) > 0 else ""
    logger.debug("generate_short_script 함수 종료")
    return script

def create_video_from_script(script, output_filename="output.mp4"):
    logger.debug(f"create_video_from_script 함수 진입 (output_filename: {output_filename})")
    # moviepy를 사용하여 비디오를 생성하는 로직을 여기에 추가합니다.
    # 이 예시에서는 간단한 텍스트 클립을 만듭니다.
    from moviepy.editor import TextClip, CompositeVideoClip, ColorClip
    from moviepy.audio.AudioClip import AudioArrayClip
    import numpy as np
    from gtts import gTTS # Google Text-to-Speech
    import os

    tts = gTTS(text=script, lang='ko')
    tts.save("temp_audio.mp3")

    # 출력 파일의 절대 경로를 구성합니다.
    current_dir = os.getcwd()
    full_output_path = os.path.join(current_dir, output_filename)

    # Load audio and get its duration
    from moviepy.editor import AudioFileClip
    audio_clip = AudioFileClip("temp_audio.mp3")
    audio_duration = audio_clip.duration

    text_clip = TextClip(script, fontsize=30, color='white', bg_color='black').set_duration(audio_duration).set_pos('center')
    final_clip = CompositeVideoClip([text_clip.set_audio(audio_clip)])
    final_clip.write_videofile(full_output_path, fps=24)

    os.remove("temp_audio.mp3") # Clean up temporary audio file
    logger.debug("create_video_from_script 함수 종료")

def add_dummy_papers(db_session):
    logger.debug("add_dummy_papers 함수 진입")
    if db_session.query(Paper).count() == 0:
        logger.debug("데이터베이스에 논문이 없습니다. 더미 데이터를 추가합니다.")
        dummy_papers = [
            Paper(id="10.1109/LRA.2023.3323098", 
                  title="A Novel Method for Autonomous Navigation of Mobile Robots in Unstructured Environments Using Deep Reinforcement Learning",
                  authors="Kim, L., Park, S.",
                  year=2023,
                  abstract="This paper proposes a novel method for autonomous navigation of mobile robots in unstructured environments. The approach utilizes deep reinforcement learning to enable the robot to learn optimal navigation policies directly from sensor inputs. Experimental results demonstrate improved performance compared to traditional methods in complex and dynamic settings."),
            Paper(id="10.1007/s00521-023-08876-0", 
                  title="Enhancing Medical Image Analysis with Generative Adversarial Networks: A Survey",
                  authors="Lee, J., Choi, H.",
                  year=2023,
                  abstract="Generative Adversarial Networks (GANs) have shown remarkable success in various computer vision tasks, including medical image analysis. This survey provides a comprehensive overview of recent advancements in applying GANs to medical imaging, covering topics such as image synthesis, segmentation, and anomaly detection. We also discuss challenges and future directions in this rapidly evolving field."),
            Paper(id="10.1145/3543597.3543632",
                  title="A Deep Learning Approach to Personalized Recommendation Systems in E-commerce",
                  authors="Jung, D., Kim, M., Lee, S.",
                  year=2022,
                  abstract="Personalized recommendation systems are crucial for enhancing user experience in e-commerce platforms. This paper introduces a deep learning framework that leverages user historical data and item attributes to generate accurate and diverse recommendations. Extensive experiments on real-world datasets demonstrate the effectiveness of our proposed approach in improving recommendation quality and user engagement."),
            Paper(id="10.1016/j.patrec.2023.01.015",
                  title="Real-time Human Pose Estimation using Lightweight Convolutional Neural Networks",
                  authors="Park, J., Ahn, Y.",
                  year=2023,
                  abstract="Human pose estimation is a fundamental task in computer vision with applications in human-computer interaction, surveillance, and sports analysis. This work presents a lightweight convolutional neural network architecture for real-time human pose estimation. The proposed model achieves high accuracy while maintaining computational efficiency, making it suitable for deployment on resource-constrained devices."),
            Paper(id="10.1016/j.mlwa.2022.100378",
                  title="Federated Learning for Privacy-Preserving Collaborative AI in Healthcare",
                  authors="Cho, W., Han, K.",
                  year=2022,
                  abstract="Federated learning has emerged as a promising paradigm for collaborative AI model training while preserving data privacy. This paper explores the application of federated learning in the healthcare domain, focusing on securely training diagnostic models across multiple medical institutions without sharing raw patient data. We discuss the benefits, challenges, and future research directions of federated learning in healthcare.")
        ]
        db_session.add_all(dummy_papers)
        db_session.commit()
        logger.debug(f"{len(dummy_papers)}개의 더미 논문이 데이터베이스에 추가되었습니다.")
    else:
        logger.debug("데이터베이스에 이미 논문이 있습니다. 더미 데이터를 추가하지 않습니다.")
    logger.debug("add_dummy_papers 함수 종료")

if __name__ == "__main__":
    logger.debug("main.py 스크립트 실행 시작")
    # 데이터베이스 초기화 (필요한 경우)
    Base.metadata.create_all(bind=engine)

    # 데이터베이스 세션 가져오기
    db_session_generator = get_db()
    db = next(db_session_generator)

    try:
        add_dummy_papers(db) # 더미 데이터 추가
        papers = get_papers_from_db(db, limit=1) # 테스트를 위해 하나의 논문만 가져옵니다.
        if papers:
            paper = papers[0]
            print(f"논문 제목: {paper.title}")
            print(f"논문 초록: {paper.abstract[:200]}...") # 초록의 처음 200자만 출력

            script = generate_short_script(paper.abstract)
            print(f"생성된 스크립트: {script}")

            # 출력 파일의 절대 경로를 구성합니다.
            output_filename_base = f"{paper.id.replace('/', '_')}_short.mp4"
            output_file = output_filename_base

            create_video_from_script(script, output_file)
            print(f"쇼츠 비디오가 {output_file}에 성공적으로 생성되었습니다.")
        else:
            print("데이터베이스에 논문이 없습니다.")
    except Exception as e:
        logger.debug(f"메인 실행 중 오류 발생: {e}")
    finally:
        db_session_generator.close()
        logger.debug("main.py 스크립트 실행 종료") 