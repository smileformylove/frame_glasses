import re


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def is_dry_run(text: str) -> bool:
    return clean_text(text).startswith("DRY RUN:")


def summarize_git_status(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "git status returned no output"

    branch_line = next((line for line in lines if line.startswith("## ")), "")
    branch = branch_line[3:] if branch_line else "unknown branch"
    status_lines = [line for line in lines if not line.startswith("## ")]
    if not status_lines:
        return f"git clean on {branch}"

    counts = {"modified": 0, "added": 0, "deleted": 0, "renamed": 0, "untracked": 0, "other": 0}
    for line in status_lines:
        code = line[:2]
        if code == "??":
            counts["untracked"] += 1
        elif "M" in code:
            counts["modified"] += 1
        elif "A" in code:
            counts["added"] += 1
        elif "D" in code:
            counts["deleted"] += 1
        elif "R" in code:
            counts["renamed"] += 1
        else:
            counts["other"] += 1

    parts = [f"{key} {value}" for key, value in counts.items() if value]
    detail = ", ".join(parts) if parts else "changes present"
    return f"git {branch}: {detail}"


def summarize_pytest_output(output: str, return_code: int) -> str:
    if is_dry_run(output):
        return clean_text(output)
    text = clean_text(output)
    line = next((line.strip() for line in output.splitlines() if "failed" in line.lower() and "passed" in line.lower()), None)
    if line:
        return clean_text(line)
    failed_case = next((line.strip() for line in output.splitlines() if line.startswith("FAILED ")), None)
    if failed_case:
        return clean_text(failed_case)
    passed_case = next((line.strip() for line in output.splitlines() if "passed" in line.lower()), None)
    if passed_case:
        return clean_text(passed_case)
    if return_code == 0:
        return "tests passed"
    return clean_text(text[:160] or f"tests failed ({return_code})")


def summarize_doctor_output(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    failures = warnings = None
    for line in output.splitlines():
        if line.startswith("Summary:"):
            match = re.search(r"Summary:\s+(\d+)\s+failure\(s\),\s+(\d+)\s+warning\(s\)", line)
            if match:
                failures = int(match.group(1))
                warnings = int(match.group(2))
                break
    if failures is not None:
        if failures == 0 and warnings == 0:
            return "doctor clean"
        return f"doctor failures {failures}, warnings {warnings}"
    return clean_text(output[:160] or "doctor completed")


def summarize_scan_output(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    line = next((line.strip() for line in output.splitlines() if line.startswith("Found ")), None)
    if line:
        return clean_text(line)
    line = next((line.strip() for line in output.splitlines() if "No matching BLE devices found." in line), None)
    if line:
        return clean_text(line)
    return clean_text(output[:160] or "scan completed")


def summarize_task_list_output(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "no tasks output"
    if lines[0] == "No open tasks.":
        return "no open tasks"
    first = lines[0]
    count = len(lines)
    return clean_text(f"{count} open tasks. first: {first}")


def summarize_pair_test_output(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    if "Test message sent successfully." in output:
        return "pair test succeeded"
    if "No matching Frame found." in output:
        return "pair test found no Frame"
    return clean_text(output[:160] or "pair test completed")


def summarize_codex_output(output: str) -> str:
    if is_dry_run(output):
        return clean_text(output)
    text = clean_text(output)
    if not text:
        return "Codex returned no summary"
    for separator in [". ", "\n", " - "]:
        if separator in text:
            first = text.split(separator)[0].strip()
            if len(first) >= 12:
                return first
    return text[:160]
