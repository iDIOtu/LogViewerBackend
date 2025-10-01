import json
from parse import Parse
from plugin_client import send_segment_to_plugin


class ParseWithLogs:
    SEGMENT_START_KEYWORD = "Terraform version:"
    SEGMENT_END_EXACT = "statemgr.Filesystem: unlocking terraform.tfstate using fcntl flock"

    PLUGINS = [
        {"host": "localhost", "port": 50051},  # первый плагин
        {"host": "localhost", "port": 50052},  # второй плагин
    ]

    @classmethod
    def split_into_segments(cls, logs: list) -> list:
        """
        Делит список логов на сегменты. Подсегмент может быть только внутри apply.
        """
        segments = []
        current_segment = None
        current_subsegment = None  # <-- объявляем подсегмент
        inside_segment = False
        segment_id = 1
        #subsegment_id = 1  # уникальный ID для подсегмента

        for i, log in enumerate(logs):
            msg = log.get("message", "")

            # --- Начало сегмента ---
            if msg.startswith(cls.SEGMENT_START_KEYWORD) and not inside_segment:
                current_segment = {
                    "Type": "unknown",
                    "Id": segment_id,
                    "StartTime": log.get("timestamp"),
                    "EndTime": None,
                    "ErrorOccurred": False,
                    "Logs": [],
                    "SubSegment": None  # <-- добавляем поле
                }
                inside_segment = True

            # --- Если внутри сегмента ---
            if inside_segment and current_segment is not None:
                current_segment["Logs"].append(log)
                current_segment["EndTime"] = log.get("timestamp")

                # определяем тип сегмента (только один раз)
                if current_segment["Type"] == "unknown":
                    msg_lower = msg.lower()
                    if "backend/local: starting apply operation" in msg_lower:
                        current_segment["Type"] = "apply"
                    elif "backend/local: starting plan operation" in msg_lower:
                        current_segment["Type"] = "plan"

                # --- подсегменты для apply ---
                if current_segment["Type"] == "apply":
                    # начало подсегмента
                    if "apply calling plan" in msg.lower() and current_subsegment is None:
                        current_subsegment = {
                            "Type": "plan",
                            "Id": 1,
                            "StartTime": log.get("timestamp"),
                            "EndTime": None,
                            "Logs": []
                        }
                        #subsegment_id += 1

                    # если подсегмент активен, добавляем лог
                    if current_subsegment is not None:
                        current_subsegment["Logs"].append(log)
                        # проверка конца подсегмента
                        msg_lower = msg.lower()
                        is_error = ("level" in log and isinstance(log["level"], str) and log[
                            "level"].lower() == "error" and
                                    (("vertex" in msg_lower and "error" in msg_lower) or
                                     "resource creation failed" in msg_lower))
                        if "plan is complete" in msg_lower or is_error:
                            current_subsegment["EndTime"] = log.get("timestamp")
                            current_segment["SubSegment"] = current_subsegment  # <-- присваиваем в поле сегмента
                            current_subsegment = None

            # --- Ошибки, завершающие сегмент ---
            if Parse.is_error_end(log) and current_segment is not None:
                current_segment["ErrorOccurred"] = True

            # --- Конец сегмента ---
            if inside_segment and msg == cls.SEGMENT_END_EXACT:
                # добавляем все последующие логи до начала нового сегмента
                j = i + 1
                while j < len(logs) and not logs[j].get("message", "").startswith(cls.SEGMENT_START_KEYWORD):
                    current_segment["Logs"].append(logs[j])
                    current_segment["EndTime"] = logs[j].get("timestamp")
                    j += 1

                segments.append(current_segment)
                segment_id += 1
                current_segment = None
                current_subsegment = None
                inside_segment = False

        return segments

    @classmethod
    def parse_file(cls, logs: list) -> list:
        """
        Принимает путь к JSON-файлу с логами,
        обогащает логи (timestamp, level) и создаёт JSON-файл с сегментами.
        """
        # --- читаем логи --

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
        # сначала вычислим сегментные диапазоны по сообщению (мы используем правила ParseWithLogs)
        segment_ranges = []
        inside = False
        start_idx = None
        for idx, entry in enumerate(enriched_logs):
            msg = entry.get("message", "")
            if msg.startswith(ParseWithLogs.SEGMENT_START_KEYWORD) and not inside:
                start_idx = idx
                inside = True
            if inside and msg == ParseWithLogs.SEGMENT_END_EXACT:
                end_idx = idx
                segment_ranges.append((start_idx, end_idx))
                inside = False
                start_idx = None
        # если сегмент начался, но не был закрыт — закроем его до конца массива
        if inside and start_idx is not None:
            segment_ranges.append((start_idx, len(enriched_logs) - 1))

        # теперь заполняем пропуски только внутри найденных сегментов
        enriched_logs = Parse.fill_missing_timestamps(enriched_logs, segment_ranges)

        # --- режем на сегменты ---
        segments = cls.split_into_segments(enriched_logs)
        return segments

    @classmethod
    def process_segments_with_plugins(cls, segments):
        """
        Отправляет каждый сегмент на все плагины и добавляет результаты в сегмент.
        """
        for segment in segments:
            segment["PluginResponses"] = []
            for plugin in cls.PLUGINS:
                host = plugin["host"]
                port = plugin["port"]

                try:
                    response = send_segment_to_plugin(segment, host, port)
                    # Сохраняем данные плагина в сегмент
                    segment["PluginResponses"].append({
                        "plugin": f"{host}:{port}",
                        "success": response.success,
                        "message": response.message,
                        "metadata": dict(response.metadata),
                        "logs_count": len(response.logs)
                    })

                    # Если плагин вернул новые логи, можно их заменить/добавить
                    if response.logs:
                        segment["Logs"] = [
                            {
                                "level": log.level,
                                "message": log.message,
                                "timestamp": log.timestamp,
                                "module": log.module
                            } for log in response.logs
                        ]

                except Exception as e:
                    # Если плагин не отвечает, просто логируем
                    segment["PluginResponses"].append({
                        "plugin": f"{host}:{port}",
                        "success": False,
                        "message": str(e),
                        "metadata": {},
                        "logs_count": 0
                    })

        return segments