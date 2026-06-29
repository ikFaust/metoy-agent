from __future__ import annotations

from edutoy.retrieval import Document, LocalRetriever


def list_teaching_aids(retriever: LocalRetriever) -> list[Document]:
    manuals = [doc for doc in retriever.documents if doc.category == "manual"]
    manuals.sort(key=lambda doc: doc.title)
    return manuals[:30]


def safety_check(level: str) -> str:
    base = ["不用明火", "不用尖锐刀具", "玻璃/镜片边缘需要包胶", "小学生需要成人或老师陪同"]
    if level in {"高中", "大学"}:
        base.append("涉及电路时使用低压电源并先断电连接")
    else:
        base.append("避免强激光、强磁铁、热水和高处坠落")
    return "；".join(base)
