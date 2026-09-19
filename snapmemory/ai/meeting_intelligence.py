"""
SnapMemory Meeting Intelligence.

Extracts summary / decisions / action items / open questions / dates /
topics / people from a transcript.

Honest note: a real deployment would run a local LLM (Qualcomm AI Hub LLM
or a local llama.cpp GGUF model on the Snapdragon NPU/CPU) over the
transcript with a structured-extraction prompt. No local LLM runtime is
available in this offline authoring sandbox (no torch/transformers/GGUF
runtime installed, no network to fetch one), so this module ships a
transparent, deterministic, RULE-BASED extractor: regex + heuristics over
segment text. It never invents a name, date, or decision that isn't present
in the transcript — if nothing is found, it says so explicitly, exactly as
the build spec requires for the neural path too.

Swapping in a real local LLM: implement `LlmMeetingExtractor` in
ai/rag.py's LLM provider and call it here instead of `_rule_based_extract`.
No other code changes needed — the return shape is identical.
"""
import re

DECISION_MARKERS = re.compile(
    r"\b(we (?:decided|will use|are using|agreed)|decision(?:s)?[:\-]|"
    r"let'?s go with|final(?:ize|ized)? on)\b", re.IGNORECASE)

ACTION_MARKERS = re.compile(
    r"\b([A-Z][a-zA-Z]+) (?:will|is going to|to|should) (?:handle|own|take|do|build|write|finish|review|deploy|deliver)\b"
)

QUESTION_MARKERS = re.compile(r"([^.!?\n]{5,200}\?)")

DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/\-]\d{1,2}(?:[/\-]\d{2,4})?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?|"
    r"\d{4}-\d{2}-\d{2}|"
    r"\b(?:next|this)\s+(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|week|month)\b|"
    r"\btomorrow\b|\bEOD\b|\bEOW\b)",
    re.IGNORECASE)

NAME_PATTERN = re.compile(r"\b([A-Z][a-z]{1,20})\b")

STOPWORD_CAPS = {"The", "This", "That", "We", "I", "It", "They", "SnapMemory",
                 "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                 "Saturday", "Sunday", "January", "February", "March", "April",
                 "May", "June", "July", "August", "September", "October",
                 "November", "December"}


def _sentences(text: str):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def extract(transcript: str, segments: list[dict] | None = None) -> dict:
    if not transcript or not transcript.strip():
        return {
            "summary": "Not found in the available meeting information.",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "important_dates": [],
            "topics": [],
            "people": [],
        }

    sentences = _sentences(transcript)

    decisions = [s for s in sentences if DECISION_MARKERS.search(s)]

    action_items = []
    for s in sentences:
        for m in ACTION_MARKERS.finditer(s):
            person = m.group(1)
            if person in STOPWORD_CAPS:
                continue
            dates_in_sentence = DATE_PATTERN.findall(s)
            action_items.append({
                "task": s.strip(),
                "person": person,
                "deadline": dates_in_sentence[0] if dates_in_sentence else None,
                "confidence": "medium",
                "source_excerpt": s.strip()[:200],
            })

    open_questions = QUESTION_MARKERS.findall(transcript)

    important_dates = sorted(set(DATE_PATTERN.findall(transcript)), key=lambda d: transcript.find(d))

    # People mentioned: capitalized tokens that repeat, excluding stopwords / sentence starts only.
    name_counts = {}
    for s in sentences:
        for m in NAME_PATTERN.finditer(s):
            name = m.group(1)
            if name in STOPWORD_CAPS or len(name) < 2:
                continue
            name_counts[name] = name_counts.get(name, 0) + 1
    people = [n for n, c in sorted(name_counts.items(), key=lambda kv: -kv[1]) if c >= 2][:10]

    # Topics: most frequent non-trivial words as a crude keyword summary
    words = re.findall(r"[a-zA-Z]{4,}", transcript.lower())
    stop = {"that", "this", "with", "have", "will", "were", "they", "them",
            "from", "there", "about", "which", "should", "would", "could",
            "going", "think", "really", "just", "also", "meeting"}
    freq = {}
    for w in words:
        if w in stop:
            continue
        freq[w] = freq.get(w, 0) + 1
    topics = [w for w, c in sorted(freq.items(), key=lambda kv: -kv[1])[:8] if c >= 2]

    summary_sentences = sentences[:3] if len(sentences) <= 6 else (
        [sentences[0]] + decisions[:2]
    )
    summary = " ".join(dict.fromkeys(summary_sentences)) or "Not found in the available meeting information."

    return {
        "summary": summary,
        "decisions": decisions if decisions else [],
        "action_items": action_items,
        "open_questions": open_questions,
        "important_dates": important_dates,
        "topics": topics,
        "people": people,
    }
