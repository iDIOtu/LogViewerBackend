import json
import re

def mark_section_boundaries(input_file: str, output_file: str):
    """
    Читает Terraform JSON-лог и маркирует только строки начала/конца
    секций plan / apply (section_marker).
    """
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
            "Apply operation completed"
            "Apply finished",
            "Apply success",
        ],
    }

    marked_logs = []

    with open(input_file, "r") as f:
        for line in f:
            try:
                log = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg = log.get("@message", "")
            marker = None

            # --- STARTS ---
            for sec_type, triggers in START_TRIGGERS.items():
                if any((t in msg) for t in triggers if isinstance(t, str)) or \
                   any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                    marker = f"{sec_type}_start"
                    break

            # --- ENDS ---
            if not marker:
                for sec_type, triggers in END_TRIGGERS.items():
                    if any((t in msg) for t in triggers if isinstance(t, str)) or \
                       any((t.match(msg)) for t in triggers if isinstance(t, re.Pattern)):
                        marker = f"{sec_type}_end"
                        break

            if marker:
                log["section_marker"] = marker

            marked_logs.append(log)

    with open(output_file, "w") as f_out:
        for log in marked_logs:
            f_out.write(json.dumps(log, ensure_ascii=False) + "\n")

    print(f"Готово! Размечено {len([l for l in marked_logs if 'section_marker' in l])} строк. Результат в {output_file}")
mark_section_boundaries("4. tflog.json", "terraform_marked.json")