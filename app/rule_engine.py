from __future__ import annotations

import csv
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Sequence, Tuple

from .config import Settings
from .db import Database
from .security import decrypt_value, deterministic_anagram, encrypt_value, hash_text, simple_encrypt


@dataclass(slots=True)
class RuleDefinition:
    id: str
    rule_type: str
    category: str
    action: str
    priority: int = 100
    case_sensitive: bool = False
    word_boundary: bool = True
    pattern: str = ""
    replacement: str = ""
    terms: List[str] = field(default_factory=list)


@dataclass(slots=True)
class RulesetState:
    version: int
    mode: str
    never_reconcile_categories: set[str]
    rules: List[RuleDefinition]


@dataclass(slots=True)
class SanitizationResult:
    original_text: str
    sanitized_text: str
    rules_triggered: List[str]
    transformations: int
    tokens_created: int
    encoded_values: List[str]
    original_hash: str


@dataclass(slots=True)
class _Candidate:
    start: int
    end: int
    value: str
    rule: RuleDefinition


class RuleEngine:
    def __init__(self, settings: Settings, db: Database) -> None:
        self._settings = settings
        self._db = db
        self._lock = Lock()
        self._state = RulesetState(version=1, mode="enforce", never_reconcile_categories=set(), rules=[])
        self.reload()

    @property
    def never_reconcile_categories(self) -> set[str]:
        return set(self._state.never_reconcile_categories)

    def get_rule_counts(self) -> Tuple[int, int]:
        with self._lock:
            all_rules = self._state.rules
            list_rules = [rule for rule in all_rules if rule.rule_type == "list"]
            return len(all_rules), len(list_rules)

    def validate(self) -> Tuple[bool, int, int, str]:
        try:
            self.reload()
            rule_count, list_count = self.get_rule_counts()
            return True, rule_count, list_count, "Valid ruleset"
        except Exception as exc:
            return False, 0, 0, str(exc)

    def reload(self) -> None:
        state = self._load_ruleset()
        with self._lock:
            self._state = state

    def _load_ruleset(self) -> RulesetState:
        ruleset_data = self._read_ruleset_file(self._settings.ruleset_file)
        rules: List[RuleDefinition] = []

        for item in ruleset_data.get("rules", []):
            rule = RuleDefinition(
                id=item.get("id", f"rule_{len(rules) + 1}"),
                rule_type=item.get("type", "regex"),
                category=item.get("category", "GENERAL").upper(),
                action=item.get("action", "tokenize"),
                priority=int(item.get("priority", 100)),
                case_sensitive=bool(item.get("case_sensitive", False)),
                word_boundary=bool(item.get("word_boundary", True)),
                pattern=item.get("pattern", ""),
                replacement=item.get("replacement", ""),
            )
            rules.append(rule)

        declared_list_sources: set[str] = set()
        for item in ruleset_data.get("lists", []):
            source = item.get("source", "")
            if not source:
                continue
            declared_list_sources.add(source)
            list_path = (self._settings.rules_dir / source).resolve()
            terms = self._load_terms(list_path)
            if bool(item.get("include_reversed_word_order", False)):
                terms = self._expand_reversed_word_order(terms)
            rules.append(
                RuleDefinition(
                    id=item.get("id", f"list_{list_path.stem}"),
                    rule_type="list",
                    category=item.get("category", "BUSINESS").upper(),
                    action=item.get("action", "tokenize"),
                    priority=int(item.get("priority", 100)),
                    case_sensitive=bool(item.get("case_sensitive", False)),
                    word_boundary=bool(item.get("word_boundary", True)),
                    terms=terms,
                )
            )

        lists_dir = self._settings.rules_dir / "lists"
        if lists_dir.exists():
            for file_path in sorted(lists_dir.iterdir()):
                if not file_path.is_file():
                    continue
                relative = str(file_path.relative_to(self._settings.rules_dir))
                if relative in declared_list_sources:
                    continue
                if file_path.suffix.lower() not in {".txt", ".csv", ".json"}:
                    continue
                terms = self._load_terms(file_path)
                if not terms:
                    continue
                rules.append(
                    RuleDefinition(
                        id=f"auto_{file_path.stem}",
                        rule_type="list",
                        category="BUSINESS",
                        action="tokenize",
                        priority=90,
                        case_sensitive=False,
                        word_boundary=True,
                        terms=terms,
                    )
                )

        version = int(ruleset_data.get("version", 1))
        mode = str(ruleset_data.get("mode", "enforce"))
        never = set(
            category.upper() for category in ruleset_data.get("never_reconcile_categories", [])
        )
        if not never:
            never = set(self._settings.never_reconcile_categories)

        return RulesetState(version=version, mode=mode, never_reconcile_categories=never, rules=rules)

    def _read_ruleset_file(self, ruleset_file: Path) -> Dict:
        if not ruleset_file.exists():
            raise FileNotFoundError(f"Ruleset not found: {ruleset_file}")

        content = ruleset_file.read_text(encoding="utf-8")
        suffix = ruleset_file.suffix.lower()
        if suffix in {".yml", ".yaml"}:
            try:
                import yaml  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("PyYAML is not installed") from exc
            data = yaml.safe_load(content) or {}
        elif suffix == ".json":
            data = json.loads(content)
        else:
            raise ValueError(f"Unsupported ruleset format: {suffix}")

        if not isinstance(data, dict):
            raise ValueError("Ruleset must be an object")
        return data

    def _load_terms(self, file_path: Path) -> List[str]:
        if not file_path.exists():
            raise FileNotFoundError(f"List file not found: {file_path}")

        suffix = file_path.suffix.lower()
        terms: list[str] = []
        if suffix == ".txt":
            for line in file_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                value = line.strip()
                if value and not value.startswith("#"):
                    terms.append(value)
        elif suffix == ".csv":
            with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
                reader = csv.reader(handle)
                for row in reader:
                    for item in row:
                        value = item.strip()
                        if value:
                            terms.append(value)
        elif suffix == ".json":
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            if isinstance(payload, list):
                terms.extend(str(item).strip() for item in payload if str(item).strip())
            elif isinstance(payload, dict) and isinstance(payload.get("terms"), list):
                terms.extend(str(item).strip() for item in payload["terms"] if str(item).strip())
        else:
            raise ValueError(f"Unsupported list format: {suffix}")

        deduplicated: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = term.strip()
            key = normalized.casefold()
            if not normalized or key in seen:
                continue
            seen.add(key)
            deduplicated.append(normalized)
        return deduplicated

    def _expand_reversed_word_order(self, terms: List[str]) -> List[str]:
        expanded: list[str] = list(terms)
        seen = {item.casefold() for item in expanded}

        for term in terms:
            parts = [piece for piece in term.split() if piece]
            if len(parts) < 2:
                continue
            reversed_term = " ".join(reversed(parts))
            key = reversed_term.casefold()
            if key in seen:
                continue
            seen.add(key)
            expanded.append(reversed_term)

        return expanded

    def sanitize(self, session_id: str, text: str) -> SanitizationResult:
        original = text or ""
        original_hash = hash_text(original)
        if not original:
            return SanitizationResult(
                original_text=original,
                sanitized_text=original,
                rules_triggered=[],
                transformations=0,
                tokens_created=0,
                encoded_values=[],
                original_hash=original_hash,
            )

        with self._lock:
            rules_snapshot = list(self._state.rules)

        candidates: list[_Candidate] = []
        for rule in rules_snapshot:
            if rule.rule_type == "regex" and rule.pattern:
                candidates.extend(self._find_regex_matches(original, rule))
            elif rule.rule_type == "list" and rule.terms:
                candidates.extend(self._find_term_matches(original, rule))

        selected = self._resolve_overlaps(candidates)
        if not selected:
            return SanitizationResult(
                original_text=original,
                sanitized_text=original,
                rules_triggered=[],
                transformations=0,
                tokens_created=0,
                encoded_values=[],
                original_hash=original_hash,
            )

        selected.sort(key=lambda item: item.start)
        cursor = 0
        chunks: list[str] = []
        triggered: set[str] = set()
        tokens_created = 0
        encoded_values: list[str] = []
        encoded_seen: set[str] = set()

        for match in selected:
            chunks.append(original[cursor : match.start])
            replacement, created = self._apply_action(session_id, match.rule, match.value)
            chunks.append(replacement)
            cursor = match.end
            triggered.add(match.rule.id)
            if created:
                tokens_created += 1
            if match.rule.action.lower().strip() == "tokenize":
                key = match.value.casefold()
                if key not in encoded_seen:
                    encoded_seen.add(key)
                    encoded_values.append(match.value)

        chunks.append(original[cursor:])
        sanitized = "".join(chunks)

        return SanitizationResult(
            original_text=original,
            sanitized_text=sanitized,
            rules_triggered=sorted(triggered),
            transformations=len(selected),
            tokens_created=tokens_created,
            encoded_values=encoded_values,
            original_hash=original_hash,
        )

    def reconcile(self, session_id: str, text: str) -> Tuple[str, int, List[str], List[str]]:
        if not text:
            return text, 0, [], []

        token_pattern = re.compile(r"<TKN_[A-Z0-9_]+_[0-9]{3}>")
        tokens = sorted(set(token_pattern.findall(text)), key=len, reverse=True)

        reconciled = text
        replaced_count = 0
        missing: list[str] = []
        decoded_values: list[str] = []
        decoded_seen: set[str] = set()

        for token in tokens:
            category_match = re.match(r"<TKN_([A-Z0-9_]+)_([0-9]{3})>", token)
            category = category_match.group(1) if category_match else ""

            if category.upper() in self._state.never_reconcile_categories:
                continue

            row = self._db.fetchone(
                "SELECT original_value_enc, expires_at FROM token_mappings WHERE session_id = ? AND token = ?",
                (session_id, token),
            )
            if row is None:
                missing.append(token)
                continue

            if row["expires_at"] < datetime.now(timezone.utc).isoformat():
                missing.append(token)
                continue

            original_value = decrypt_value(row["original_value_enc"], self._settings.token_secret)
            occurrences = reconciled.count(token)
            if occurrences == 0:
                continue
            reconciled = reconciled.replace(token, original_value)
            replaced_count += occurrences
            value_key = original_value.casefold()
            if value_key not in decoded_seen:
                decoded_seen.add(value_key)
                decoded_values.append(original_value)

        return reconciled, replaced_count, missing, decoded_values

    def _find_regex_matches(self, text: str, rule: RuleDefinition) -> List[_Candidate]:
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        found: list[_Candidate] = []
        try:
            for match in re.finditer(rule.pattern, text, flags):
                found.append(
                    _Candidate(
                        start=match.start(),
                        end=match.end(),
                        value=match.group(0),
                        rule=rule,
                    )
                )
        except re.error:
            return []
        return found

    def _find_term_matches(self, text: str, rule: RuleDefinition) -> List[_Candidate]:
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        found: list[_Candidate] = []
        for term in rule.terms:
            if not term:
                continue
            escaped = re.escape(term)
            if rule.word_boundary:
                start_boundary = r"\b" if re.match(r"\w", term[0]) else ""
                end_boundary = r"\b" if re.match(r"\w", term[-1]) else ""
                pattern = rf"{start_boundary}{escaped}{end_boundary}"
            else:
                pattern = escaped
            try:
                for match in re.finditer(pattern, text, flags):
                    found.append(
                        _Candidate(
                            start=match.start(),
                            end=match.end(),
                            value=match.group(0),
                            rule=rule,
                        )
                    )
            except re.error:
                continue
        return found

    def _resolve_overlaps(self, candidates: Sequence[_Candidate]) -> List[_Candidate]:
        ordered = sorted(
            candidates,
            key=lambda item: (item.start, -(item.end - item.start), -item.rule.priority),
        )

        accepted: list[_Candidate] = []
        occupied: list[Tuple[int, int]] = []

        for candidate in ordered:
            overlaps = False
            for start, end in occupied:
                if candidate.start < end and start < candidate.end:
                    overlaps = True
                    break
            if overlaps:
                continue
            accepted.append(candidate)
            occupied.append((candidate.start, candidate.end))

        return accepted

    def _apply_action(self, session_id: str, rule: RuleDefinition, value: str) -> Tuple[str, bool]:
        action = rule.action.lower().strip()
        if action == "replace":
            replacement = rule.replacement or f"[{rule.category}]"
            return replacement, False
        if action == "anagram":
            return deterministic_anagram(value, self._settings.token_secret), False
        if action == "simple_encrypt":
            return simple_encrypt(value, self._settings.token_secret), False
        if action == "tokenize":
            token, created = self._get_or_create_token(session_id, value, rule.category)
            return token, created
        return value, False

    def _get_or_create_token(self, session_id: str, value: str, category: str) -> Tuple[str, bool]:
        normalized_category = self._normalize_category(category)
        value_hash = hash_text(f"{normalized_category}|{value.casefold().strip()}")

        row = self._db.fetchone(
            "SELECT token FROM token_mappings WHERE session_id = ? AND value_hash = ? AND category = ?",
            (session_id, value_hash, normalized_category),
        )
        if row is not None:
            return row["token"], False

        row_count = self._db.fetchone(
            "SELECT COUNT(*) AS count FROM token_mappings WHERE session_id = ? AND category = ?",
            (session_id, normalized_category),
        )
        next_index = (row_count or {"count": 0})["count"] + 1
        token = f"<TKN_{normalized_category}_{next_index:03d}>"

        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=self._settings.token_ttl_days)
        self._db.execute(
            """
            INSERT INTO token_mappings (
                id, session_id, token, value_hash, original_value_enc, category, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                session_id,
                token,
                value_hash,
                encrypt_value(value, self._settings.token_secret),
                normalized_category,
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        return token, True

    @staticmethod
    def _normalize_category(category: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "_", category.upper()).strip("_")
        return cleaned or "GENERIC"
