import json
from Parse_with_segments import ParseWithLogs

def main():
    input_file = "4. tflog.json"          # входной файл с логами
    output_file = "segments_parsed.json"  # файл для результата

    logs = []

    # --- читаем построчно (NDJSON) ---
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                log = json.loads(line.strip())
                logs.append(log)
            except json.JSONDecodeError:
                continue

    # --- прогоняем через парсер ---
    segments = ParseWithLogs.parse_file(logs)

    # --- сохраняем результат ---
    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(segments, f_out, ensure_ascii=False, indent=2)

    print(f"✅ Готово! Найдено {len(segments)} сегментов. Результат сохранён в {output_file}")


if __name__ == "__main__":
    main()
