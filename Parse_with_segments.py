import json
from parse import Parse


class ParseWithLogs:
    SEGMENT_START_KEYWORD = "Terraform version:"
    SEGMENT_END_EXACT = "statemgr.Filesystem: unlocking terraform.tfstate using fcntl flock"

    @classmethod
    def split_into_segments(cls, logs: list) -> list:
        """
        Делит список логов на сегменты.
        """
        segments = []
        current_segment = None
        inside_segment = False
        segment_id = 1

        for i, log in enumerate(logs):
            msg = log.get("message", "")


            # --- Начало сегмента ---
            if msg.startswith(cls.SEGMENT_START_KEYWORD) and not inside_segment:
                current_segment = {
                    "Type":"unknown",
                    "Id": segment_id,
                    "StartTime": log.get("timestamp"),
                    "EndTime": None,
                    "ErrorOccurred": False,
                    "Logs": []
                }
                inside_segment = True

            # --- Если внутри сегмента ---
            if inside_segment and current_segment is not None:
                current_segment["Logs"].append(log)
                current_segment["EndTime"] = log.get("timestamp")

                # определяем тип сегмента (только один раз)
                if current_segment["Type"] == "unknown":
                    msg = log.get("message", "").lower()
                    if "backend/local: starting apply operation" in msg:
                        current_segment["Type"] = "apply"
                    elif "backend/local: starting plan operation" in msg:
                        current_segment["Type"] = "plan"

            if Parse.is_error_end(log):
                current_segment["ErrorOccurred"] = True;

                # --- Конец сегмента ---
            if inside_segment and msg == cls.SEGMENT_END_EXACT:

                j = i + 1
                while j < len(logs) and not logs[j].get("message", "").startswith(cls.SEGMENT_START_KEYWORD):
                    current_segment["Logs"].append(logs[j])
                    current_segment["EndTime"] = logs[j].get("timestamp")
                    j += 1

                segments.append(current_segment)
                segment_id += 1
                current_segment = None
                inside_segment = False



        return segments

    @classmethod
    def parse_file(cls, input_file: str, output_file: str):
        """
        Принимает путь к JSON-файлу с логами,
        обогащает логи (timestamp, level) и создаёт JSON-файл с сегментами.
        """
        # --- читаем логи ---
        with open(input_file, "r", encoding="utf-8") as f:
            logs = [json.loads(line) for line in f]

        enriched_logs = []
        for entry in logs:
            # убираем @ в ключах
            entry = Parse.normalize_keys(entry)

            msg = entry.get("message", "")
            ts_existing = entry.get("timestamp")
            lvl_existing = entry.get("level")


            # --- извлекаем время и уровень ---
            if ts_existing is None or lvl_existing is None or ts_existing == "" or lvl_existing == "":
                ts, lvl = Parse.extract_timestamp_level(msg, ts_existing, lvl_existing)
                if ts:
                    entry["timestamp"] = ts
                if lvl:
                    entry["level"] = lvl

            enriched_logs.append(entry)


        # --- заполняем пропущенные timestamp ---
        enriched_logs = Parse.fill_missing_timestamps(enriched_logs)

        # --- режем на сегменты ---
        segments = cls.split_into_segments(enriched_logs)

        # --- пишем результат ---
        with open(output_file, "w", encoding="utf-8") as f_out:
            json.dump(segments, f_out, ensure_ascii=False, indent=2)

        print(f"Готово! Найдено {len(segments)} сегментов. Результат сохранён в {output_file}")
input_file = "4. tflog.json"
output_file = "segments.json"

ParseWithLogs.parse_file(input_file, output_file)