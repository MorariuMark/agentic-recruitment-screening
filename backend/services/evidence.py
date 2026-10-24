"""Source-backed text matching and shared language screening policy."""
import re
import unicodedata
import json
from functools import lru_cache
from collections import defaultdict

from backend.services.skill_equivalence import CEFR_LEVELS

TOKEN = re.compile(r"\w+[+#]*", re.UNICODE)
TIER_LABEL = re.compile(r"\s*(?:\((?:REJECT|BORDERLINE|STRONG)\s+Tier\)|\[tier[_ -]?\d+\])", re.I)
LANGUAGES = {
    "german": ["german", "deutsch", "germana", "germană"], "english": ["english", "englisch", "engleza", "engleză"],
    "french": ["french", "français", "francais", "franceza", "franceză"], "romanian": ["romanian", "română", "romana"],
    "spanish": ["spanish", "español"], "italian": ["italian", "italiano"],
    "dutch": ["dutch", "nederlands"],
}


def clean_model_text(text: str) -> str:
    """Exclude benchmark answers from derived model inputs, preserving stored originals."""
    return TIER_LABEL.sub("", text or "")


def is_benchmark_profile(profile: dict) -> bool:
    return profile.get("dataset") == "benchmark" or bool(TIER_LABEL.search(json.dumps(profile, ensure_ascii=False)))


@lru_cache(maxsize=128)
def _source_tokens(source):
    spans = list(TOKEN.finditer(source or ""))
    actual = [unicodedata.normalize("NFKC", m.group()).lower() for m in spans]
    positions = defaultdict(list)
    for index, token in enumerate(actual):
        positions[token].append(index)
    return spans, actual, positions


def source_quote(source: str, quote: str) -> str | None:
    """Return the original span for contiguous equal tokens; never trust parsed text."""
    normalize = lambda word: unicodedata.normalize("NFKC", word).lower()
    wanted = [normalize(m.group()) for m in TOKEN.finditer(quote or "")]
    if not wanted:
        return None
    source_tokens, actual, positions = _source_tokens(source or "")
    for index in positions.get(wanted[0], []):
        if actual[index:index + len(wanted)] == wanted:
            return source[source_tokens[index].start():source_tokens[index + len(wanted) - 1].end()]
    return None


def _contains(text, word):
    return bool(re.search(r"(?<!\w)" + re.escape(word) + r"(?!\w)", text, re.I))


def language_target(requirement):
    title = requirement.title.casefold()
    if any(word in title for word in ["location", "relocat", "presence", "visa", "on-site", "work permit"]):
        return None
    text = f"{requirement.title} {requirement.description}".casefold()
    return next((name for name, aliases in LANGUAGES.items() if any(_contains(text, alias) for alias in aliases)), None)


def language_level(text):
    explicit = re.findall(r"\b([a-c][12])\b", text.casefold())
    if explicit:
        # A range such as B1/B2 does not establish its upper endpoint.
        return min(CEFR_LEVELS[level] for level in explicit)
    return next((CEFR_LEVELS[word] for word in sorted(CEFR_LEVELS, key=len, reverse=True)
                 if _contains(text, word)), None)


def assess_language(candidate, requirement):
    target = language_target(requirement)
    if target is None:
        return None
    text = f"{requirement.title} {requirement.description}"
    required = language_level(text)
    matching = [item for item in candidate.anonymized_languages
                if any(_contains(item.language, alias) for alias in LANGUAGES[target])]
    levels = [language_level(f"{item.language} {item.proficiency or ''}") for item in matching]
    known = [level for level in levels if level is not None]
    if not matching:
        return "unknown", 0, f"{target.title()} proficiency is not documented; clarify with the candidate."
    if required is None:
        return "supported", 100, f"{target.title()} is documented; the role specifies no minimum proficiency level."
    if not known:
        return "unknown", 0, f"The documented {target} entry does not specify the required proficiency level."
    if max(known) >= required:
        return "supported", 100, f"Documented {target} proficiency satisfies the stated level."
    return "contradicted", 0, f"Documented {target} proficiency is below the stated level; recruiter review required."


def language_priority(candidate, job):
    """Documented mandatory languages and recruiter evidence gates precede unknowns."""
    checks = [assess_language(candidate, req) for req in job.requirements
              if req.category == "must_have" and req.weight > 0]
    checks = [check for check in checks if check is not None]
    if any(check[0] == "contradicted" for check in checks):
        return 2
    required_phrases = [req.eligibility_evidence.strip() for req in job.requirements
                        if req.category == "must_have" and req.weight > 0 and req.eligibility_evidence and req.eligibility_evidence.strip()]
    missing_required_evidence = any(source_quote(clean_model_text(candidate.sanitized_text), phrase) is None
                                    for phrase in required_phrases)
    if missing_required_evidence or any(check[0] == "unknown" for check in checks):
        return 1
    return 0


def documented_language_quote(candidate, requirement):
    target = language_target(requirement)
    if not target:
        return None
    for item in candidate.anonymized_languages:
        if not any(_contains(item.language, alias) for alias in LANGUAGES[target]):
            continue
        for alias in LANGUAGES[target]:
            quote = source_quote(candidate.sanitized_text, f"{alias} {item.proficiency or ''}")
            if quote:
                return quote
            descriptors = re.findall(r"[\w]+", item.proficiency or '')
            for descriptor in descriptors:
                if language_level(descriptor) is None:
                    continue
                for wording in (f"{alias} {descriptor}", f"{descriptor} {alias}"):
                    quote = source_quote(candidate.sanitized_text, wording)
                    if quote and language_level(descriptor) >= (language_level(f"{requirement.title} {requirement.description}") or 0):
                        return quote
            if (item.proficiency or '').casefold() in ('native', 'mother tongue'):
                match = re.search(r"mother\s+tongue(?:\(s\))?\s*:\s*" + re.escape(alias), candidate.sanitized_text, re.I)
                if match:
                    return match.group()
        # PDF columns can separate the language name from its proficiency. A
        # language-list entry supports presence, not an inferred Native/C1 level.
        if language_level(f"{requirement.title} {requirement.description}") is None:
            for alias in LANGUAGES[target]:
                for line in re.finditer(r"(?im)^.*$", candidate.sanitized_text):
                    value = line.group().strip()
                    if re.match(r"(?i)^(?:spoken\s+)?languages?(?:\s+skills)?\s*[:\-]", value) and _contains(value, alias):
                        if not re.search(r"\b(?:no|not|cannot)\b", value, re.I):
                            return value
                    names = {name.casefold() for aliases in LANGUAGES.values() for name in aliases}
                    tokens = {token.group().casefold() for token in TOKEN.finditer(value)}
                    is_language_list = bool(tokens) and tokens <= names and _contains(value, alias)
                    if is_language_list:
                        preceding = candidate.sanitized_text[max(0, line.start() - 4000):line.start()]
                        if re.search(r"(?im)^\s*(?:mother\s+tongue(?:\(s\))?|(?:other\s+)?languages?(?:\(s\))?(?:\s+skills)?|personal\s+skills)\s*:?[ \t]*$", preceding):
                            return value
    return None


def source_passages(source, max_chars=1400):
    """Bound source passages without replacing text or losing citation provenance."""
    passages = re.split(r"\n\s*\n|(?<=[.!?])\s+", source or '')
    bounded = []
    for passage in passages:
        start = 0
        while len(passage) - start > max_chars:
            end = passage.rfind(" ", start + max_chars // 2, start + max_chars)
            if end < 0:
                end = start + max_chars
            bounded.append(passage[start:end])
            start = end
        if passage[start:].strip():
            bounded.append(passage[start:])
    return bounded


def ticket_evidence(text):
    """Recognize service tools/workflows without accepting mathematical queues."""
    return bool(re.search(
        r"\b(?:tickets?|ticketing|service[\s-]*now|jira|zendesk|fresh[\s-]*(?:desk|service)|"
        r"otrs|osticket|glpi|connectwise|autotask|bmc\s+remedy|manageengine|"
        r"help[\s-]*desk|service\s+(?:requests?|desk)|support\s+cases?|incidents?)\b",
        text, re.I))


def relevant_source_passages(source, requirement, limit=3):
    """Select original source paragraphs; generated profile headings are never proof."""
    terms = {m.group().casefold() for m in TOKEN.finditer(requirement)
             if len(m.group()) > 2 and m.group().casefold() not in {'the', 'and', 'for', 'with', 'required', 'ability', 'experience'}}
    passages = source_passages(source)
    ticket_requirement = bool(terms & {"ticket", "tickets", "ticketing"})
    if ticket_requirement:
        # Mathematical queues alone do not establish IT service-management evidence.
        passages = [p for p in passages if ticket_evidence(p)]
    scored = [(len(terms & {m.group().casefold() for m in TOKEN.finditer(p)}) +
               (1 if ticket_requirement else 0), i, p)
              for i, p in enumerate(passages) if p.strip()]
    return [p for score, _, p in sorted(scored, key=lambda item: (-item[0], item[1]))[:limit] if score > 0]
