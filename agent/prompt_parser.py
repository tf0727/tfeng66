"""Parse structured Markdown prompt sections."""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class PromptDocument:
    sections: dict[str, str]

    @property
    def rules(self) -> str:
        return self.sections.get("铁律", "")

    @property
    def tone(self) -> str:
        return self.sections.get("语气", "")

    def validate(self) -> list[str]:
        errors: list[str] = []
        for required in ("铁律", "语气"):
            if not self.sections.get(required, "").strip():
                errors.append(f"必须保留非空 section：## {required}")
        if not any(line.strip() for line in self.rules.splitlines()):
            errors.append("## 铁律 至少需要一条规则")
        return errors


def parse_prompt(markdown: str) -> PromptDocument:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return PromptDocument({name: "\n".join(lines).strip() for name, lines in sections.items()})

