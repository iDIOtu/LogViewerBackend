import json
import re
from datetime import datetime, timedelta


class Parse:
    # --- Регулярки для timestamp и уровня логирования ---
    TS_PATTERNS = [
        re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:\d{2})?"),
        re.compile(r"\d{2}:\d{2}:\d{2}(?:[.,]\d+)?"),
        re.compile(r"\d{10}(?:\.\d+)?"),
    ]

    LEVEL_PATTERN = re.compile(r"\b(INFO|DEBUG|TRACE|ERROR|WARN|FATAL)\b", re.IGNORECASE)

    START_TRIGGERS = {
        "plan": [
            "CLI args: []string{\"plan",
            "backend/local: starting Plan operation",
        ],
        "apply": [
            "CLI args: []string{\"apply",
            "backend/local: starting Apply operation",
        ],
    }

    END_TRIGGERS = {
        "plan": [
            "Plan is complete",
            "Plan complete",
            "Plan operation completed",
            re.compile(r"^Plan: \d+ to add, \d+ to change, \d+ to destroy"),
        ],
        "apply": [
            "Apply complete",
            "Apply is complete",
            "Apply operation completed",
            "Apply finished",
            "Apply success",
        ],
    }

    @classmethod
    def extract_timestamp_level(cls, msg, ts_existing=None, lvl_existing=None):
        ts, lvl = ts_existing, lvl_existing

        # --- timestamp через regex ---
        if not ts:
            for pat in cls.TS_PATTERNS:
                m = pat.search(msg)
                if m:
                    ts = m.group(0)
                    break

        # --- уровень ---
        if not lvl:
            m = cls.LEVEL_PATTERN.search(msg)
            lvl = m.group(1).upper() if m else None

        return ts, lvl

    @classmethod
    def fill_missing_timestamps(cls, logs):
        """
        Заполняем пропуски timestamp на основе соседей.
        """
        # Вытаскиваем список времён
        timestamps = [log.get("@timestamp") for log in logs]

        for i, ts in enumerate(timestamps):
            if ts is None:
                # ищем ближайших сверху
                prev = next((timestamps[j] for j in range(i - 1, -1, -1) if timestamps[j]), None)
                # ищем ближайших снизу
                nxt = next((timestamps[j] for j in range(i + 1, len(timestamps)) if timestamps[j]), None)

                if prev and nxt:
                    try:
                        dt_prev = datetime.fromisoformat(prev)
                        dt_next = datetime.fromisoformat(nxt)
                        dt_mid = dt_prev + (dt_next - dt_prev) / 2
                        logs[i]["@timestamp"] = dt_mid.isoformat()
                    except Exception:
                        logs[i]["@timestamp"] = prev
                elif prev:
                    logs[i]["@timestamp"] = prev
                elif nxt:
                    logs[i]["@timestamp"] = nxt
                else:
                    logs[i]["@timestamp"] = None

        return logs

    @classmethod
    def mark_section_boundaries(cls, logs):
        result = []
        for entry in logs:
            msg = entry.get("@message", "")
            marker = None

            for sec_type, triggers in cls.START_TRIGGERS.items():
                if any((t in msg) for t in triggers if isinstance(t, str)) or \
                   any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                    marker = f"{sec_type}_start"
                    break

            if not marker:
                for sec_type, triggers in cls.END_TRIGGERS.items():
                    if any((t in msg) for t in triggers if isinstance(t, str)) or \
                       any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                        marker = f"{sec_type}_end"
                        break

            if marker:
                entry["section_marker"] = marker

            result.append(entry)
        return result

    @classmethod
    def parse_logs_from_list(cls, logs: list):
        parsed_logs = []
        for entry in logs:
            msg = entry.get("@message", "")
            ts_existing = entry.get("@timestamp")
            lvl_existing = entry.get("@level")

            ts, lvl = cls.extract_timestamp_level(msg, ts_existing, lvl_existing)
            if ts:
                entry["@timestamp"] = ts
            if lvl:
                entry["@level"] = lvl

            parsed_logs.append(entry)

        # --- заполняем отсутствующие timestamp ---
        parsed_logs = cls.fill_missing_timestamps(parsed_logs)

        # --- маркируем секции ---
        parsed_logs = cls.mark_section_boundaries(parsed_logs)

        return parsed_logs
