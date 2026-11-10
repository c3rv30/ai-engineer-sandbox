"""Language of the answer: the order the generator gets and the check after it (BUG-11).

The supervisor decides the language (router.py); this module turns that decision into
the generator's instruction and checks the final answer against it. The application
and the language eval (tests/evals/answer_language/) use the same detector, so the eval
measures exactly the signal production records.

It loads no LLM client and no embedding model, so the pure logic layer can import it.
"""
import re
from collections import Counter
from dataclasses import dataclass
from functools import cache
from typing import Optional

from lingua import Language, LanguageDetectorBuilder

SUPPORTED_LANGUAGES = {"es": "Spanish", "en": "English"}

# How far apart the two languages' confidences must be for the detector to answer.
# Below it the answer is "undetermined", which is never counted as a mismatch: a Spanish
# answer full of English technology names comes out close to the middle, and a false
# mismatch would keep a good answer out of the cache.
MIN_RELATIVE_DISTANCE = 0.25
# The language covering most of the letters wins, and it must cover at least this share,
# or the answer is undetermined. Judging the whole text at once let a few long Spanish
# proper nouns outweigh English prose: an English answer listing "Diplomado en
# Inteligencia Artificial (Diploma in Artificial Intelligence)" came out as Spanish with
# full confidence, 3 of 200 answers of the eval. In those 200, the right language never
# covered less than 62%.
MIN_SHARE = 0.6
# With fewer letters than this, even a clear language is a guess ("Hi!" or "OK" come
# out as English with 0.7-0.9 confidence).
MIN_LETTERS = 20

# Code is neither Spanish nor English, and keywords like "for" or "return" push the
# detector toward English.
_CODE = re.compile(r"```.*?```|`[^`\n]*`", re.DOTALL)
_URL = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class LanguageCheck:
    """Decided language vs. detected language. None means unknown."""
    expected: Optional[str]
    detected: Optional[str]

    @property
    def mismatch(self) -> bool:
        # Only when both are known: an undetermined answer is not a wrong one.
        return (self.expected is not None and self.detected is not None
                and self.expected != self.detected)


def answer_instruction(language: str) -> str:
    """The generator's language order, for a language the supervisor decided."""
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported answer language: {language!r}")
    return (
        f"LANGUAGE: Write 'answer' in {SUPPORTED_LANGUAGES[language]}, even if the Question "
        "or the Context is in another language. Translate what you take from the Context; "
        "keep proper nouns, company names and technology names as they are."
    )


@cache
def _detector():
    # Built on first use, not on import: the purity guard imports this module, and the
    # language models are only needed when there is an answer to check.
    return (LanguageDetectorBuilder.from_languages(Language.SPANISH, Language.ENGLISH)
            .with_minimum_relative_distance(MIN_RELATIVE_DISTANCE)
            .build())


def detect_language(text: Optional[str]) -> Optional[str]:
    """'es' or 'en', or None when the text is too short or too close to call."""
    if not text:
        return None
    prose = _URL.sub(" ", _CODE.sub(" ", text))
    if _letters(prose) < MIN_LETTERS:
        return None
    letters = Counter()
    for segment in _detector().detect_multiple_languages_of(prose):
        letters[segment.language] += _letters(prose[segment.start_index:segment.end_index])
    if not letters:
        return None
    language, covered = letters.most_common(1)[0]
    if covered / sum(letters.values()) < MIN_SHARE:
        return None
    return language.iso_code_639_1.name.lower()


def _letters(text: str) -> int:
    return sum(c.isalpha() for c in text)


def check_answer_language(expected: Optional[str], answer: Optional[str]) -> LanguageCheck:
    """Compares an answer with the decided language. An empty decision counts as unknown."""
    return LanguageCheck(expected=expected or None, detected=detect_language(answer))
