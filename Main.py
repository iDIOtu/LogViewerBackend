from fastapi import FastAPI, UploadFile, HTTPException
import json
from parse import parse_logs

app = FastAPI(title="Terraform Logs Parser API")

@app.post("/api/parsejson")
async def parse_json(file: UploadFile):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .json")

    content = await file.read()
    try:
        logs = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Некорректный JSON")

    parsed_data = parse_logs(logs)
    return {"parsed": parsed_data}
