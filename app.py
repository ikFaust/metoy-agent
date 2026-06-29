from __future__ import annotations

import re
import time
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from edutoy.agent import EduToyAgent


ROOT = Path(__file__).parent
INDEX_PATH = ROOT / "data" / "edutoy" / "documents.jsonl"

st.set_page_config(page_title="Metoy 科学小导师", page_icon="ET", layout="wide", initial_sidebar_state="expanded")


def render_html(markup: str, target=None) -> None:
    renderer = target or st
    if hasattr(renderer, "html"):
        renderer.html(markup)
    else:
        renderer.markdown(markup, unsafe_allow_html=True)


def inline_markdown_html(text: str) -> str:
    html = escape(text)
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    html = re.sub(r"`([^`]+)`", r"<code>\1</code>", html)
    return html


def markdown_to_bubble_html(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parts: list[str] = ['<div class="md-content">']
    list_mode: str | None = None

    def close_list() -> None:
        nonlocal list_mode
        if list_mode:
            parts.append(f"</{list_mode}>")
            list_mode = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            close_list()
            continue

        heading = re.match(r"^(#{2,3})\s+(.+)$", line)
        if heading:
            close_list()
            tag = "h2" if heading.group(1) == "##" else "h3"
            parts.append(f"<{tag}>{inline_markdown_html(heading.group(2))}</{tag}>")
            continue

        bullet = re.match(r"^[-*]\s*(.+)$", line)
        if bullet:
            if list_mode != "ul":
                close_list()
                parts.append("<ul>")
                list_mode = "ul"
            parts.append(f"<li>{inline_markdown_html(bullet.group(1))}</li>")
            continue

        numbered = re.match(r"^\d+[.、]\s*(.+)$", line)
        if numbered:
            if list_mode != "ol":
                close_list()
                parts.append("<ol>")
                list_mode = "ol"
            parts.append(f"<li>{inline_markdown_html(numbered.group(1))}</li>")
            continue

        close_list()
        parts.append(f"<p>{inline_markdown_html(line)}</p>")

    close_list()
    parts.append("</div>")
    return "".join(parts)


render_html(
    """
    <style>
    .stApp {
        background: #f7f8fb;
        color: #222733;
    }
    .block-container {
        max-width: 1180px;
        padding-top: 1.2rem;
        padding-bottom: 6rem;
    }
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu, footer { visibility: hidden; height: 0; }
    .stDeployButton,
    div[data-testid="stDeployButton"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
    }
    div[data-testid="stToolbar"] {
        visibility: hidden !important;
        height: 0 !important;
        background: transparent !important;
    }
    button[data-testid="stExpandSidebarButton"],
    div[data-testid="collapsedControl"] {
        visibility: visible !important;
        opacity: 1 !important;
        position: fixed !important;
        top: 12px !important;
        left: 12px !important;
        z-index: 999999 !important;
        background: #ffffff !important;
        border: 1px solid #dfe6f4 !important;
        border-radius: 12px !important;
        box-shadow: 0 12px 28px rgba(42, 56, 84, 0.16) !important;
        padding: 4px !important;
    }
    button[data-testid="stExpandSidebarButton"] {
        width: 42px !important;
        height: 42px !important;
        min-height: 42px !important;
    }
    div[data-testid="collapsedControl"] button,
    div[data-testid="collapsedControl"] svg,
    button[data-testid="stExpandSidebarButton"] span,
    button[data-testid="stExpandSidebarButton"] svg {
        width: 28px !important;
        height: 28px !important;
        color: #293042 !important;
    }
    button[data-testid="stExpandSidebarButton"]:hover {
        background: #eaf0ff !important;
        border-color: #cbd8ff !important;
    }
    section[data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid #e5e8f0;
    }
    section[data-testid="stSidebar"] * { color: #293042 !important; }
    .brand {
        font-size: 1.15rem;
        font-weight: 800;
        color: #293042;
        margin-bottom: 0.35rem;
    }
    .side-note {
        color: #788195;
        font-size: 0.88rem;
        line-height: 1.45;
        margin-bottom: 1rem;
    }
    div[data-testid="stButton"] > button,
    button[data-testid="baseButton-primary"],
    button[data-testid="baseButton-secondary"] {
        border-radius: 12px !important;
        min-height: 40px;
        font-weight: 700 !important;
        background: #f3f5fb !important;
        border: 1px solid #e2e6f0 !important;
        color: #293042 !important;
        box-shadow: none !important;
    }
    div[data-testid="stButton"] > button:hover {
        background: #eaf0ff !important;
        border-color: #cbd8ff !important;
    }
    div[data-testid="stButton"] > button * { color: #293042 !important; }
    div[data-testid="stButton"] > button[title="删除这条历史对话"] {
        min-width: 42px !important;
        padding-left: 0 !important;
        padding-right: 0 !important;
        font-size: 1.08rem !important;
    }
    div[data-testid="stButton"] > button[title="删除这条历史对话"]:hover {
        background: #fff1f2 !important;
        border-color: #fecdd3 !important;
        color: #be123c !important;
    }
    div[data-testid="stButton"] > button[title="打开教具商店"] {
        background: linear-gradient(135deg, #3157f6, #2fc8b6) !important;
        border-color: transparent !important;
        color: #ffffff !important;
    }
    div[data-testid="stButton"] > button[title="打开教具商店"] * {
        color: #ffffff !important;
    }
    .store-frame-title {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 12px;
    }
    .store-frame-title h1 {
        color: #293042;
        font-size: 1.25rem;
        margin: 0;
    }
    .store-frame-title span {
        color: #788195;
        font-size: 0.9rem;
    }
    .quick-actions {
        display: flex;
        justify-content: flex-end;
        margin: -0.25rem 0 0.75rem;
    }
    .topline {
        display: flex;
        align-items: center;
        gap: 12px;
        margin: 0.2rem 0 1.4rem 0;
    }
    .bot-avatar, .user-avatar {
        width: 46px;
        height: 46px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        flex: 0 0 auto;
        font-weight: 900;
        color: #ffffff;
        box-shadow: 0 10px 24px rgba(50, 88, 180, 0.18);
    }
    .bot-avatar {
        background: linear-gradient(135deg, #3b82f6, #7c5cff);
    }
    .user-avatar {
        background: linear-gradient(135deg, #4f7cff, #2fd0b5);
    }
    .speaker {
        color: #737c92;
        font-size: 0.98rem;
        margin-bottom: 0.35rem;
    }
    .chat-row {
        display: grid;
        grid-template-columns: 58px minmax(0, 1fr);
        gap: 12px;
        margin: 1.4rem 0;
    }
    .bubble {
        border-radius: 14px;
        padding: 16px 18px;
        line-height: 1.75;
        font-size: 1.02rem;
        white-space: normal;
    }
    .bot-bubble {
        background: linear-gradient(120deg, #ffffff 0%, #f2f5fb 100%);
        border: 1px solid #e4e8f1;
        color: #424a5d;
        box-shadow: 0 18px 42px rgba(42, 56, 84, 0.08);
    }
    .user-bubble {
        background: linear-gradient(120deg, #ececff 0%, #dddffd 100%);
        border: 1px solid #cfd4ff;
        color: #222733;
        max-width: 680px;
    }
    .md-content {
        color: inherit;
        line-height: 1.75;
    }
    .md-content p {
        margin: 0 0 0.8rem;
    }
    .md-content p:last-child {
        margin-bottom: 0;
    }
    .md-content strong {
        color: #293042;
        font-weight: 850;
    }
    .md-content h2,
    .md-content h3 {
        color: #293042;
        font-weight: 900;
        line-height: 1.3;
        margin: 1.05rem 0 0.55rem;
    }
    .md-content h2 { font-size: 1.36rem; }
    .md-content h3 { font-size: 1.08rem; }
    .md-content ul,
    .md-content ol {
        margin: 0.2rem 0 0.9rem 1.2rem;
        padding: 0;
    }
    .md-content li {
        margin: 0.18rem 0;
        padding-left: 0.15rem;
    }
    .store-actions {
        display: flex;
        justify-content: flex-start;
        margin-bottom: 0.8rem;
    }
    .cards-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 14px;
        margin: 1.2rem 0 1.1rem 58px;
    }
    .aid-card {
        min-height: 205px;
        background: linear-gradient(180deg, #ffffff 0%, #f7f9ff 100%);
        border: 1px solid #dfe6f4;
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 16px 36px rgba(42, 56, 84, 0.08);
        position: relative;
        overflow: hidden;
    }
    .aid-card::before {
        content: "";
        position: absolute;
        inset: 0 0 auto 0;
        height: 4px;
        background: linear-gradient(90deg, #4f7cff, #2fd0b5);
    }
    .aid-head {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }
    .aid-icon {
        width: 38px;
        height: 38px;
        border-radius: 12px;
        display: grid;
        place-items: center;
        color: #ffffff;
        font-weight: 900;
        background: linear-gradient(135deg, #3157f6, #2fc8b6);
        box-shadow: 0 10px 22px rgba(49, 87, 246, 0.18);
        flex: 0 0 auto;
    }
    .aid-title {
        color: #253047;
        font-size: 1rem;
        font-weight: 850;
        line-height: 1.3;
    }
    .aid-tag {
        display: inline-flex;
        width: fit-content;
        border: 1px solid #d8e0f0;
        background: #eef4ff;
        color: #42506a;
        border-radius: 999px;
        padding: 4px 8px;
        font-size: 0.78rem;
        font-weight: 750;
        margin-bottom: 10px;
    }
    .aid-desc {
        color: #566174;
        line-height: 1.55;
        font-size: 0.92rem;
        margin-bottom: 12px;
    }
    .aid-meta {
        color: #6a7487;
        display: block;
        line-height: 1.5;
        font-size: 0.84rem;
    }
    .aid-source {
        color: #8791a3;
        display: block;
        margin-top: 10px;
        font-size: 0.76rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
    }
    .metric-strip {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 1rem;
    }
    .pill {
        background: #ffffff;
        border: 1px solid #e3e8f2;
        border-radius: 999px;
        color: #5d677b;
        padding: 7px 11px;
        font-size: 0.86rem;
    }
    div[data-testid="stTabs"] div[role="tablist"], div[role="tablist"] {
        background: #f0f3f9 !important;
        border: 1px solid #e0e5ef !important;
        border-radius: 12px !important;
        padding: 6px !important;
    }
    button[role="tab"] {
        background: #ffffff !important;
        border: 1px solid #e0e5ef !important;
        border-radius: 10px !important;
        color: #293042 !important;
    }
    button[role="tab"] * { color: #293042 !important; font-weight: 700 !important; }
    button[role="tab"][aria-selected="true"] {
        background: #3157f6 !important;
        border-color: #3157f6 !important;
    }
    button[role="tab"][aria-selected="true"] * { color: #ffffff !important; }
    .source-box {
        border-left: 4px solid #4467f6;
        padding: 12px 14px;
        background: #ffffff;
        border-radius: 0 12px 12px 0;
        margin: 10px 0;
        color: #3c4558;
    }
    .agent-grid {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 12px;
        margin: 14px 0 18px;
    }
    .agent-node {
        background: #ffffff;
        border: 1px solid #dfe6f4;
        border-radius: 14px;
        padding: 14px;
        min-height: 116px;
        box-shadow: 0 12px 26px rgba(42, 56, 84, 0.06);
    }
    .agent-node b {
        display: block;
        color: #253047;
        margin-bottom: 8px;
        font-size: 0.95rem;
    }
    .agent-node span {
        display: block;
        color: #667085;
        line-height: 1.45;
        font-size: 0.86rem;
    }
    .trace-strip {
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 10px;
        margin: 10px 0 16px;
    }
    .trace-metric {
        background: #ffffff;
        border: 1px solid #dfe6f4;
        border-radius: 14px;
        padding: 12px 14px;
        color: #293042;
    }
    .trace-metric strong {
        display: block;
        font-size: 1.05rem;
        margin-bottom: 2px;
    }
    .trace-metric span {
        color: #788195;
        font-size: 0.82rem;
    }
    .trace-timeline {
        display: flex;
        flex-direction: column;
        gap: 10px;
        margin: 12px 0 18px;
    }
    .trace-card {
        display: grid;
        grid-template-columns: 42px minmax(0, 1fr);
        gap: 12px;
        background: #ffffff;
        border: 1px solid #dfe6f4;
        border-radius: 14px;
        padding: 13px 14px;
        box-shadow: 0 10px 22px rgba(42, 56, 84, 0.05);
    }
    .trace-index {
        width: 34px;
        height: 34px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #edf2ff;
        color: #3157f6;
        font-weight: 900;
        border: 1px solid #cbd8ff;
    }
    .trace-card.done .trace-index,
    .trace-card.pass .trace-index { background: #eafaf4; color: #1d8f5b; border-color: #bdebd8; }
    .trace-card.skipped .trace-index { background: #f3f5fb; color: #8791a3; border-color: #dfe6f4; }
    .trace-card.review .trace-index,
    .trace-card.unknown .trace-index { background: #fff5dc; color: #a16207; border-color: #f2d58b; }
    .trace-title {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        color: #293042;
        font-weight: 850;
        margin-bottom: 4px;
    }
    .trace-kind {
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        background: #f4f7ff;
        color: #5d677b;
        font-size: 0.74rem;
        padding: 2px 8px;
        border: 1px solid #e0e7ff;
    }
    .trace-summary {
        color: #3f485c;
        line-height: 1.55;
        margin-bottom: 4px;
    }
    .trace-detail {
        color: #788195;
        line-height: 1.5;
        font-size: 0.88rem;
    }
    .check-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 12px;
        margin-top: 12px;
    }
    .check-card {
        background: #ffffff;
        border: 1px solid #dfe6f4;
        border-radius: 14px;
        padding: 12px 14px;
        color: #3d4659;
    }
    .check-pass {
        border-left: 5px solid #24a66a;
    }
    .check-review {
        border-left: 5px solid #dc8a18;
    }
    .small-muted {
        color: #768196;
        font-size: 0.85rem;
        line-height: 1.55;
    }
    .thinking-dots {
        display: inline-flex;
        gap: 5px;
        align-items: center;
        min-height: 12px;
    }
    .thinking-dots span {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: #7d8aa3;
        display: inline-block;
        animation: pulseDot 1.1s infinite ease-in-out;
    }
    .thinking-bubble {
        display: inline-flex;
        align-items: center;
        gap: 10px;
        width: fit-content;
        max-width: 360px;
        padding: 10px 13px !important;
        line-height: 1.35 !important;
        min-height: auto;
        font-size: 0.9rem !important;
    }
    .thinking-bubble .small-muted {
        font-size: 0.78rem;
        line-height: 1.2;
    }
    .thinking-dots span:nth-child(2) { animation-delay: 0.16s; }
    .thinking-dots span:nth-child(3) { animation-delay: 0.32s; }
    .typing-cursor {
        display: inline-block;
        width: 8px;
        color: #3157f6;
        animation: blinkCursor 0.9s steps(2, start) infinite;
    }
    @keyframes pulseDot {
        0%, 80%, 100% { opacity: 0.35; transform: translateY(0); }
        40% { opacity: 1; transform: translateY(-3px); }
    }
    @keyframes blinkCursor {
        0%, 45% { opacity: 1; }
        46%, 100% { opacity: 0; }
    }
    div[data-testid="stAlert"] {
        background: #fff8e8 !important;
        border: 1px solid #e6bd67 !important;
        border-radius: 12px !important;
        color: #473719 !important;
    }
    div[data-testid="stAlert"] * { color: #473719 !important; }
    @media (max-width: 860px) {
        .cards-grid { grid-template-columns: 1fr; margin-left: 0; }
        .agent-grid, .check-grid, .trace-strip { grid-template-columns: 1fr; }
        .chat-row { grid-template-columns: 46px minmax(0, 1fr); }
        .bot-avatar, .user-avatar { width: 38px; height: 38px; }
    }
    @media (min-width: 861px) and (max-width: 1120px) {
        .cards-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    </style>
    """
)


@st.cache_resource
def get_agent() -> EduToyAgent:
    return EduToyAgent(INDEX_PATH)


@st.cache_data
def index_count() -> int:
    if not INDEX_PATH.exists():
        return 0
    return sum(1 for line in INDEX_PATH.read_text(encoding="utf-8").splitlines() if line.strip())


def run_agent(
    prompt: str,
    mode: str,
    history: list[dict[str, str]] | None = None,
    level: str = "自动识别",
    topic: str = "",
    constraints: str = "",
    fast_mode: bool = False,
):
    return get_agent().run(
        message=prompt,
        level=level,
        mode=mode,
        topic_hint=topic,
        constraints=constraints,
        history=history or [],
        fast_mode=fast_mode,
    )


def should_use_fast_mode(prompt: str, response_mode: str) -> bool:
    if response_mode == "极速模式":
        return True
    if response_mode == "智能模式":
        return False
    smart_words = [
        "详细",
        "深入",
        "一步步",
        "带我做",
        "设计",
        "方案",
        "实验报告",
        "课程",
        "教案",
        "为什么",
        "怎么证明",
        "改进",
        "评价",
    ]
    fast_words = ["有哪些教具", "有什么教具", "有啥教具", "介绍一下你们的教具", "教具清单"]
    follow_up_words = ["第", "这个", "那个", "刚才", "上面", "下一步", "继续", "接着", "往下"]
    if any(word in prompt for word in fast_words):
        return True
    if any(word in prompt for word in follow_up_words):
        return False
    if any(word in prompt for word in smart_words):
        return False
    return len(prompt.strip()) <= 18


def summarize_title_rule(prompt: str) -> str:
    text = prompt.strip().replace("\n", " ")
    prefixes = ["请问", "我想", "帮我", "能不能", "可以", "你能"]
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
    replacements = {
        "介绍一下你们的": "",
        "介绍一下": "",
        "怎么形成的": "形成",
        "是怎么形成的": "形成",
        "带我一步步做": "实验",
        "带我做": "实验",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.strip(" ，。！？?：:")
    if not text:
        return "新的科学对话"
    return text[:12]


def summarize_title_ai(prompt: str, answer: str, use_ai: bool) -> str:
    fallback = summarize_title_rule(prompt)
    if not use_ai or not get_agent().llm.available:
        return fallback
    system = "你是对话标题生成器。只输出一个中文短标题，6到10个字，不要标点，不要解释。"
    user = f"用户问题：{prompt[:160]}\n助手回答摘要：{answer[:220]}"
    try:
        title = get_agent().llm.complete(system, user).strip()
    except Exception:
        return fallback
    title = title.replace("\n", " ").strip(" ，。！？?：:\"'“”")
    return title[:14] or fallback


def seed_conversation() -> list[dict[str, str]]:
    return [
        {
            "role": "assistant",
            "content": "你好呀！我是 Metoy 科学小导师，会从本地教材、论文和教具说明书里找资料，用有趣的方式带你探索科学世界的奥秘～",
        }
    ]


def init_sessions() -> None:
    if "sessions" not in st.session_state:
        st.session_state["sessions"] = [
            {
                "title": "新的科学对话",
                "messages": seed_conversation(),
                "last_result": None,
                "title_generated": False,
            }
        ]
    if "active_session" not in st.session_state:
        st.session_state["active_session"] = 0
    if "pending_prompt" not in st.session_state:
        st.session_state["pending_prompt"] = None
    if "active_view" not in st.session_state:
        st.session_state["active_view"] = "chat"


def active_session() -> dict:
    init_sessions()
    return st.session_state["sessions"][st.session_state["active_session"]]


def add_session() -> None:
    st.session_state["sessions"].insert(
        0,
        {
            "title": "新的科学对话",
            "messages": seed_conversation(),
            "last_result": None,
            "title_generated": False,
        },
    )
    st.session_state["active_session"] = 0


def delete_session(index: int) -> None:
    sessions = st.session_state["sessions"]
    if not sessions:
        add_session()
        return
    del sessions[index]
    if not sessions:
        add_session()
        return
    active = st.session_state["active_session"]
    if index < active:
        st.session_state["active_session"] = active - 1
    elif index == active:
        st.session_state["active_session"] = min(index, len(sessions) - 1)
        st.session_state["pending_prompt"] = None


def render_message(message: dict[str, str]) -> None:
    is_bot = message["role"] == "assistant"
    avatar = "M" if is_bot else "你"
    avatar_class = "bot-avatar" if is_bot else "user-avatar"
    bubble_class = "bot-bubble" if is_bot else "user-bubble"
    speaker = "Metoy科学小导师" if is_bot else "RootUser"
    content = markdown_to_bubble_html(message["content"])
    render_html(
        f"""
        <div class="chat-row">
          <div class="{avatar_class}">{avatar}</div>
          <div>
            <div class="speaker">{speaker}</div>
            <div class="bubble {bubble_class}">{content}</div>
          </div>
        </div>
        """
    )


def assistant_message_html(content: str, cursor: bool = False) -> str:
    cursor_html = '<span class="typing-cursor">|</span>' if cursor else ""
    content_html = markdown_to_bubble_html(content)
    return f"""
    <div class="chat-row">
      <div class="bot-avatar">M</div>
      <div>
        <div class="speaker">Metoy科学小导师</div>
        <div class="bubble bot-bubble">{content_html}{cursor_html}</div>
      </div>
    </div>
    """


def render_streaming_message(content: str) -> None:
    placeholder = st.empty()
    shown = ""
    if not content:
        render_html(assistant_message_html("", cursor=False), placeholder)
        return
    chunk_size = 2 if len(content) < 220 else 4
    delay = 0.018 if len(content) < 500 else 0.01
    for start in range(0, len(content), chunk_size):
        shown = content[: start + chunk_size]
        render_html(assistant_message_html(shown, cursor=True), placeholder)
        time.sleep(delay)
    render_html(assistant_message_html(content, cursor=False), placeholder)


def render_thinking(response_mode: str, placeholder=None):
    slot = placeholder or st.empty()
    render_html(
        f"""
        <div class="chat-row">
          <div class="bot-avatar">M</div>
          <div>
            <div class="speaker">Metoy科学小导师</div>
            <div class="bubble bot-bubble thinking-bubble">
              <div class="thinking-dots"><span></span><span></span><span></span></div>
              <div class="small-muted">{escape(response_mode)} 思考中</div>
            </div>
          </div>
        </div>
        """,
        slot,
    )
    return slot


def render_cards(cards: list[dict[str, str]]) -> None:
    if not cards:
        return
    render_html('<div class="cards-grid">')
    for card in cards:
        title = escape(card.get("title", "未命名教具"))
        category = escape(card.get("category", "科学教具"))
        level = escape(card.get("level", "通用"))
        knowledge = escape(card.get("knowledge", "科学探究"))
        description = escape(card.get("description", "用于课堂科学探究活动。"))
        source = escape(Path(card.get("source", "")).name or "本地教具说明书")
        icon = escape(card.get("icon", "科"))
        render_html(
            f"""
            <div class="aid-card">
              <div class="aid-head">
                <div class="aid-icon">{icon}</div>
                <div class="aid-title">{title}</div>
              </div>
              <div class="aid-tag">{category}</div>
              <div class="aid-desc">{description}</div>
              <span class="aid-meta">适合：{level}</span>
              <span class="aid-meta">知识点：{knowledge}</span>
              <span class="aid-source">来源：{source}</span>
            </div>
            """
        )
    render_html("</div>")


def render_card_actions(cards: list[dict[str, str]], session: dict, response_mode: str, key_prefix: str) -> None:
    if not cards:
        return
    card_cols = st.columns(2)
    for idx, card in enumerate(cards):
        with card_cols[idx % 2]:
            if st.button(card["action"], key=f"{key_prefix}_{idx}", use_container_width=True):
                follow_up = f"我想用《{card['title']}》学习{card['knowledge']}，请带我一步步做实验。"
                session["messages"].append({"role": "user", "content": follow_up})
                st.session_state["pending_prompt"] = {
                    "session_index": st.session_state["active_session"],
                    "prompt": follow_up,
                    "topic": card["knowledge"],
                    "response_mode": response_mode,
                }
                st.rerun()


def render_agent_architecture(result) -> None:
    quality = result.quality_checks or {}
    nodes = [
        ("1. Profile", "整理学生问题、历史上下文、学段和约束，形成 AgentState。"),
        ("2. Router", f"当前意图：{quality.get('intent', result.intent)}；路线：{quality.get('route', 'unknown')}。"),
        ("3. Toolbox", "按意图选择工具，不把所有问题都直接丢给模型。"),
        ("4. RAG / Catalog", "从本地教材、论文、教具说明书检索依据。"),
        ("5. Reason / Design", "知识点先解释；实验需求再生成活动、材料和观察任务。"),
        ("6. Safety", "检查明火、尖锐物、强光、电路、低龄陪同等风险。"),
        ("7. Generator", "调用 GLM 或本地规则，生成学生版/开发者版回答。"),
        ("8. Verifier", f"质量状态：{quality.get('status', 'unknown')}，得分：{quality.get('score', '-')}."),
    ]
    render_html('<div class="agent-grid">')
    for title, desc in nodes:
        render_html(
            f"""
            <div class="agent-node">
              <b>{escape(title)}</b>
              <span>{escape(desc)}</span>
            </div>
            """
        )
    render_html("</div>")

    st.markdown("#### 本轮工具注册表")
    for tool in result.tool_summary or []:
        st.markdown(f"- **{tool['name']}**：{tool['role']}")


def render_agent_trajectory(result) -> None:
    quality = result.quality_checks or {}
    used_tools = quality.get("used_tools", [])
    trajectory = getattr(result, "trajectory", None) or []
    render_html(
        f"""
        <div class="trace-strip">
          <div class="trace-metric"><strong>{escape(result.intent)}</strong><span>识别意图</span></div>
          <div class="trace-metric"><strong>{len(used_tools)}</strong><span>调用/启用工具</span></div>
          <div class="trace-metric"><strong>{len(result.documents)}</strong><span>本地资料命中</span></div>
          <div class="trace-metric"><strong>{escape(str(quality.get("score", "-")))}</strong><span>质量得分</span></div>
        </div>
        """
    )

    if not trajectory:
        st.info("当前结果还没有结构化轨迹。可以重新运行一次 Agent。")
        return

    render_html('<div class="trace-timeline">')
    for idx, item in enumerate(trajectory, start=1):
        status = escape(str(item.get("status", "unknown")))
        kind = escape(str(item.get("kind", "step")))
        phase = escape(str(item.get("phase", f"步骤 {idx}")))
        summary = escape(str(item.get("summary", "")))
        detail = escape(str(item.get("detail", "")))
        render_html(
            f"""
            <div class="trace-card {status}">
              <div class="trace-index">{idx}</div>
              <div>
                <div class="trace-title">{phase}<span class="trace-kind">{kind} · {status}</span></div>
                <div class="trace-summary">{summary}</div>
                <div class="trace-detail">{detail}</div>
              </div>
            </div>
            """
        )
    render_html("</div>")

    with st.expander("查看原始运行日志 steps"):
        for idx, step in enumerate(result.steps, start=1):
            st.markdown(f"#### {idx}. {step.name} · {step.kind}")
            st.write(step.detail)
            if step.output.strip().startswith("{"):
                st.code(step.output, language="json")
            else:
                st.write(step.output)


def render_quality_checks(result) -> None:
    quality = result.quality_checks or {}
    st.metric("质量得分", quality.get("score", "-"), quality.get("status", "unknown"))
    used_tools = "、".join(quality.get("used_tools", [])) or "无"
    render_html(f'<div class="small-muted">本轮工具：{escape(used_tools)}</div>')
    render_html('<div class="check-grid">')
    for check in quality.get("checks", []):
        cls = "check-pass" if check.get("pass") else "check-review"
        status = "通过" if check.get("pass") else "需要复核"
        render_html(
            f"""
            <div class="check-card {cls}">
              <strong>{escape(check.get("name", "检查项"))} · {status}</strong><br>
              <span>{escape(str(check.get("detail", "")))}</span>
            </div>
            """
        )
    render_html("</div>")
    issues = quality.get("issues") or []
    if issues:
        st.warning("；".join(issues))
    else:
        st.success("本轮回答通过基础校验。")


def render_store() -> None:
    render_html(
        """
        <div class="store-frame-title">
          <div>
            <h1>Metoy 教具商店</h1>
            <span>从智能体里直接查看教具和学习产品页面</span>
          </div>
        </div>
        """
    )
    if not (ROOT / "static" / "store" / "商城.html").exists():
        st.error("没有找到商店网页文件。")
        return
    store_html = (ROOT / "static" / "store" / "商城.html").read_text(encoding="utf-8")
    store_html = store_html.replace(
        "<head>",
        '<head><base href="/app/static/store/">',
        1,
    )
    for page_name in ["彝历漆盘·星斗棋.html", "傣族竹楼榫卯积木+声学探索.html"]:
        page_path = ROOT / "static" / "store" / page_name
        if page_path.exists():
            page_html = page_path.read_text(encoding="utf-8").replace(
                "<head>",
                '<head><base href="/app/static/store/">',
                1,
            )
            store_html = store_html.replace(
                f'<iframe src="{page_name}"></iframe>',
                f'<iframe srcdoc="{escape(page_html, quote=True)}"></iframe>',
            )
    components.html(store_html, height=760, scrolling=True)


init_sessions()

view_param = st.query_params.get("view")
if view_param in {"chat", "store"}:
    st.session_state["active_view"] = view_param

with st.sidebar:
    render_html('<div class="brand">Metoy 科学小导师</div>')
    render_html('<div class="side-note">左侧查看历史对话，中间直接聊天。教具清单会严格来自本地说明书。</div>')
    if st.session_state.get("active_view") == "store":
        st.link_button("← 返回聊天", "?view=chat", use_container_width=True)
    top_actions = st.columns([0.78, 0.22], gap="small")
    with top_actions[0]:
        if st.button("新建对话", use_container_width=True):
            st.session_state["active_view"] = "chat"
            st.query_params["view"] = "chat"
            add_session()
            st.rerun()
    with top_actions[1]:
        if st.button("🛒", key="sidebar_store_button", use_container_width=True, help="打开教具商店"):
            st.session_state["active_view"] = "store"
            st.query_params["view"] = "store"
            st.rerun()

    mode = st.radio("模式", ["学生聊天", "开发者控制台"], label_visibility="collapsed")
    if st.session_state.get("last_mode") != mode and st.session_state.get("active_view") != "store":
        st.session_state["active_view"] = "chat" if mode == "学生聊天" else "developer"
        st.session_state["last_mode"] = mode
    response_mode = st.radio(
        "学生回答模式",
        ["自动模式", "极速模式", "智能模式"],
        help="自动模式会按问题复杂度选择快路径或 GLM 深度生成；极速模式秒回；智能模式更慢但更会组织语言和推理。",
    )
    st.divider()
    st.caption("历史对话")
    for idx, session in enumerate(st.session_state["sessions"]):
        title = session["title"] or f"对话 {idx + 1}"
        row_cols = st.columns([0.78, 0.22], gap="small")
        with row_cols[0]:
            if st.button(title[:18], key=f"session_{idx}", use_container_width=True):
                st.session_state["active_session"] = idx
                st.rerun()
        with row_cols[1]:
            if st.button("🗑", key=f"delete_session_{idx}", use_container_width=True, help="删除这条历史对话"):
                delete_session(idx)
                st.rerun()

    st.divider()
    st.caption(f"本地资料：{index_count()} 条")
    st.caption("GLM：" + ("已配置" if get_agent().llm.available else "未配置"))

if st.session_state.get("active_view") == "store":
    render_store()
elif mode == "学生聊天":
    st.session_state["active_view"] = "chat"
    session = active_session()
    render_html(
        """
        <div class="topline">
          <div class="bot-avatar">M</div>
          <div>
            <div style="font-size:1.18rem;font-weight:800;color:#293042;">Metoy科学小导师</div>
            <div style="color:#788195;">直接问知识点、教具清单，或让它带你做实验</div>
          </div>
        </div>
        """
    )
    render_html(
        f"""
        <div class="metric-strip">
          <div class="pill">本地资料 {index_count()} 条</div>
          <div class="pill">RAG 检索</div>
          <div class="pill">教具目录工具</div>
          <div class="pill">{response_mode}</div>
          <div class="pill">GLM {'已配置' if get_agent().llm.available else '未配置'}</div>
        </div>
        """
    )

    for message in session["messages"]:
        render_message(message)

    last_result = session.get("last_result")
    if last_result and last_result.cards:
        render_cards(last_result.cards)
        render_card_actions(last_result.cards, session, response_mode, f"start_card_{st.session_state['active_session']}")

    prompt = st.chat_input("继续对话... 例如：你们有哪些教具？")
    if prompt:
        session["messages"].append({"role": "user", "content": prompt})
        if session["title"] == "新的科学对话":
            session["title"] = summarize_title_rule(prompt)
        st.session_state["pending_prompt"] = {
            "session_index": st.session_state["active_session"],
            "prompt": prompt,
            "topic": "",
            "response_mode": response_mode,
        }
        st.rerun()

    pending = st.session_state.get("pending_prompt")
    if pending and pending["session_index"] == st.session_state["active_session"]:
        thinking_slot = render_thinking(pending["response_mode"])
        fast_mode = should_use_fast_mode(pending["prompt"], pending["response_mode"])
        result = run_agent(
            pending["prompt"],
            mode="student",
            history=session["messages"],
            topic=pending.get("topic", ""),
            fast_mode=fast_mode,
        )
        thinking_slot.empty()
        render_streaming_message(result.answer)
        if result.cards:
            render_cards(result.cards)
            render_card_actions(result.cards, session, pending["response_mode"], f"new_card_{st.session_state['active_session']}_{len(session['messages'])}")
        session["messages"].append({"role": "assistant", "content": result.answer})
        session["last_result"] = result
        if not session.get("title_generated"):
            session["title"] = summarize_title_ai(
                pending["prompt"],
                result.answer,
                use_ai=not fast_mode,
            )
            session["title_generated"] = True
        st.session_state["pending_prompt"] = None

else:
    st.session_state["active_view"] = "developer"
    st.title("开发者控制台")
    st.caption("用于查看 Agent 内部流程、RAG 命中文档和教学方案。学生不会看到这些参数。")
    col_a, col_b = st.columns([0.9, 1.1])
    with col_a:
        dev_level = st.selectbox("学生水平", ["小学", "初中", "高中"], index=1)
        dev_topic = st.text_input("知识点", value="平面镜成像")
        dev_constraints = st.text_area("材料/约束", value="低成本，课堂 20 分钟内完成，尽量用纸板、镜片、尺子和手机。")
        dev_prompt = st.text_area("学生问题/教师需求", value="我想让学生通过一个益智玩具理解平面镜成像的特点，并能自己动手验证。", height=130)
        run_dev = st.button("运行 Agent", type="primary", use_container_width=True)
    with col_b:
        st.info("流程：Profile -> Router -> Tool Registry -> RAG/Catalog -> Reason/Design -> Safety -> Generate -> Verify")
        st.write("这里展示的是轻量级 Agent 工作流。你可以截图架构、轨迹和质量校验，放进大作业报告。")

    if run_dev:
        with st.spinner("正在运行 EduToy Agent..."):
            st.session_state["dev_result"] = run_agent(
                dev_prompt,
                mode="developer",
                level=dev_level,
                topic=dev_topic,
                constraints=dev_constraints,
            )

    result = st.session_state.get("dev_result")
    if result:
        report_tab, arch_tab, trace_tab, docs_tab, quality_tab = st.tabs(["输出方案", "Agent 架构", "Agent 轨迹", "RAG 依据", "质量校验"])
        with report_tab:
            st.caption("当前模式：" + ("GLM Agent" if result.llm_enabled else "本地规则兜底"))
            st.caption(f"识别意图：{result.intent}")
            st.markdown(result.answer)
        with arch_tab:
            render_agent_architecture(result)
        with trace_tab:
            render_agent_trajectory(result)
        with docs_tab:
            for doc in result.documents:
                render_html(
                    f"""
                    <div class="source-box">
                    <strong>{doc.title}</strong> · {doc.category} · {doc.level}<br>
                    {doc.content[:260]}<br>
                    <small>{doc.path}</small>
                    </div>
                    """
                )
        with quality_tab:
            render_quality_checks(result)
