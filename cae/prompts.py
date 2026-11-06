"""System prompts for the three variants and the summarizer.

companion_no_flag and companion_may_flag are built from one base text with a
single placeholder, so they are identical word for word except for the speech
recognition rule. That is what lets the comparison isolate this one rule.
"""

from .schema import ROOT

PROMPT_DIR = ROOT / "prompts"
PLACEHOLDER = "{{ASR_RULE}}"

VARIANTS = ["neutral", "companion_no_flag", "companion_may_flag"]


def _read(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8").strip()


def system_prompt(variant: str) -> str:
    if variant == "neutral":
        return _read("neutral.de.md")
    if variant in ("companion_no_flag", "companion_may_flag"):
        base = _read("companion_base.de.md")
        assert base.count(PLACEHOLDER) == 1, "companion base must contain the rule placeholder once"
        rule = _read("asr_rule_no_flag.de.md" if variant.endswith("no_flag") else "asr_rule_may_flag.de.md")
        return base.replace(PLACEHOLDER, rule)
    raise ValueError(f"unknown prompt variant {variant!r}")


def summarizer_prompt(variant: str = "standard") -> str:
    return _read(f"summarizer_{variant}.de.md")
