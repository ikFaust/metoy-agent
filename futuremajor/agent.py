from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .admissions import AdmissionMatcher, AdmissionRecord
from .llm import GLMClient
from .retrieval import Document, LocalRetriever


REQUIRED_FIELDS = {
    "province": "省份",
    "rank": "位次或大概分数段",
    "subjects": "选科",
}


@dataclass
class AgentStep:
    name: str
    kind: str
    detail: str
    output: str


@dataclass
class AgentResult:
    status: str
    missing_fields: list[str]
    profile: dict[str, Any]
    retrieved_docs: list[Document]
    admission_matches: list[AdmissionRecord]
    steps: list[AgentStep]
    llm_enabled: bool
    report: str


class FutureMajorAgent:
    def __init__(self, knowledge_path: str | Path, admissions_path: str | Path | None = None):
        self.retriever = LocalRetriever.from_jsonl(knowledge_path)
        self.admissions = AdmissionMatcher.from_csv(admissions_path) if admissions_path else AdmissionMatcher([])
        self.llm = GLMClient()

    def run(self, profile: dict[str, Any]) -> AgentResult:
        steps: list[AgentStep] = []
        normalized = self._normalize_profile(profile)
        steps.append(
            AgentStep(
                "Profile",
                "state",
                "整理结构化学生画像",
                self._compact_json(normalized),
            )
        )
        missing = self._missing_fields(normalized)
        steps.append(
            AgentStep(
                "Clarify",
                "reason",
                "检查是否缺少省份、位次、选科等关键字段",
                "缺失：" + ("、".join(missing) if missing else "无"),
            )
        )
        plan = self._plan(normalized, missing)
        steps.append(
            AgentStep(
                "Plan",
                "llm" if self.llm.available else "rule",
                "生成本轮分析计划和需要调用的工具",
                self._compact_json(plan),
            )
        )
        query = self._build_query(normalized)
        retrieved = self._merge_documents(
            self._framework_docs(normalized),
            self._profile_major_docs(normalized),
            [doc for doc, _score in self.retriever.search(query, top_k=10)],
        )[:16]
        steps.append(
            AgentStep(
                "RetrieveKnowledge",
                "tool",
                "调用本地 RAG 检索专业、城市、风险和公开咨询框架资料",
                "、".join(doc.title for doc in retrieved[:10]) or "无结果",
            )
        )
        admission_matches = self.admissions.match(normalized)
        steps.append(
            AgentStep(
                "MatchAdmissions",
                "tool",
                "调用院校分数线匹配工具，根据位次生成冲稳保候选",
                "、".join(f"{item.band}:{item.school}" for item in admission_matches[:10]) or "无结果",
            )
        )

        if missing:
            report = self._clarify_report(normalized, missing, retrieved)
            steps.append(AgentStep("Report", "rule", "信息不足，先生成追问", report[:500]))
            return AgentResult(
                "needs_clarification",
                missing,
                normalized,
                retrieved,
                admission_matches,
                steps,
                self.llm.available,
                report,
            )

        report = self._generate_report(normalized, retrieved, admission_matches, plan)
        steps.append(
            AgentStep(
                "SynthesizeReport",
                "llm" if self.llm.available else "rule",
                "综合用户画像、RAG 资料和院校匹配结果生成最终报告",
                report[:600],
            )
        )
        return AgentResult("complete", [], normalized, retrieved, admission_matches, steps, self.llm.available, report)

    def _plan(self, profile: dict[str, Any], missing: list[str]) -> dict[str, Any]:
        fallback = {
            "goal": "生成高考志愿方向分析",
            "need_clarification": bool(missing),
            "missing_fields": missing,
            "tools": ["local_knowledge_retrieval", "admission_rank_matcher"],
            "retrieval_queries": [self._build_query(profile)],
            "decision_axes": ["就业路径", "城市机会", "学校平台", "专业底线", "家庭资源", "AI 风险", "冲稳保"],
        }
        if not self.llm.available:
            return fallback
        system = (
            "你是高考志愿 Agent 的规划器。你只输出 JSON，不输出解释文字。"
            "你的任务是根据学生画像规划本轮需要问什么、查什么、调用哪些工具、按哪些维度决策。"
            "不要编造录取结论。"
        )
        user = json.dumps({"student_profile": profile, "missing_fields": missing}, ensure_ascii=False)
        return self.llm.complete_json(system, user, fallback)

    def _normalize_profile(self, profile: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(profile)
        normalized["subjects"] = [s.strip() for s in profile.get("subjects", []) if s.strip()]
        normalized["interests"] = [s.strip() for s in profile.get("interests", []) if s.strip()]
        normalized["avoid"] = [s.strip() for s in profile.get("avoid", []) if s.strip()]
        normalized["city_preference"] = [s.strip() for s in profile.get("city_preference", []) if s.strip()]
        normalized["target_schools"] = [s.strip() for s in profile.get("target_schools", []) if s.strip()]
        return normalized

    def _missing_fields(self, profile: dict[str, Any]) -> list[str]:
        missing = []
        for key, label in REQUIRED_FIELDS.items():
            value = profile.get(key)
            if value is None or value == "" or value == []:
                missing.append(label)
        return missing

    def _build_query(self, profile: dict[str, Any]) -> str:
        parts = [
            profile.get("province", ""),
            str(profile.get("rank", "")),
            " ".join(profile.get("subjects", [])),
            " ".join(profile.get("interests", [])),
            " ".join(profile.get("city_preference", [])),
            " ".join(profile.get("target_schools", [])),
            profile.get("goal", ""),
            profile.get("decision_framework", ""),
            profile.get("family_resource", ""),
            profile.get("risk_tolerance", ""),
        ]
        return " ".join(part for part in parts if part)

    def _framework_docs(self, profile: dict[str, Any]) -> list[Document]:
        docs = [
            doc
            for doc in self.retriever.documents
            if doc.category in {"framework", "rule"}
            and any(tag in doc.tags for tag in ["张雪峰式框架", "决策规则"])
        ]
        focus = profile.get("decision_framework", "")
        if "就业倒推" in focus:
            docs.sort(key=lambda doc: 0 if "就业倒推" in doc.tags or "就业优先" in doc.tags else 1)
        elif "城市" in focus:
            docs.sort(key=lambda doc: 0 if "城市" in doc.tags else 1)
        elif "家庭" in focus:
            docs.sort(key=lambda doc: 0 if "家庭资源" in doc.tags else 1)
        else:
            docs.sort(key=lambda doc: 0 if "就业倒推" in doc.tags else 1)
        return docs[:5]

    def _profile_major_docs(self, profile: dict[str, Any]) -> list[Document]:
        major_docs = [doc for doc in self.retriever.documents if doc.category == "major"]
        scored = [(doc, self._profile_score(doc, profile)) for doc in major_docs]
        scored = [(doc, score) for doc, score in scored if score > 0]
        scored.sort(key=lambda item: item[1], reverse=True)
        return self._diversify_majors([doc for doc, _score in scored], limit=7)

    def _profile_score(self, doc: Document, profile: dict[str, Any]) -> float:
        strong_text = f"{doc.title} {' '.join(doc.tags)}"
        score = 0.0
        for interest in profile.get("interests", []):
            if not interest:
                continue
            if interest in strong_text:
                score += 4.0
            elif interest in doc.content:
                score += 0.6
        for avoided in profile.get("avoid", []):
            if not avoided:
                continue
            if avoided in strong_text:
                score -= 6.0
            elif avoided in doc.content:
                score -= 1.5
        goal = profile.get("goal", "")
        if "就业" in goal and any(tag in doc.tags for tag in ["就业", "稳定", "软件", "电气", "电子"]):
            score += 1.2
        if "考研" in goal and any(tag in doc.tags for tag in ["读研", "算法", "芯片", "医学"]):
            score += 1.2
        if "考公" in goal and any(tag in doc.tags for tag in ["考公", "稳定", "师范", "会计"]):
            score += 1.2
        if profile.get("family_resource") in {"一般", "较弱"} and "资源依赖" in doc.tags:
            score -= 2.0
        return score

    def _diversify_majors(self, docs: list[Document], limit: int = 5) -> list[Document]:
        selected = []
        family_counts: dict[str, int] = {}
        for doc in docs:
            family = self._major_family(doc)
            max_per_family = 3 if family == "tech" else 2
            if family_counts.get(family, 0) >= max_per_family:
                continue
            selected.append(doc)
            family_counts[family] = family_counts.get(family, 0) + 1
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _major_family(doc: Document) -> str:
        tags = set(doc.tags)
        if tags & {"计算机", "软件", "人工智能", "网络安全", "数据", "AI", "互联网"}:
            return "tech"
        if tags & {"电子", "通信", "芯片", "硬件", "自动化", "物联网", "电气"}:
            return "ee"
        if tags & {"机械", "制造", "车辆", "能源", "材料", "化工", "汽车"}:
            return "engineering"
        if tags & {"医学", "药学", "护理", "口腔医学", "医院"}:
            return "medical"
        if tags & {"会计", "金融", "经济", "统计", "财务"}:
            return "business"
        if tags & {"法学", "汉语言", "英语", "新闻传播", "公共管理", "师范", "考公"}:
            return "humanities"
        return "other"

    @staticmethod
    def _merge_documents(*groups: list[Document]) -> list[Document]:
        merged = []
        seen = set()
        for group in groups:
            for doc in group:
                if doc.id in seen:
                    continue
                merged.append(doc)
                seen.add(doc.id)
        return merged

    def _clarify_report(self, profile: dict[str, Any], missing: list[str], docs: list[Document]) -> str:
        tips = "、".join(missing)
        return (
            f"还需要补充关键信息：{tips}。\n\n"
            "高考志愿建议高度依赖省份、位次和选科。缺少这些信息时，我可以先做专业方向讨论，"
            "但不能给出比较像样的冲稳保策略。\n\n"
            f"目前已能参考的资料方向：{self._doc_titles(docs)}"
        )

    def _generate_report(
        self,
        profile: dict[str, Any],
        docs: list[Document],
        admissions: list[AdmissionRecord],
        plan: dict[str, Any],
    ) -> str:
        if self.llm.available:
            try:
                return self._generate_llm_report(profile, docs, admissions, plan)
            except Exception as exc:
                return self._generate_rule_report(profile, docs, admissions, error=str(exc))
        return self._generate_rule_report(profile, docs, admissions)

    def _generate_llm_report(
        self,
        profile: dict[str, Any],
        docs: list[Document],
        admissions: list[AdmissionRecord],
        plan: dict[str, Any],
    ) -> str:
        system = (
            "你是 FutureMajor Agent，一个高考专业与志愿方向辅助分析智能体。"
            "你不预测录取，不冒充官方或专家；你基于给定资料做可解释的方向分析。"
            "你可以借鉴公开升学咨询方法论，例如就业倒推、城市-学校-专业排序、家庭资源约束和专业底线，但不能模仿或冒充具体真人。"
            "输出要有：用户画像、主推方向、备选方向、谨慎/不推荐方向、目标院校与分数线匹配、张雪峰式框架如何参与决策、冲稳保策略、风险、下一步核验清单。"
            "不要把同一类热门专业全部堆在前面，要给出跨类别备选。"
            "每条建议都要说明依据，不能编造未提供的数据。"
            "院校分数线若标注为示例数据，必须提醒用户以省考试院和院校招生章程核验。"
        )
        user = json.dumps(
            {
                "agent_plan": plan,
                "student_profile": profile,
                "retrieved_knowledge": [
                    {
                        "title": doc.title,
                        "category": doc.category,
                        "content": doc.content,
                        "tags": doc.tags,
                        "source": doc.source,
                    }
                    for doc in docs
                ],
                "admission_matches": [
                    {
                        "school": item.school,
                        "city": item.city,
                        "level": item.level,
                        "major_direction": item.major_direction,
                        "year": item.year,
                        "min_score": item.min_score,
                        "min_rank": item.min_rank,
                        "plan_count": item.plan_count,
                        "band": item.band,
                        "rank_gap": item.rank_gap,
                        "source": item.source,
                    }
                    for item in admissions
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        return self.llm.complete(system, user)

    def _generate_rule_report(
        self,
        profile: dict[str, Any],
        docs: list[Document],
        admissions: list[AdmissionRecord],
        error: str | None = None,
    ) -> str:
        goal = profile.get("goal", "就业与长期发展平衡")
        interests = "、".join(profile.get("interests", [])) or "暂未明确"
        cities = "、".join(profile.get("city_preference", [])) or "暂未明确"
        schools = "、".join(profile.get("target_schools", [])) or "暂未明确"
        subjects = "、".join(profile.get("subjects", []))
        titles = self._doc_titles(docs)

        ranked_major_docs = sorted(
            [doc for doc in docs if doc.category == "major"],
            key=lambda doc: self._profile_score(doc, profile),
            reverse=True,
        )
        positive_major_docs = [doc for doc in ranked_major_docs if self._profile_score(doc, profile) > 0]
        major_docs = self._diversify_majors(positive_major_docs or ranked_major_docs, limit=6)
        primary_docs = major_docs[:3]
        backup_docs = major_docs[3:6]
        caution_docs = self._caution_major_docs(profile, major_docs)
        framework_docs = [doc for doc in docs if doc.category == "framework"][:4]
        rule_docs = [doc for doc in docs if doc.category == "rule"][:3]
        city_docs = [doc for doc in docs if doc.category == "city"][:3]

        primary_recs = "\n".join(
            f"- {doc.title}：{doc.content[:120]}..."
            for doc in primary_docs
        ) or "- 暂未检索到足够专业资料，需要扩充知识库。"
        backup_recs = "\n".join(
            f"- {doc.title}：{doc.content[:120]}..."
            for doc in backup_docs
        ) or "- 当前画像的备选方向不足，需要补充兴趣、城市或风险偏好。"
        caution_recs = "\n".join(
            f"- {doc.title}：{doc.content[:110]}..."
            for doc in caution_docs
        ) or "- 暂未发现强烈排除方向，但正式填报前仍要核验专业底线。"
        frameworks = "\n".join(f"- {doc.title}：{doc.content[:115]}..." for doc in framework_docs) or "- 当前未检索到公开升学咨询框架资料。"
        rules = "\n".join(f"- {doc.title}：{doc.content[:100]}..." for doc in rule_docs) or "- 使用通用就业、城市、专业匹配规则。"
        city_notes = "\n".join(f"- {doc.title}：{doc.content[:100]}..." for doc in city_docs) or "- 城市偏好还需要结合招生计划和家庭可承受成本核验。"
        admission_notes = self._format_admissions(admissions)

        api_note = f"\n\n> GLM 调用失败，已使用本地规则报告。错误：{error}" if error else ""
        return f"""## 用户画像
- 省份：{profile.get("province")}
- 位次/分数段：{profile.get("rank")}
- 选科：{subjects}
- 兴趣方向：{interests}
- 城市偏好：{cities}
- 目标学校：{schools}
- 目标倾向：{goal}
- 家庭资源：{profile.get("family_resource", "未填写")}
- 风险偏好：{profile.get("risk_tolerance", "中等")}
- 决策框架：{profile.get("decision_framework", "就业倒推 + 城市/学校/专业权衡")}

## 主推方向
{primary_recs}

## 备选方向
{backup_recs}

## 谨慎/不建议方向
{caution_recs}

## 公开咨询框架
{frameworks}

## 决策规则依据
{rules}

## 城市与机会提示
{city_notes}

## 目标院校与分数线匹配
{admission_notes}

## 冲稳保策略
- 冲：优先选择城市平台或学校层次更强、专业可接受的组合，但必须核验历年位次和选科要求。
- 稳：选择就业路径清晰、与兴趣和选科匹配度高的专业方向，把专业满意度放在前面。
- 保：选择录取安全性更高、转专业空间或升学路径明确的院校专业组，避免只为学校名气牺牲底线专业。

## 风险提示
- 当前 MVP 不接入全量历年录取线，因此不能给出真实投档概率。
- 招生章程、选科要求、专业组计划每年变化，正式填报前必须核验官方来源。
- 当前院校分数线模块使用示例数据结构，正式使用前必须替换为目标省考试院/阳光高考/院校招生网核验数据。
- 建议只能辅助讨论，不能替代考生家庭和学校老师的正式决策。

## 下一步核验清单
- 查目标省份当年志愿批次、专业组选科和投档规则。
- 查目标院校近三年最低位次、专业录取位次和招生计划变化。
- 对每个候选专业确认学习内容、读研必要性、就业城市和家庭资源匹配度。

## 本次检索到的资料
{titles}{api_note}
"""

    @staticmethod
    def _doc_titles(docs: list[Document]) -> str:
        return "、".join(doc.title for doc in docs[:8]) or "暂无"

    @staticmethod
    def _compact_json(data: Any) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2)[:1200]

    def _caution_major_docs(self, profile: dict[str, Any], selected_docs: list[Document]) -> list[Document]:
        selected_ids = {doc.id for doc in selected_docs}
        cautions = []
        for doc in self.retriever.documents:
            if doc.category != "major" or doc.id in selected_ids:
                continue
            score = self._profile_score(doc, profile)
            if score < 0:
                cautions.append((doc, score))
        cautions.sort(key=lambda item: item[1])
        return [doc for doc, _score in cautions[:3]]

    @staticmethod
    def _format_admissions(admissions: list[AdmissionRecord]) -> str:
        if not admissions:
            return "- 暂未匹配到院校分数线数据。需要补充目标省份的一分一段、投档线、专业组和院校专业录取数据。"
        lines = []
        for item in admissions[:8]:
            gap_text = f"位次差 {item.rank_gap:+d}"
            lines.append(
                f"- [{item.band}] {item.school}（{item.city}，{item.level}）："
                f"{item.major_direction}，{item.year} 年最低位次 {item.min_rank}，最低分 {item.min_score}，计划 {item.plan_count}，{gap_text}。"
            )
        return "\n".join(lines)
