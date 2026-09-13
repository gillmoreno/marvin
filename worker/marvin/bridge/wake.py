"""Wake-word detection on finalized STT segments.

Rule for v1 (deliberately simple, tune after seeing real false triggers):
the agent's name, or a known misspelling of it, must appear within the first
or last `window` words of the utterance. "let's ask marvin later" therefore does
NOT trigger while "marvin, what do you think" and "does that make sense marvin" do.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

DEFAULT_NAME = "marvin"
# Spellings speech-to-text tends to produce for "Marvin" (fuzzy matching covers the rest).
DEFAULT_ALIASES: tuple[str, ...] = ("marvin", "marvyn", "marven", "marvine", "marvel")

_WORD_RE = re.compile(r"[a-z0-9']+")


@dataclass(frozen=True)
class WakeMatch:
    position: str  # "start" | "end"
    alias: str  # the token that matched
    question: str  # utterance with the name removed


class WakeDetector:
    def __init__(
        self,
        name: str = DEFAULT_NAME,
        aliases: tuple[str, ...] = DEFAULT_ALIASES,
        window: int = 3,
        fuzzy_ratio: float = 0.85,
    ) -> None:
        self.name = name.lower()
        self.aliases = {a.lower() for a in aliases} | {self.name}
        self.window = window
        self.fuzzy_ratio = fuzzy_ratio

    def _is_name(self, token: str) -> bool:
        if token in self.aliases:
            return True
        # Fuzzy fallback for tokens of similar length ("marvin" vs "marvyn").
        if abs(len(token) - len(self.name)) <= 1 and difflib.SequenceMatcher(None, token, self.name).ratio() >= self.fuzzy_ratio:
            return True
        return False

    def detect(self, text: str) -> WakeMatch | None:
        words = _WORD_RE.findall(text.lower())
        if not words:
            return None
        n = len(words)
        head = range(0, min(self.window, n))
        tail = range(max(0, n - self.window), n)
        for idx in list(head) + [i for i in tail if i not in head]:
            tok = words[idx]
            if self._is_name(tok):
                position = "start" if idx in head else "end"
                question = self._strip(text, tok)
                return WakeMatch(position=position, alias=tok, question=question)
        return None

    @staticmethod
    def _strip(text: str, alias: str) -> str:
        # Remove the name token (case-insensitive) and tidy leftover punctuation.
        out = re.sub(rf"\b{re.escape(alias)}\b[,.!?]*", "", text, flags=re.IGNORECASE)
        out = re.sub(r"\s{2,}", " ", out).strip(" ,.!?")
        return out
