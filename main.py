from fastapi import FastAPI, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import json
from Parse_with_segments import ParseWithLogs

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
    return {"segments": segments}