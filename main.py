from fastapi import FastAPI, UploadFile, HTTPException
import json
from parse import Parse

app = FastAPI(title="Terraform Logs Parser API")

@app.post("/api/parsejson")
async def parse_json(file: UploadFile):
    if not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="Файл должен быть в формате .json")

    content = await file.read()
    try:
        logs = json.loads(content.decode("utf-8"))
        if not isinstance(logs, list):
            raise ValueError("JSON должен быть списком объектов")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Некорректный JSON: {str(e)}")


    parsed_data = Parse.parse_logs_from_list(logs)

    return {"parsed": parsed_data}
