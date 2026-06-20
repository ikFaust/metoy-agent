from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class AdmissionRecord:
    school: str
    province: str
    city: str
    level: str
    type: str
    major_group: str
    major_direction: str
    subjects: str
    year: int
    min_score: int
    min_rank: int
    plan_count: int
    source: str
    band: str = ""
    rank_gap: int = 0


class AdmissionMatcher:
    def __init__(self, records: list[AdmissionRecord]):
        self.records = records

    @classmethod
    def from_csv(cls, path: str | Path) -> "AdmissionMatcher":
        records = []
        csv_path = Path(path)
        if not csv_path.exists():
            return cls([])
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                records.append(
                    AdmissionRecord(
                        school=row["school"],
                        province=row["province"],
                        city=row["city"],
                        level=row["level"],
                        type=row["type"],
                        major_group=row["major_group"],
                        major_direction=row["major_direction"],
                        subjects=row["subjects"],
                        year=int(row["year"]),
                        min_score=int(row["min_score"]),
                        min_rank=int(row["min_rank"]),
                        plan_count=int(row["plan_count"]),
                        source=row["source"],
                    )
                )
        return cls(records)

    def match(self, profile: dict[str, Any], limit: int = 12) -> list[AdmissionRecord]:
        rank = _parse_rank(profile.get("rank", ""))
        if not rank:
            return []

        subjects = set(profile.get("subjects", []))
        cities = set(profile.get("city_preference", []))
        interests = set(profile.get("interests", []))
        target_schools = set(profile.get("target_schools", []))

        scored = []
        for record in self.records:
            if subjects and not subjects.issubset(set(record.subjects.split())):
                continue
            score = 0.0
            if record.city in cities:
                score += 8.0
            if record.school in target_schools:
                score += 10.0
            if any(item and item in record.major_direction for item in interests):
                score += 5.0
            score += self._rank_score(rank, record.min_rank)
            scored.append((record, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        matched = []
        for record, _score in scored[:limit]:
            copy = AdmissionRecord(**{field: getattr(record, field) for field in record.__dataclass_fields__ if field not in {"band", "rank_gap"}})
            copy.rank_gap = rank - record.min_rank
            copy.band = self._band(rank, record.min_rank)
            matched.append(copy)
        return matched

    @staticmethod
    def _rank_score(user_rank: int, min_rank: int) -> float:
        gap = user_rank - min_rank
        if gap > 25000:
            return 1.0
        if gap > 8000:
            return 5.0
        if gap >= -8000:
            return 10.0
        if gap >= -35000:
            return 7.0
        return 3.0

    @staticmethod
    def _band(user_rank: int, min_rank: int) -> str:
        gap = user_rank - min_rank
        if gap > 25000:
            return "冲"
        if gap > 8000:
            return "小冲"
        if gap >= -8000:
            return "稳"
        if gap >= -35000:
            return "保"
        return "兜底"


def _parse_rank(value: object) -> int | None:
    text = str(value)
    numbers = re.findall(r"\d+", text.replace(",", ""))
    if not numbers:
        return None
    return int(numbers[0])
