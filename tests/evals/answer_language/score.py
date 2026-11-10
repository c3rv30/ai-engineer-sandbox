"""Scores the answers collect.py saved (BUG-11). It makes no LLM call.

    uv run --no-sync python tests/evals/answer_language/score.py after.jsonl
    uv run --no-sync python tests/evals/answer_language/score.py after.jsonl --baseline before.jsonl

It detects with src/services/language.py from this repository, whatever code
collected the answers, so the "before" and "after" variants are scored with the same
detector the application uses. The rate is matches / (matches + mismatches): an
undetermined answer or an error is counted apart, never as a success, and a language
with nothing determined has no rate.
"""
import argparse
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.services.language import SUPPORTED_LANGUAGES, detect_language  # noqa: E402

Z_95 = 1.96


def wilson(successes: int, total: int, z: float = Z_95) -> Optional[tuple[float, float]]:
    """Wilson score interval: unlike p ± z·√(p(1-p)/n), it stays inside [0, 1] and does
    not collapse to a zero width at 0% or 100%, which is where this metric lives."""
    if total == 0:
        return None
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


@dataclass
class LanguageScore:
    answers: int = 0
    matches: int = 0
    mismatches: int = 0
    undetermined: int = 0
    errors: int = 0
    decisions: int = 0
    decision_errors: int = 0
    mismatched_questions: Counter = field(default_factory=Counter)

    @property
    def determined(self) -> int:
        return self.matches + self.mismatches

    @property
    def rate(self) -> Optional[float]:
        return self.matches / self.determined if self.determined else None

    @property
    def interval(self) -> Optional[tuple[float, float]]:
        return wilson(self.matches, self.determined)

    @property
    def decision_accuracy(self) -> Optional[float]:
        # Only when the code that collected the answers had a decision to record.
        return (self.decisions - self.decision_errors) / self.decisions if self.decisions else None


def score(records: list[dict]) -> dict[str, LanguageScore]:
    scores = {language: LanguageScore() for language in SUPPORTED_LANGUAGES}
    for record in records:
        s = scores[record["language"]]
        s.answers += 1
        if record.get("error"):
            s.errors += 1
            continue
        if record.get("answer_language"):
            s.decisions += 1
            if record["answer_language"] != record["language"]:
                s.decision_errors += 1
        detected = detect_language(record.get("answer"))
        if detected is None:
            s.undetermined += 1
        elif detected == record["language"]:
            s.matches += 1
        else:
            s.mismatches += 1
            s.mismatched_questions[record["id"]] += 1
    return scores


def compare(after: LanguageScore, before: LanguageScore) -> str:
    """The verdict for one language. An improvement needs intervals that do not overlap."""
    if after.rate is None or before.rate is None:
        return "not comparable (no determined answers)"
    if after.rate < before.rate:
        return "regression"
    if after.rate > before.rate and after.interval[0] > before.interval[1]:
        return "improvement"
    return "no evidence of improvement"


def load(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def _rate(s: LanguageScore) -> str:
    if s.rate is None:
        return "n/a"
    low, high = s.interval
    return f"{s.rate:.1%} [{low:.1%}, {high:.1%}]"


def report(name: str, records: list[dict], scores: dict[str, LanguageScore]) -> str:
    codes = sorted({r.get("code", "?") for r in records})
    lines = [
        f"### {name}",
        "",
        f"{len(records)} answers, code {', '.join(codes)}",
        "",
        "| Language | Answers | Match | Mismatch | Undetermined | Errors | Rate [95% CI] | Supervisor decision |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for language, s in scores.items():
        lines.append(f"| {language} | {s.answers} | {s.matches} | {s.mismatches} | {s.undetermined} | {s.errors} "
                     f"| {_rate(s)} | {_pct(s.decision_accuracy)} |")
    mismatched = Counter()
    for s in scores.values():
        mismatched.update(s.mismatched_questions)
    if mismatched:
        lines += ["", "Questions with mismatches: " + ", ".join(f"`{q}` ×{n}" for q, n in mismatched.most_common())]
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Score the answer language eval (no LLM calls).")
    parser.add_argument("answers", type=Path, help="JSONL written by collect.py")
    parser.add_argument("--baseline", type=Path, help="JSONL of the variant to compare against")
    args = parser.parse_args(argv)

    after_records = load(args.answers)
    after = score(after_records)
    sections = [report(args.answers.name, after_records, after)]
    if args.baseline:
        before_records = load(args.baseline)
        before = score(before_records)
        sections.insert(0, report(args.baseline.name, before_records, before))
        verdicts = ["### Comparison", "", "| Language | Before | After | Verdict |", "|---|---|---|---|"]
        for language in SUPPORTED_LANGUAGES:
            verdicts.append(f"| {language} | {_rate(before[language])} | {_rate(after[language])} "
                            f"| {compare(after[language], before[language])} |")
        sections.append("\n".join(verdicts))
    print("\n\n".join(sections))
    return 0


if __name__ == "__main__":
    sys.exit(main())
