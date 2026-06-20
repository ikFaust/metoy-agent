from __future__ import annotations

import json
import re
from typing import Any


FOLLOW_UP_PATTERN = re.compile(r"(第\s*[一二三四五六七八九十\d]+\s*(种|个|条)?|这个|那个|刚才|上面|下一步|继续|接着|往下|怎么验证|如何验证|怎么证明|怎么做)")
ITEM_PATTERN = re.compile(r"(?:^|\n)\s*(?:[-*]|\d+[.、]|[A-Fa-f][.、])\s*([^\n：:]{2,40})(?:[：:]|，|。|\n|$)")
NUMBER_WORDS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def should_use_llm_context_resolver(message: str, history: list[dict[str, str]]) -> bool:
    if len(history) < 2:
        return False
    compact = re.sub(r"\s+", "", message)
    if len(compact) <= 18:
        return True
    return bool(FOLLOW_UP_PATTERN.search(message))


def build_context_resolver_messages(message: str, history: list[dict[str, str]]) -> tuple[str, str]:
    recent = _compact_history(history)
    latest_assistant = _latest_assistant_message(history)
    system = (
        "你是 Agent 的上下文解析器，只输出 JSON。"
        "你的任务是判断用户当前输入是否依赖上文，并把它改写成一个完整、可执行的问题。"
        "尤其要理解：下一步、继续、接着、这个、那个、第2种、第二个、刚才那个实验。"
        "当用户输入很短或只说怎么验证/怎么做/下一步时，必须优先绑定 latest_assistant_message，而不是更早的话题。"
        "如果 latest_assistant_message 中提到铁、棉花、天平、一样重，用户问怎么验证时，必须解析为验证铁和棉花同重。"
        "禁止把短追问解析到更早的麦克斯韦方程组、电磁感应或其他旧话题，除非用户明确点名。"
        "不要回答学生，只做解析。"
        "JSON 字段：is_follow_up(boolean), status(string), resolved_message(string), reference(string), "
        "intent_hint(string: catalog_query|concept_explanation|experiment_design|clarify|unknown), confidence(number), reason(string)。"
    )
    user = json.dumps(
        {
            "current_user_message": message,
            "latest_assistant_message": latest_assistant,
            "recent_conversation": recent,
            "rules": [
                "latest_assistant_message 是最近上下文，除非用户明确说更早的话题，否则优先使用它。",
                "如果用户问怎么验证/如何证明/怎么做，并且 latest_assistant_message 中有例子或概念，应改写为验证这个最近概念。",
                "如果用户说下一步/继续/接着，并且上一轮 assistant 给过实验建议，应改写为继续上一轮实验的下一步操作。",
                "如果用户说第2种/第二个，应从上一轮列表中找对应项目。",
                "如果能解析，就不要让后续 Agent 重新追问 A/B/C。",
                "如果确实无法解析，is_follow_up=false，resolved_message 保持原话。",
            ],
        },
        ensure_ascii=False,
    )
    return system, user


def normalize_context_result(message: str, result: dict[str, Any]) -> dict[str, Any]:
    is_follow_up = bool(result.get("is_follow_up"))
    resolved = str(result.get("resolved_message") or message).strip()
    reference = str(result.get("reference") or "").strip()
    status = str(result.get("status") or ("resolved_llm" if is_follow_up else "none")).strip()
    intent_hint = str(result.get("intent_hint") or "unknown").strip()
    try:
        confidence = float(result.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if not is_follow_up:
        return {
            "resolved_message": message,
            "reference": "",
            "status": "none",
            "intent_hint": "unknown",
            "confidence": confidence,
            "resolver": "llm",
            "reason": str(result.get("reason") or ""),
        }
    return {
        "resolved_message": resolved or message,
        "reference": reference,
        "status": status if status != "none" else "resolved_llm",
        "intent_hint": intent_hint,
        "confidence": confidence,
        "resolver": "llm",
        "reason": str(result.get("reason") or ""),
    }


def resolve_follow_up_reference(message: str, history: list[dict[str, str]]) -> dict[str, Any]:
    if not FOLLOW_UP_PATTERN.search(message):
        return {"resolved_message": message, "reference": "", "status": "none", "intent_hint": "unknown", "resolver": "rule"}

    recent_assistant = ""
    for item in reversed(history):
        if item.get("role") == "assistant" and item.get("content"):
            recent_assistant = item["content"]
            break
    if not recent_assistant:
        return {"resolved_message": message, "reference": "", "status": "missing_history", "intent_hint": "unknown", "resolver": "rule"}

    items = _extract_items(recent_assistant)
    index = _extract_index(message)
    reference = ""
    if _is_vague_verification(message):
        reference = _extract_verification_focus(recent_assistant) or _extract_last_topic(recent_assistant)
        if reference:
            resolved = f"请设计一个实验来验证：{reference}。不要切换到更早的话题。"
            return {
                "resolved_message": resolved,
                "reference": reference,
                "status": "resolved_latest_verification",
                "intent_hint": "experiment_design",
                "resolver": "rule",
            }
    if _is_next_step(message):
        reference = _extract_next_step(recent_assistant) or _extract_last_topic(recent_assistant)
        if reference:
            resolved = f"继续上一轮内容的下一步：{reference}。请直接给出接下来的操作步骤，不要重新追问方向。"
            return {
                "resolved_message": resolved,
                "reference": reference,
                "status": "resolved_next_step",
                "intent_hint": "experiment_design",
                "resolver": "rule",
            }
    if index and 1 <= index <= len(items):
        reference = items[index - 1]
    elif items and any(token in message for token in ["这个", "那个", "刚才", "上面"]):
        reference = items[-1]

    if not reference:
        return {"resolved_message": message, "reference": "", "status": "unresolved", "intent_hint": "unknown", "resolver": "rule"}

    resolved = f"{message}。这里的指代对象是：{reference}"
    return {
        "resolved_message": resolved,
        "reference": reference,
        "status": "resolved",
        "intent_hint": "concept_explanation",
        "resolver": "rule",
    }


def _compact_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    compact = []
    for item in history[-8:]:
        role = item.get("role", "")
        content = item.get("content", "")
        if not role or not content:
            continue
        compact.append({"role": role, "content": content[-1200:]})
    return compact


def nearest_context_guard(message: str, history: list[dict[str, str]], context: dict[str, Any]) -> dict[str, Any]:
    """Keep very short follow-ups anchored to the latest assistant message."""
    if not _is_vague_verification(message) and not _is_next_step(message):
        return context
    rule_context = resolve_follow_up_reference(message, history)
    if rule_context.get("status") in {"resolved_latest_verification", "resolved_next_step"}:
        resolved = str(context.get("resolved_message", ""))
        reference = str(rule_context.get("reference", ""))
        if reference and reference not in resolved:
            return rule_context | {
                "guardrail": "nearest_assistant_override",
                "llm_context": context,
            }
    return context


def _latest_assistant_message(history: list[dict[str, str]]) -> str:
    for item in reversed(history):
        if item.get("role") == "assistant" and item.get("content"):
            return item["content"][-1600:]
    return ""


def _is_next_step(message: str) -> bool:
    compact = re.sub(r"\s+", "", message)
    return any(token in compact for token in ["下一步", "继续", "接着", "往下"])


def _is_vague_verification(message: str) -> bool:
    compact = re.sub(r"\s+", "", message)
    return any(token in compact for token in ["怎么验证", "如何验证", "怎么证明", "怎么做实验", "怎么做"]) and len(compact) <= 18


def _extract_verification_focus(text: str) -> str:
    patterns = [
        r"就像[^。；\n]*(铁|棉花)[^。；\n]*",
        r"生活中的例子[：:]\s*([^。；\n]{6,140})",
        r"要不要用教具/实验验证[？?]?\s*([^。\n]{0,80})",
        r"验证([^。；\n]{4,100})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return _clean_item(match.group(0 if "就像" in pattern else 1))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if any(token in line for token in ["铁", "棉花", "天平", "一样重", "重量", "质量"]):
            return _clean_item(line)
    return ""


def _extract_next_step(text: str) -> str:
    patterns = [
        r"下一步挑战[：:]\s*([^\n]{4,120})",
        r"下一步[：:]\s*([^\n]{4,120})",
        r"你可以尝试([^\n。]{4,100})",
        r"你想试试这个实验吗[？?]?",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        if match.lastindex:
            return _clean_item(match.group(1))
        return "继续刚才提到的实验验证"
    return ""


def _extract_last_topic(text: str) -> str:
    headings = re.findall(r"##\s*([^\n]{2,30})", text)
    if headings:
        return _clean_item(headings[-1])
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in reversed(lines):
        if len(line) >= 6:
            return _clean_item(line)
    return ""


def _extract_index(message: str) -> int | None:
    digit = re.search(r"第\s*(\d+)\s*(种|个|条)?", message)
    if digit:
        return int(digit.group(1))
    word = re.search(r"第\s*([一二两三四五六七八九十])\s*(种|个|条)?", message)
    if word:
        return NUMBER_WORDS.get(word.group(1))
    return None


def _extract_items(text: str) -> list[str]:
    items = []
    for match in ITEM_PATTERN.finditer(text):
        item = _clean_item(match.group(1))
        if item and item not in items:
            items.append(item)
    if items:
        return items[:12]

    compact = re.sub(r"\s+", "", text)
    named = re.findall(r"([一二三四五六七八九十\d]+)[.、]([^。；\n]{2,32})", compact)
    for _num, value in named:
        item = _clean_item(value)
        if item and item not in items:
            items.append(item)
    return items[:12]


def _clean_item(value: str) -> str:
    value = value.strip(" ：:，。；;、-*")
    value = re.sub(r"^[A-Fa-f][.、]\s*", "", value)
    value = re.sub(r"^\d+[.、]\s*", "", value)
    return value[:90]
