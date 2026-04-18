"""
数据内容语言判定提示词（极简版）。

与旧版 `STRUCTURED_UNDERSTANDING_USER_PROMPT_TEMPLATE` 一致：`basic_information` 中含自然语言
`language` 字段描述数据主体语言；开源版额外产出稳定码 `content_language`（zh/en/mixed/unknown），
供前端与后续阶段决定展示文案语言（与 UI 语言解耦）。
"""

CONTENT_LANGUAGE_SYSTEM = """You classify the primary language of tabular / JSONL text data samples.
Return ONLY valid JSON with keys:
- "content_language": one of "zh", "en", "mixed", "unknown"
  - "zh" if Chinese is clearly dominant
  - "en" if English is clearly dominant
  - "mixed" if both are substantial in the samples
  - "unknown" if unclear or non CJK/Latin
- "language_label": short human label in English (e.g. "Chinese", "English", "Mixed Chinese-English")
- "confidence": number 0.0-1.0
- "rationale": one short English sentence explaining the decision

Do not include any keys other than these four."""

CONTENT_LANGUAGE_USER_TEMPLATE = """## Manifest metadata (may be empty)
{manifest_meta}

## Raw data sample (first lines, may be truncated)
{raw_sample}

## Seed data sample (first lines, may be truncated)
{seed_sample}

## Optional task / description file sample
{desc_sample}

Classify the primary language of the **data records** (not the manifest keys)."""
