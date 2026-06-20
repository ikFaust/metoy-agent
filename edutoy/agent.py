from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from edutoy.memory import (
    build_context_resolver_messages,
    nearest_context_guard,
    normalize_context_result,
    resolve_follow_up_reference,
    should_use_llm_context_resolver,
)
from edutoy.tools import list_teaching_aids, safety_check
from futuremajor.llm import GLMClient
from futuremajor.retrieval import Document, LocalRetriever


@dataclass
class EduStep:
    name: str
    kind: str
    detail: str
    output: str


@dataclass
class AgentState:
    message: str
    level: str
    mode: str
    topic_hint: str
    constraints: str
    history: list[dict[str, str]]
    intent: str = "unknown"
    route: str = "undecided"


@dataclass
class EduToyResult:
    answer: str
    plan: dict[str, Any]
    documents: list[Document]
    steps: list[EduStep]
    llm_enabled: bool
    cards: list[dict[str, str]] | None = None
    needs_clarification: bool = False
    intent: str = "unknown"
    quality_checks: dict[str, Any] | None = None
    tool_summary: list[dict[str, str]] | None = None


class EduToyAgent:
    def __init__(self, index_path: str | Path):
        self.retriever = LocalRetriever.from_jsonl(index_path)
        self.llm = GLMClient()
        self.system_prompt = self._load_system_prompt()

    def run(
        self,
        message: str,
        level: str = "自动识别",
        mode: str = "student",
        topic_hint: str = "",
        constraints: str = "",
        history: list[dict[str, str]] | None = None,
        fast_mode: bool = False,
    ) -> EduToyResult:
        history = history or []
        context = self._resolve_context(message, history)
        effective_message = context["resolved_message"]
        if context["reference"] and not topic_hint:
            topic_hint = context["reference"]
        state = AgentState(effective_message, level, mode, topic_hint, constraints, history)
        profile = self._state_snapshot(state)
        steps = [
            EduStep("Profile", "state", "整理学生水平、对话历史、知识点提示和实验约束", self._compact_json(profile)),
        ]
        if context["status"] != "none":
            resolver_name = "LLM Context Resolver" if context.get("resolver") == "llm" else "Rule Memory Fallback"
            steps.append(EduStep("ResolveContext", "memory", f"{resolver_name} 解析同一对话中的追问、指代和下一步意图", self._compact_json(context)))

        classification = self._classify_intent(state)
        if context.get("intent_hint") == "experiment_design" or context["status"] == "resolved_next_step":
            classification = {
                "intent": "experiment_design",
                "route": "memory_continue_experiment" if context["status"] == "resolved_next_step" else "llm_context_follow_up",
                "reason": "上下文解析器判断用户在承接上一轮内容，直接继续任务，不重新追问。",
                "need_llm": self.llm.available,
                "expected_tools": ["local_rag", "experiment_designer", "safety_checker", "llm"],
            }
        elif context.get("intent_hint") == "concept_explanation":
            classification = {
                "intent": "concept_explanation",
                "route": "llm_context_follow_up",
                "reason": "上下文解析器已把追问改写成完整知识点解释问题。",
                "need_llm": self.llm.available,
                "expected_tools": ["local_rag", "llm"],
            }
        state.intent = classification["intent"]
        state.route = classification["route"]
        steps.append(EduStep("ClassifyIntent", "router", "先判断用户真正想做什么，再决定工具和回答路径", self._compact_json(classification)))

        tools = self._tool_registry(state)
        steps.append(EduStep("SelectTools", "toolbox", "根据意图选择本轮可调用工具，避免所有问题都交给大模型", self._compact_json(tools)))

        if state.intent == "catalog_query":
            catalog_docs = self._tool_list_teaching_aids()
            steps.append(
                EduStep(
                    "ListTeachingAids",
                    "tool",
                    "调用本地教具说明书目录工具，只返回知识库里已有的标准教具",
                    "、".join(doc.title for doc in catalog_docs) or "未找到教具说明书",
                )
            )
            answer = self._catalog_answer(catalog_docs)
            quality = self._quality_check(answer, catalog_docs, "", state, used_tools=["list_teaching_aids"])
            steps.append(EduStep("VerifyAnswer", "guardrail", "检查是否基于本地资料、是否有编造教具、是否符合学生入口", self._compact_json(quality)))
            steps.append(EduStep("Respond", "tool", "教具清单属于标准目录查询，直接依据本地说明书返回，不交给模型自由生成", answer))
            return EduToyResult(
                answer=answer,
                plan={"intent": "catalog_query", "tools": ["list_teaching_aids"]},
                documents=catalog_docs,
                steps=steps,
                llm_enabled=self.llm.available,
                cards=self._catalog_cards(catalog_docs),
                intent=state.intent,
                quality_checks=quality,
                tool_summary=tools,
            )

        if state.intent == "clarify":
            answer = self._clarifying_question(effective_message)
            quality = self._quality_check(answer, [], "", state, used_tools=[])
            steps.append(EduStep("VerifyAnswer", "guardrail", "检查追问是否简短、是否没有乱生成实验", self._compact_json(quality)))
            steps.append(EduStep("Clarify", "rule", "问题较宽泛，先追问学习目标", answer))
            return EduToyResult(
                answer=answer,
                plan={"intent": "clarify"},
                documents=[],
                steps=steps,
                llm_enabled=self.llm.available,
                cards=[],
                needs_clarification=True,
                intent=state.intent,
                quality_checks=quality,
                tool_summary=tools,
            )

        use_llm_plan = mode == "developer"
        plan = self._plan(effective_message, level, topic_hint, constraints, history, use_llm=use_llm_plan)
        steps.append(
            EduStep(
                "Plan",
                "llm" if use_llm_plan and self.llm.available else "rule",
                "规划本轮要解释的概念、要检索的资料和要设计的实验；学生端默认走快速规则规划",
                self._compact_json(plan),
            )
        )

        queries = plan.get("retrieval_queries") or [self._build_query(effective_message, level, topic_hint, constraints)]
        docs, retrieval_meta = self._retrieve_with_meta(queries, level)
        steps.append(EduStep("RetrieveMaterials", "tool", "调用本地教材/论文/教具说明书 RAG 检索工具", self._compact_json(retrieval_meta)))

        if state.intent == "concept_explanation":
            answer = self._fast_concept_answer(effective_message, docs) if fast_mode and mode == "student" else self._explain_concept(effective_message, level, topic_hint, history, plan, docs)
            answer = answer or self._fast_concept_answer(effective_message, docs)
            steps.append(
                EduStep(
                    "ExplainConcept",
                    "rule" if fast_mode and mode == "student" else ("llm" if self.llm.available else "rule"),
                    "识别为知识点/原理提问，先讲概念，不默认设计实验",
                    answer[:900],
                )
            )
            quality = self._quality_check(answer, docs, "", state, used_tools=["local_rag", "fast_template"] if fast_mode and mode == "student" else ["local_rag", "llm"])
            steps.append(EduStep("VerifyAnswer", "guardrail", "检查知识讲解是否先讲概念、是否引用本地资料、是否没有误入实验设计", self._compact_json(quality)))
            return EduToyResult(
                answer=answer,
                plan=plan,
                documents=docs,
                steps=steps,
                llm_enabled=self.llm.available,
                cards=[],
                intent=state.intent,
                quality_checks=quality,
                tool_summary=tools,
            )

        design_brief = self._design_brief(effective_message, level, constraints, docs)
        steps.append(EduStep("DesignExperiment", "tool", "把检索资料转成实验/玩具设计约束和候选活动", design_brief))

        safety = self._safety_check(level, design_brief)
        steps.append(EduStep("SafetyCheck", "tool", "根据学生年龄和材料风险生成安全提示", safety))

        if fast_mode and mode == "student":
            answer = self._fallback_answer(effective_message, level, docs, design_brief, safety)
            response_kind = "rule"
            used_tools = ["local_rag", "experiment_designer", "safety_checker", "fast_template"]
        else:
            answer = self._synthesize(effective_message, level, mode, topic_hint, constraints, history, plan, docs, design_brief, safety)
            answer = answer or self._fallback_answer(effective_message, level, docs, design_brief, safety)
            response_kind = "llm" if self.llm.available else "rule"
            used_tools = ["local_rag", "experiment_designer", "safety_checker", "llm"]
        steps.append(EduStep("Respond", response_kind, "面向学生或开发者生成最终回答", answer[:900]))
        quality = self._quality_check(answer, docs, safety, state, used_tools=used_tools)
        steps.append(EduStep("VerifyAnswer", "guardrail", "检查实验是否有安全边界、是否使用本地资料、是否没有把模型猜测当来源", self._compact_json(quality)))

        return EduToyResult(
            answer=answer,
            plan=plan,
            documents=docs,
            steps=steps,
            llm_enabled=self.llm.available,
            cards=[],
            intent=state.intent,
            quality_checks=quality,
            tool_summary=tools,
        )

    def _classify_intent(self, state: AgentState) -> dict[str, Any]:
        if self._is_catalog_query(state.message):
            return {
                "intent": "catalog_query",
                "route": "tool_first",
                "reason": "用户在问有哪些教具/教育用品，需要准确列出本地目录。",
                "need_llm": False,
                "expected_tools": ["list_teaching_aids"],
            }
        if self._needs_clarification(state.message):
            return {
                "intent": "clarify",
                "route": "ask_before_act",
                "reason": "问题过宽，直接设计实验会偏题。",
                "need_llm": False,
                "expected_tools": [],
            }
        if state.mode == "student" and not self._wants_experiment(state.message):
            return {
                "intent": "concept_explanation",
                "route": "rag_then_explain",
                "reason": "学生在问知识点/原理，先解释概念，不默认进入实验设计。",
                "need_llm": self.llm.available,
                "expected_tools": ["local_rag", "llm"],
            }
        return {
            "intent": "experiment_design",
            "route": "rag_tools_generate_verify",
            "reason": "用户明确需要实验、教具、玩法、步骤或开发者教学设计。",
            "need_llm": self.llm.available,
            "expected_tools": ["local_rag", "experiment_designer", "safety_checker", "llm"],
        }

    def _resolve_context(self, message: str, history: list[dict[str, str]]) -> dict[str, Any]:
        fallback = resolve_follow_up_reference(message, history)
        if not self.llm.available or not should_use_llm_context_resolver(message, history):
            return fallback
        system, user = build_context_resolver_messages(message, history)
        raw = self.llm.complete_json(
            system,
            user,
            {
                "is_follow_up": fallback.get("status") not in {"none", "missing_history", "unresolved"},
                "status": fallback.get("status", "none"),
                "resolved_message": fallback.get("resolved_message", message),
                "reference": fallback.get("reference", ""),
                "intent_hint": fallback.get("intent_hint", "unknown"),
                "confidence": 0,
                "reason": "fallback",
            },
        )
        context = normalize_context_result(message, raw)
        context = nearest_context_guard(message, history, context)
        if context["status"] == "none" and fallback.get("status") not in {"none", "missing_history", "unresolved"}:
            return fallback
        if context["status"] == "none":
            return context
        if context.get("confidence", 0) < 0.35 and fallback.get("status") not in {"none", "missing_history", "unresolved"}:
            return fallback
        return context

    def _tool_registry(self, state: AgentState) -> list[dict[str, str]]:
        registry = {
            "catalog_query": [
                ("list_teaching_aids", "读取本地教具说明书目录，回答有哪些标准教具。"),
                ("answer_verifier", "检查教具是否都来自本地资料。"),
            ],
            "clarify": [
                ("clarifier", "把宽泛需求变成可执行的学习目标。"),
                ("answer_verifier", "检查追问是否没有过度生成。"),
            ],
            "concept_explanation": [
                ("local_rag", "检索教材、论文、说明书中的相关概念。"),
                ("glm_generator", "用学生能懂的语言讲解知识点。"),
                ("answer_verifier", "检查是否先讲概念、不乱做实验。"),
            ],
            "experiment_design": [
                ("local_rag", "检索教材、论文、说明书中的依据。"),
                ("experiment_designer", "把资料转成可观察、可操作的活动。"),
                ("safety_checker", "按学段和材料做安全边界检查。"),
                ("glm_generator", "生成学生版或开发者版输出。"),
                ("answer_verifier", "检查来源、安全和任务结构。"),
            ],
        }
        return [{"name": name, "role": role} for name, role in registry.get(state.intent, [])]

    @staticmethod
    def _load_system_prompt() -> str:
        path = Path(__file__).with_name("sys.md")
        if path.exists():
            return path.read_text(encoding="utf-8")
        return ""

    @staticmethod
    def _state_snapshot(state: AgentState) -> dict[str, Any]:
        return {
            "level": state.level,
            "mode": state.mode,
            "topic_hint": state.topic_hint,
            "constraints": state.constraints,
            "message": state.message,
            "recent_history_count": len(state.history[-6:]),
            "intent": state.intent,
            "route": state.route,
        }

    def _plan(
        self,
        message: str,
        level: str,
        topic_hint: str,
        constraints: str,
        history: list[dict[str, str]],
        use_llm: bool = False,
    ) -> dict[str, Any]:
        fallback = {
            "intent": "fast_rule_plan",
            "concepts": [topic_hint or message[:30]],
            "retrieval_queries": [self._build_query(message, level, topic_hint, constraints)],
            "tools": ["local_material_retrieval", "experiment_design", "safety_check"],
            "response_style": "student_dialogue" if level in {"小学", "初中"} else "guided_reasoning",
            "planner": "rule_fast_path",
        }
        if not use_llm or not self.llm.available:
            return fallback

        system = (
            "你是 EduToy Agent 的规划器。只输出 JSON。"
            "根据学生问题、年级水平和材料约束，规划要讲解的核心概念、检索关键词、实验/玩具设计方向和安全关注点。"
            "不要直接回答学生。"
        )
        user = json.dumps(
            {
                "message": message,
                "level": level,
                "topic_hint": topic_hint,
                "constraints": constraints,
                "recent_history": history[-6:],
            },
            ensure_ascii=False,
        )
        try:
            return self.llm.complete_json(system, user, fallback)
        except Exception as exc:
            fallback["llm_error"] = str(exc)
            return fallback

    def _retrieve(self, queries: list[str], level: str) -> list[Document]:
        docs, _meta = self._retrieve_with_meta(queries, level)
        return docs

    def _retrieve_with_meta(self, queries: list[str], level: str) -> tuple[list[Document], dict[str, Any]]:
        docs: list[Document] = []
        seen = set()
        hits = []
        for query in queries[:4]:
            expanded = f"{level} {query}"
            for doc, _score in self.retriever.search(expanded, top_k=8):
                if doc.id in seen:
                    continue
                docs.append(doc)
                seen.add(doc.id)
                hits.append(
                    {
                        "query": expanded,
                        "title": doc.title,
                        "category": doc.category,
                        "score": round(_score, 3),
                        "path": doc.path or doc.source,
                    }
                )
        docs = docs[:14]
        meta = {
            "queries": queries[:4],
            "hit_count": len(docs),
            "top_hits": hits[:10],
        }
        return docs, meta

    def _tool_list_teaching_aids(self) -> list[Document]:
        return list_teaching_aids(self.retriever)

    @staticmethod
    def _is_catalog_query(message: str) -> bool:
        keywords = [
            "有哪些教具",
            "有什么教具",
            "有啥教具",
            "有啥子教具",
            "介绍一下你们的教具",
            "介绍你们的教具",
            "介绍一下教具",
            "教具清单",
            "教育用品清单",
            "有哪些玩具",
            "可用教具",
            "都有哪些教具",
        ]
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _needs_clarification(message: str) -> bool:
        cleaned = message.strip()
        broad = ["我想做实验", "做个实验", "光的实验", "力的实验", "科学实验", "物理实验", "给我推荐", "我想学习"]
        known_topics = ["杠杆", "平面镜", "平面镜成像", "液体压强", "光的偏振", "光的干涉", "超重", "失重", "声音", "浮力"]
        if cleaned in known_topics:
            return False
        if len(cleaned) <= 6 and not EduToyAgent._is_catalog_query(cleaned):
            return True
        return any(item == cleaned for item in broad)

    @staticmethod
    def _clarifying_question(message: str) -> str:
        return (
            f"你说的是“{message}”。我先帮你缩小一下方向：\n\n"
            "你更想做哪一种？\n"
            "A. 看得见现象的演示实验\n"
            "B. 自己动手制作一个益智玩具\n"
            "C. 用已有教具学习一个知识点\n\n"
            "也可以直接告诉我知识点，比如“平面镜成像”“杠杆”“液体压强”“光的偏振”。"
        )

    @staticmethod
    def _merge_docs(primary: list[Document], secondary: list[Document]) -> list[Document]:
        merged = []
        seen = set()
        for doc in primary + secondary:
            if doc.id in seen:
                continue
            merged.append(doc)
            seen.add(doc.id)
        return merged[:18]

    def _design_brief(self, message: str, level: str, constraints: str, docs: list[Document]) -> str:
        manual_titles = [doc.title for doc in docs if doc.category in {"manual", "primary_science", "cross_discipline"}][:5]
        materials = "由 Agent 根据知识点推荐，不要求学生预先填写"
        if constraints:
            materials = constraints
        return (
            f"目标学生：{level}\n"
            f"学习问题：{message}\n"
            f"可用材料：{materials}\n"
            f"参考资料：{'、'.join(manual_titles) or '本地教材和实验教学论文'}\n"
            "设计原则：低成本、可观察、可重复、学生能动手、先预测再实验再解释。"
        )

    @staticmethod
    def _safety_check(level: str, design_brief: str) -> str:
        return safety_check(level)

    @staticmethod
    def _quality_check(answer: str, docs: list[Document], safety: str, state: AgentState, used_tools: list[str]) -> dict[str, Any]:
        issues = []
        checks = []

        grounded = bool(docs) or state.intent in {"clarify"}
        checks.append({"name": "资料依据", "pass": grounded, "detail": f"命中文档 {len(docs)} 条"})
        if not grounded:
            issues.append("没有检索到本地资料，回答只能作为兜底建议。")

        local_catalog = True
        if state.intent == "catalog_query":
            manual_count = sum(1 for doc in docs if doc.category == "manual")
            local_catalog = manual_count > 0 and "说明书" in answer
            checks.append({"name": "教具不编造", "pass": local_catalog, "detail": f"本地 manual 文档 {manual_count} 条"})
            if not local_catalog:
                issues.append("教具清单没有明确绑定本地说明书。")

        concept_route_ok = True
        if state.intent == "concept_explanation":
            experiment_terms = ["材料清单", "动手步骤", "制作步骤"]
            concept_route_ok = not any(term in answer for term in experiment_terms)
            checks.append({"name": "知识点不误入实验", "pass": concept_route_ok, "detail": "学生只问知识点时先解释概念"})
            if not concept_route_ok:
                issues.append("知识点回答里出现了过早的实验步骤。")

        safety_ok = True
        if state.intent == "experiment_design":
            safety_ok = bool(safety) and ("安全" in answer or "提醒" in answer)
            checks.append({"name": "安全边界", "pass": safety_ok, "detail": safety or "无"})
            if not safety_ok:
                issues.append("实验设计缺少安全提醒。")

        style_ok = len(answer.strip()) > 20
        checks.append({"name": "回答完整性", "pass": style_ok, "detail": f"回答长度 {len(answer)} 字符"})
        if not style_ok:
            issues.append("回答过短。")

        passed = sum(1 for check in checks if check["pass"])
        return {
            "status": "pass" if not issues else "review",
            "score": round(passed / max(len(checks), 1), 2),
            "intent": state.intent,
            "route": state.route,
            "used_tools": used_tools,
            "checks": checks,
            "issues": issues,
        }

    def _synthesize(
        self,
        message: str,
        level: str,
        mode: str,
        topic_hint: str,
        constraints: str,
        history: list[dict[str, str]],
        plan: dict[str, Any],
        docs: list[Document],
        design_brief: str,
        safety: str,
    ) -> str:
        if not self.llm.available:
            return self._fallback_answer(message, level, docs, design_brief, safety)

        system = (
            self.system_prompt
            + "\n\n"
            "你是 EduToy Agent，一个面向学生的科学/物理益智玩具学习智能体。"
            "你必须先适配学生水平，再用本地检索资料设计可动手实验。"
            "如果学生询问有哪些教具/教育用品，你必须只依据 retrieved_documents 中的 manual 文档列清单，不要编造。"
            "如果学生只是问知识点、定义或原理，先讲概念，不要默认设计实验；最后可以问他要不要进入实验。"
            "回答时不要装作已经做过真实实验；不要编造来源。"
            "如果 mode=student，语气要像耐心老师，用对话式、短步骤、鼓励学生先预测。"
            "如果 mode=developer，输出更完整的教学设计、工具调用依据、材料清单、安全边界和评价方式。"
            "回答实验设计时尽量使用固定结构：你要学的知识、推荐教具、先猜一猜、动手步骤、观察什么、为什么、安全提醒、下一步挑战。"
        )
        user = json.dumps(
            {
                "mode": mode,
                "level": level,
                "student_message": message,
                "topic_hint": topic_hint,
                "constraints": constraints,
                "recent_history": history[-6:],
                "agent_plan": plan,
                "retrieved_documents": [
                    {
                        "title": doc.title,
                        "category": doc.category,
                        "level": getattr(doc, "level", ""),
                        "content": doc.content[:520],
                        "path": getattr(doc, "path", ""),
                    }
                    for doc in docs[:5]
                ],
                "design_brief": design_brief,
                "safety_check": safety,
            },
            ensure_ascii=False,
        )
        try:
            answer = self.llm.complete(system, user)
            if answer:
                return answer
            raise RuntimeError("GLM returned empty content.")
        except Exception as exc:
            fallback = self._fallback_answer(message, level, docs, design_brief, safety)
            return f"{fallback}\n\n> GLM 调用失败，已自动使用本地规则兜底。错误：{exc}"

    def _explain_concept(
        self,
        message: str,
        level: str,
        topic_hint: str,
        history: list[dict[str, str]],
        plan: dict[str, Any],
        docs: list[Document],
    ) -> str:
        if not self.llm.available:
            refs = "、".join(doc.title for doc in docs[:4]) or "本地教材与实验资料"
            return (
                f"我们先只讲知识点，不急着做实验。\n\n"
                f"## 这个问题在问什么\n{message}\n\n"
                "## 简单理解\n"
                "它可以先理解成：观察一个现象，找到背后的规律，再用生活里的例子验证。\n\n"
                f"## 参考资料\n{refs}\n\n"
                "如果你愿意，我下一步可以用一个教具或小实验带你验证。"
            )

        system = (
            self.system_prompt
            + "\n\n"
            "你是 EduToy Agent 的概念讲解模块。"
            "学生现在只是在问知识点、定义或原理，不是在要求设计实验。"
            "你要先用适合学生水平的语言讲清楚概念，最多给一个生活例子。"
            "不要输出材料清单、实验步骤或教具设计。最后只问一句：要不要用教具/实验验证。"
            "必须基于 retrieved_documents，不要编造来源。"
        )
        user = json.dumps(
            {
                "level": level,
                "student_message": message,
                "topic_hint": topic_hint,
                "recent_history": history[-6:],
                "agent_plan": plan,
                "retrieved_documents": [
                    {
                        "title": doc.title,
                        "category": doc.category,
                        "content": doc.content[:480],
                        "path": doc.path,
                    }
                    for doc in docs[:4]
                ],
            },
            ensure_ascii=False,
        )
        try:
            answer = self.llm.complete(system, user)
            if answer:
                return answer
            raise RuntimeError("GLM returned empty content.")
        except Exception as exc:
            refs = "、".join(doc.title for doc in docs[:4]) or "本地教材与实验资料"
            return (
                f"我们先只讲知识点，不急着做实验。\n\n"
                f"## 这个问题在问什么\n{message}\n\n"
                "## 简单理解\n"
                "它可以先理解成：观察一个现象，找到背后的规律，再用生活里的例子验证。\n\n"
                f"## 参考资料\n{refs}\n\n"
                f"如果你愿意，我下一步可以用一个教具或小实验带你验证。\n\n"
                f"> GLM 调用失败，已自动使用本地规则兜底。错误：{exc}"
            )

    @staticmethod
    def _fast_concept_answer(message: str, docs: list[Document]) -> str:
        refs = "、".join(doc.title for doc in docs[:3]) or "本地教材与实验资料"
        if "过冷" in message:
            return (
                "我们先讲“过冷现象”，不急着做实验。\n\n"
                "## 简单理解\n"
                "过冷是指液体已经低于正常凝固点，却暂时还没有结冰。它看起来还是液体，但状态并不稳定；一旦受到震动、碰到冰晶或有杂质作为结晶起点，就可能很快开始结冰。\n\n"
                "## 为什么会这样\n"
                "结冰需要一个开始排列的“起点”。如果水比较纯、容器很光滑、环境扰动很少，水分子可能暂时没有找到合适起点，所以会短时间保持液态。\n\n"
                "## 你可以这样记\n"
                "过冷不是“不冷”，而是“已经够冷了，但还没找到结冰的开头”。\n\n"
                f"## 本地依据\n{refs}\n\n"
                "要不要我下一步用一个安全的课堂演示思路来验证？"
            )
        snippet = ""
        for doc in docs:
            text = doc.content.strip().replace("\n", " ")
            if len(text) > 40:
                snippet = text[:180]
                break
        if not snippet:
            snippet = "可以先观察现象，再找出影响现象变化的条件，最后用自己的话解释规律。"
        return (
            f"我们先讲“{message}”，不急着做实验。\n\n"
            "## 简单理解\n"
            f"{snippet}\n\n"
            "## 你可以这样记\n"
            "先看现象，再找原因：是什么变了、为什么会变、换一个条件会不会还这样。\n\n"
            f"## 本地依据\n{refs}\n\n"
            "要不要我下一步用一个教具或小实验带你验证？"
        )

    @staticmethod
    def _fallback_answer(message: str, level: str, docs: list[Document], design_brief: str, safety: str) -> str:
        if EduToyAgent._is_catalog_query(message):
            manuals = [doc for doc in docs if doc.category == "manual"]
            return EduToyAgent._catalog_answer(manuals)

        refs = "、".join(doc.title for doc in docs[:5]) or "本地教材与实验资料"
        if level == "小学":
            return (
                f"我们可以把“{message}”做成一个小实验。\n\n"
                "## 你要学的知识\n"
                "通过玩具实验观察现象，再用自己的话解释原因。\n\n"
                "## 先猜一猜\n"
                "如果改变材料或位置，现象会不会变？\n\n"
                "## 动手步骤\n"
                "1. 准备生活材料。\n"
                "2. 只改变一个条件。\n"
                "3. 观察结果。\n"
                "4. 记录看到的变化。\n\n"
                "## 为什么\n"
                "把观察到的变化和知识点联系起来。\n\n"
                f"## 参考资料\n{refs}\n\n"
                f"## 安全提醒\n{safety}\n\n"
                "## 下一步挑战\n"
                "你可以告诉我你的预测，我再带你判断实验结果。"
            )
        return (
            f"围绕“{message}”，可以设计一个探究式教具实验。\n\n"
            "## 你要学的知识\n"
            "围绕核心概念建立可观察、可测量的实验任务。\n\n"
            "## 推荐教具/材料\n"
            f"{design_brief}\n\n"
            "## 先猜一猜\n"
            "让学生先预测变量改变后现象如何变化。\n\n"
            "## 动手步骤\n"
            "提出问题 -> 学生预测 -> 操作实验 -> 记录数据/现象 -> 解释原理 -> 改进玩具结构。\n\n"
            "## 观察什么\n"
            "观察关键现象是否随变量变化，并记录可比较的数据或图像。\n\n"
            "## 为什么\n"
            "把观察结果和教材中的物理模型联系起来。\n\n"
            f"## 参考资料\n{refs}\n\n"
            f"## 安全提醒\n{safety}\n\n"
            "## 下一步挑战\n"
            "让学生改一个结构参数，再预测实验结果。"
        )

    @staticmethod
    def _build_query(message: str, level: str, topic_hint: str, constraints: str) -> str:
        return " ".join(part for part in [level, topic_hint, message, constraints, "实验 教具 益智玩具"] if part)

    @staticmethod
    def _wants_experiment(message: str) -> bool:
        experiment_words = [
            "实验",
            "教具",
            "玩具",
            "动手",
            "制作",
            "设计",
            "材料",
            "步骤",
            "玩法",
            "带我做",
            "怎么做",
            "验证",
        ]
        return any(word in message for word in experiment_words)

    @staticmethod
    def _compact_json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2)[:1400]

    @staticmethod
    def _catalog_answer(manuals: list[Document]) -> str:
        if not manuals:
            return "我在本地教具说明书库里暂时没有检索到明确教具。可以换一个关键词，例如“光学教具”“力学教具”或“压强教具”。"
        lines = [
            "目前本地知识库中有这些标准教具。下面的名称来自本地“教具说明书”，不是模型猜的：",
            "",
        ]
        for idx, doc in enumerate(manuals[:30], start=1):
            meta = EduToyAgent._aid_meta(doc.title)
            lines.append(f"{idx}. {doc.title}：{meta['description']}")
        lines.extend(
            [
                "",
                "你可以继续问：某个教具适合哪个学段、能讲哪个知识点、怎么组织课堂实验。",
            ]
        )
        return "\n".join(lines)

    @staticmethod
    def _catalog_cards(manuals: list[Document]) -> list[dict[str, str]]:
        cards = []
        for doc in manuals[:12]:
            meta = EduToyAgent._aid_meta(doc.title)
            cards.append(
                {
                    "title": doc.title,
                    "level": meta["level"],
                    "knowledge": meta["knowledge"],
                    "category": meta["category"],
                    "description": meta["description"],
                    "icon": meta["icon"],
                    "action": meta["action"],
                    "source": doc.path or doc.source,
                }
            )
        return cards

    @staticmethod
    def _aid_meta(title: str) -> dict[str, str]:
        if "平面镜" in title:
            return {
                "icon": "光",
                "category": "光学教具",
                "knowledge": "平面镜成像、像距物距、虚像",
                "level": "初中",
                "description": "用于观察像与物的大小、位置和距离关系，适合做成像规律探究。",
                "action": "开始平面镜成像实验",
            }
        if "杠杆" in title:
            return {
                "icon": "力",
                "category": "力学教具",
                "knowledge": "杠杆平衡、省力与力臂",
                "level": "小学/初中",
                "description": "用于比较支点位置、力臂长短和省力效果，适合动手探究。",
                "action": "开始杠杆省力实验",
            }
        if "液体压强" in title:
            return {
                "icon": "压",
                "category": "压强教具",
                "knowledge": "液体压强、深度、方向",
                "level": "初中",
                "description": "用于探究液体内部压强随深度和方向变化的规律。",
                "action": "开始液体压强探究",
            }
        if "偏振" in title:
            return {
                "icon": "偏",
                "category": "光学教具",
                "knowledge": "光的偏振、光强变化",
                "level": "高中",
                "description": "用于观察偏振片角度变化对透光强度的影响。",
                "action": "开始光的偏振实验",
            }
        if "干涉" in title:
            return {
                "icon": "波",
                "category": "光学教具",
                "knowledge": "光的干涉、波动性",
                "level": "高中",
                "description": "用于观察干涉条纹，帮助理解光的波动性。",
                "action": "开始光的干涉实验",
            }
        if "超失重" in title:
            return {
                "icon": "重",
                "category": "力学教具",
                "knowledge": "超重失重、压力变化",
                "level": "高中",
                "description": "用于演示运动过程中压力读数变化，理解超重和失重。",
                "action": "开始超失重演示",
            }
        return {
            "icon": "科",
            "category": "科学教具",
            "knowledge": "科学探究",
            "level": "通用",
            "description": "用于课堂科学探究活动。",
            "action": "查看玩法",
        }
