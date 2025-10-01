from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from Parse_with_segments import ParseWithLogs
from database import json_repo

app = FastAPI(title="Terraform Logs Parser API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешает все источники (не для продакшена!)
    allow_credentials=True,
    allow_methods=["*"],  # Разрешает все HTTP методы (GET, POST, PUT, DELETE и т.д.)
    allow_headers=["*"],  # Разрешает все заголовки
)
@app.post("/api/parsejson")
async def parse_json(file: UploadFile):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .json")

    content = await file.read()
    text = content.decode("utf-8-sig")
    logs = [json.loads(line) for line in text.splitlines() if line.strip()]


    segments = ParseWithLogs.parse_file(logs)
    await json_repo.save_json_file(file.filename, segments=segments)
    return {"segments": segments}

@app.post("/api/parsechainsjson")
async def parse_chains_json(file: UploadFile):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .json")

    content = await file.read()
    text = content.decode("utf-8-sig")
    logs = [json.loads(line) for line in text.splitlines() if line.strip()]


    chains = ParseWithLogs.parse_file_to_chain(logs)
    await json_repo.save_json_file(file.filename, chains=chains)
    return {"chains": chains}

@app.get("/api/jsonfiles")
async def get_all_json_filenames():
    """
    Получить список всех названий JSON файлов
    """
    filenames = await json_repo.get_all_filenames()
    return {"filenames": filenames}


@app.get("/api/jsonfiles/{filename}/segments")
async def get_file_segments(filename: str):
    """
    Получить segments по названию файла
    """
    segments = await json_repo.get_segments_by_filename(filename)
    if segments is None:
        raise HTTPException(status_code=404, detail=f"Файл с названием '{filename}' не найден")

    return {"filename": filename, "segments": segments}


@app.get("/api/jsonfiles/{filename}/chains")
async def get_file_chains(filename: str):
    """
    Получить chains по названию файла
    """
    chains = await json_repo.get_chains_by_filename(filename)
    if chains is None:
        raise HTTPException(status_code=404, detail=f"Файл с названием '{filename}' не найден")

    return {"filename": filename, "chains": chains}