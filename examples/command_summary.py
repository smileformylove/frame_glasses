import re
from typing import Literal

Locale = Literal['en', 'zh']


def clean_text(text: str) -> str:
    return " ".join(text.strip().split())


def is_dry_run(text: str) -> bool:
    return clean_text(text).startswith("DRY RUN:")


def summarize_git_status(output: str, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "git status returned no output" if locale == 'en' else "git 状态没有输出"

    branch_line = next((line for line in lines if line.startswith("## ")), "")
    branch = branch_line[3:] if branch_line else ("unknown branch" if locale == 'en' else "未知分支")
    status_lines = [line for line in lines if not line.startswith("## ")]
    if not status_lines:
        return f"git clean on {branch}" if locale == 'en' else f"git 干净，分支 {branch}"

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

    if locale == 'en':
        parts = [f"{key} {value}" for key, value in counts.items() if value]
        detail = ", ".join(parts) if parts else "changes present"
        return f"git {branch}: {detail}"

    labels = {
        "modified": "修改",
        "added": "新增",
        "deleted": "删除",
        "renamed": "重命名",
        "untracked": "未跟踪",
        "other": "其他",
    }
    parts = [f"{labels[key]} {value}" for key, value in counts.items() if value]
    detail = "，".join(parts) if parts else "有变更"
    return f"git {branch}：{detail}"


def summarize_pytest_output(output: str, return_code: int, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    text = clean_text(output)
    line = next((line.strip() for line in output.splitlines() if "failed" in line.lower() and "passed" in line.lower()), None)
    if line:
        return clean_text(line) if locale == 'en' else clean_text(line.replace('failed', '失败').replace('passed', '通过').replace('warnings', '警告'))
    failed_case = next((line.strip() for line in output.splitlines() if line.startswith("FAILED ")), None)
    if failed_case:
        return clean_text(failed_case) if locale == 'en' else f"测试失败：{clean_text(failed_case[7:])}"
    passed_case = next((line.strip() for line in output.splitlines() if "passed" in line.lower()), None)
    if passed_case:
        return clean_text(passed_case) if locale == 'en' else clean_text(passed_case.replace('passed', '通过'))
    if return_code == 0:
        return 'tests passed' if locale == 'en' else '测试通过'
    return clean_text(text[:160] or (f'tests failed ({return_code})' if locale == 'en' else f'测试失败（{return_code}）'))


def summarize_doctor_output(output: str, locale: Locale = 'en') -> str:
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
            return 'doctor clean' if locale == 'en' else '环境检查正常'
        return f'doctor failures {failures}, warnings {warnings}' if locale == 'en' else f'环境检查：失败 {failures}，警告 {warnings}'
    return clean_text(output[:160] or ('doctor completed' if locale == 'en' else '环境检查完成'))


def summarize_scan_output(output: str, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    line = next((line.strip() for line in output.splitlines() if line.startswith("Found ")), None)
    if line:
        return clean_text(line) if locale == 'en' else clean_text(line.replace('Found', '找到').replace('device(s)', '个设备'))
    line = next((line.strip() for line in output.splitlines() if "No matching BLE devices found." in line), None)
    if line:
        return clean_text(line) if locale == 'en' else '没有找到匹配的 Frame 设备'
    return clean_text(output[:160] or ('scan completed' if locale == 'en' else '扫描完成'))


def summarize_task_list_output(output: str, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return 'no tasks output' if locale == 'en' else '任务列表没有输出'
    if lines[0] == 'No open tasks.':
        return 'no open tasks' if locale == 'en' else '当前没有未完成任务'
    first = lines[0]
    count = len(lines)
    return clean_text(f"{count} open tasks. first: {first}") if locale == 'en' else clean_text(f"当前 {count} 个任务，第一项：{first}")


def summarize_pair_test_output(output: str, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    if 'Test message sent successfully.' in output:
        return 'pair test succeeded' if locale == 'en' else '连接测试成功'
    if 'No matching Frame found.' in output:
        return 'pair test found no Frame' if locale == 'en' else '连接测试没找到 Frame'
    return clean_text(output[:160] or ('pair test completed' if locale == 'en' else '连接测试完成'))


def summarize_codex_output(output: str, locale: Locale = 'en') -> str:
    if is_dry_run(output):
        return clean_text(output)
    text = clean_text(output)
    if not text:
        return 'Codex returned no summary' if locale == 'en' else 'Codex 没有返回摘要'
    for separator in ['. ', '\n', ' - ']:
        if separator in text:
            first = text.split(separator)[0].strip()
            if len(first) >= 12:
                return first
    return text[:160]
