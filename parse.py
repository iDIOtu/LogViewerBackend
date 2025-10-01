import json
import re
from datetime import datetime, timedelta


class Parse:
    # --- Регулярки для timestamp и уровня логирования ---
    TS_PATTERNS = [
        # строгий ISO (приоритет)
        re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?"),
        # время HH:MM:SS только в безопасных позициях (например начало строки или после даты)
        re.compile(r"(?:^\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)|(?:(?<=\d{4}-\d{2}-\d{2}[ T])\d{2}:\d{2}:\d{2}(?:[.,]\d+)?)"),
        # epoch (только как отдельный токен)
        re.compile(r"\b\d{10}(?:\.\d+)?\b"),
    ]

    # допустимый диапазон epoch (примерно 2001-01-01 .. 2100-01-01)
    EPOCH_MIN = 1000000000  # ~2001-09-09
    EPOCH_MAX = 4102444800  # 2100-01-01

    LEVEL_PATTERN = re.compile(r"\b(INFO|DEBUG|TRACE|ERROR|WARN|FATAL)\b", re.IGNORECASE)

    START_TRIGGERS = {
        "plan": [
            "backend/local: starting Plan operation",
            "calling Plan",
        ],
        "apply": [
            "backend/local: starting Apply operation",

        ],
    }

    END_TRIGGERS = {
        "plan": [
            "Plan is complete",
            "Plan complete",
            "Plan operation completed",
            "statemgr.Filesystem: unlocking terraform.tfstate using fcntl flock",
            re.compile(r"^Plan: \d+ to add, \d+ to change, \d+ to destroy"),
        ],
        "apply": [
            "Apply complete",
            "Apply is complete",
            "Apply operation completed",
            "Apply finished",
            "Apply success",
            "statemgr.Filesystem: unlocking terraform.tfstate using fcntl flock"
        ],
    }

    @classmethod
    def is_error_end(cls, log: dict) -> bool:
        """
        Проверяет, является ли лог ошибкой, которая завершает apply-сегмент.
        Возвращает True/False.
        """
        level_val = log.get("level")
        msg = log.get("message", "")
        if isinstance(level_val, str) and level_val.lower() == "error":
            msg_lower = msg.lower()
            if "vertex" in msg_lower and "error" in msg_lower:
                return True
            elif "resource creation failed" in msg_lower:
                return True
            elif "provider" in msg_lower and "error" in msg_lower:
                return True
        return False

    @staticmethod
    def normalize_keys(entry: dict) -> dict:
        """Убираем символ @ из ключей"""
        return {k.lstrip("@"): v for k, v in entry.items()}

    @classmethod
    def extract_timestamp_level(cls, msg, ts_existing=None, lvl_existing=None):
        ts, lvl = ts_existing, lvl_existing

        # --- timestamp через regex ---
        if not ts :
            for pat in cls.TS_PATTERNS:
                m = pat.search(msg)
                if not m:
                    continue
                candidate = m.group(0)

                # если это epoch-паттерн (последний паттерн в списке), то валидируем
                if pat.pattern == cls.TS_PATTERNS[2].pattern:
                    # candidate содержит только цифры (10 digits) возможно с .fraction
                    try:
                        epoch_val = float(candidate)
                        if EPOCH_MIN <= epoch_val <= EPOCH_MAX:
                            # преобразуем epoch в ISO (без tz, например)
                            try:
                                dt = datetime.fromtimestamp(epoch_val)
                                ts = dt.isoformat()
                                break
                            except Exception:
                                # если не смогли парсить epoch в datetime — игнорируем этот матч
                                continue
                        else:
                            # число вне разумного диапазона — это подозрительный матч (например часть версии)
                            # игнорируем и продолжаем поиск по другим паттернам
                            continue
                    except Exception:
                        continue
                else:
                    # для остальных паттернов просто используем найденную строку
                    ts = candidate
                    break

        # --- уровень ---
        if not lvl:
            m = cls.LEVEL_PATTERN.search(msg)
            lvl = m.group(1).upper() if m else "undefined"

        return ts, lvl

    @classmethod
    def fill_missing_timestamps(cls, logs, segment_start_indices=None, segment_end_indices=None):
        """
        Заполняем пропуски timestamp на основе соседей **только внутри сегментов**.
        segment_start_indices и segment_end_indices — списки индексов начала и конца сегментов в logs
        """
        if segment_start_indices is None or segment_end_indices is None:
            # если сегменты не переданы, используем все логи как один сегмент
            segment_start_indices = [0]
            segment_end_indices = [len(logs) - 1]

        for seg_start, seg_end in zip(segment_start_indices, segment_end_indices):
            timestamps = [logs[i].get("timestamp") for i in range(seg_start, seg_end + 1)]
            for offset, ts in enumerate(timestamps):
                i = seg_start + offset
                if not ts:  # это сработает и для None, и для ""
                    # ищем предыдущий timestamp только внутри сегмента
                    prev = next((timestamps[j] for j in range(offset - 1, -1, -1) if timestamps[j]), None)
                    nxt = next((timestamps[j] for j in range(offset + 1, len(timestamps)) if timestamps[j]), None)

                    if prev and nxt:
                        try:
                            dt_prev = datetime.fromisoformat(prev)
                            dt_next = datetime.fromisoformat(nxt)
                            dt_mid = dt_prev + (dt_next - dt_prev) / 2
                            logs[i]["timestamp"] = dt_mid.isoformat()
                        except Exception:
                            logs[i]["timestamp"] = prev
                    elif prev:
                        logs[i]["timestamp"] = prev
                    elif nxt:
                        logs[i]["timestamp"] = nxt
                    else:
                        logs[i]["timestamp"] = None

        return logs

    @classmethod
    def mark_section_boundaries(cls, logs):
        result = []
        for entry in logs:
            msg = entry.get("message", "")
            marker = None

            # --- START ---
            for sec_type, triggers in cls.START_TRIGGERS.items():
                if any((t in msg) for t in triggers if isinstance(t, str)) or \
                   any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                    marker = f"{sec_type}_start"
                    break

            # --- END ---
            if not marker:
                for sec_type, triggers in cls.END_TRIGGERS.items():
                    if any((t in msg) for t in triggers if isinstance(t, str)) or \
                       any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                        marker = f"{sec_type}_end"
                        break

            # --- Ошибки, завершающие apply ---
            if not marker:
                level_val = entry.get("level")
                if isinstance(level_val, str) and level_val.lower() == "error":
                    msg_lower = msg.lower()
                    if "vertex" in msg_lower and "error" in msg_lower:
                        marker = "error_end"
                    elif "resource creation failed" in msg_lower:
                        marker = "error_end"
                    elif "provider" in msg_lower and "error" in msg_lower:
                        marker = "error_end"

            if marker:
                entry["section_marker"] = marker

            result.append(entry)
        return result

    @classmethod
    def parse_logs_from_list(cls, logs: list):
        parsed_logs = []
        for entry in logs:
            # --- нормализуем ключи ---
            entry = cls.normalize_keys(entry)

            msg = entry.get("message", "")
            ts_existing = entry.get("timestamp")
            lvl_existing = entry.get("level")

            ts, lvl = cls.extract_timestamp_level(msg, ts_existing, lvl_existing)
            if ts:
                entry["timestamp"] = ts
            if lvl:
                entry["level"] = lvl

            parsed_logs.append(entry)

        parsed_logs = cls.fill_missing_timestamps(parsed_logs)
        parsed_logs = cls.mark_section_boundaries(parsed_logs)

        return parsed_logs

