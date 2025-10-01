from sqlalchemy.orm import sessionmaker
from models import JsonFile, get_database_engine, create_tables
from datetime import datetime


class JsonFileRepository:
    def __init__(self):
        self.engine = get_database_engine()
        create_tables(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    async def save_json_file(self, filename: str, segments: list = None, chains: list = None) -> bool:
        # Если оба параметра None, не сохраняем ничего
        if segments is None and chains is None:
            return False

        db = self.SessionLocal()
        try:
            # Проверяем, существует ли уже файл с таким именем
            existing_file = db.query(JsonFile).filter(JsonFile.filename == filename).first()

            if existing_file:
                # Обновляем существующий файл только если переданы данные
                if segments is not None:
                    existing_file.segments = segments
                if chains is not None:
                    existing_file.chains = chains
                existing_file.upload_date = datetime.utcnow()
            else:
                # Создаем новый файл только если есть данные для сохранения
                db_file = JsonFile(
                    filename=filename,
                    segments=segments,
                    chains=chains,
                    upload_date=datetime.utcnow()
                )
                db.add(db_file)

            db.commit()
            return True
        except Exception as e:
            db.rollback()
            raise e
        finally:
            db.close()

    async def get_all_filenames(self):
        """Получить только названия всех JSON файлов"""
        db = self.SessionLocal()
        try:
            files = db.query(JsonFile.filename).order_by(JsonFile.upload_date.desc()).all()
            return [filename[0] for filename in files]
        finally:
            db.close()

    async def get_segments_by_filename(self, filename: str):
        """Получить segments по названию файла"""
        db = self.SessionLocal()
        try:
            file = db.query(JsonFile).filter(JsonFile.filename == filename).first()
            if file:
                return {
                    "filename": file.filename,
                    "segments": file.segments,
                    "upload_date": file.upload_date
                }
            return None
        finally:
            db.close()

    async def get_chains_by_filename(self, filename: str):
        """Получить chains по названию файла"""
        db = self.SessionLocal()
        try:
            file = db.query(JsonFile).filter(JsonFile.filename == filename).first()
            if file:
                return {
                    "filename": file.filename,
                    "chains": file.chains,
                    "upload_date": file.upload_date
                }
            return None
        finally:
            db.close()


# Глобальный экземпляр репозитория
json_repo = JsonFileRepository()