"""LLM-backed natural-language command parser.

This is the open-ended counterpart to the deterministic rule-based parser.
It converts free-form instructions (e.g. "push the memory banks toward the
bottom-left and give the router more breathing room") into the same structured
CommandAction list that the rest of the system already knows how to apply.

Design goals:
- Provider-agnostic: supports Anthropic (Claude) and OpenAI (GPT).
- Zero-config safe: if no API key is present, `is_configured()` returns False
  and the caller falls back to the rule-based parser. No key => no crash.
- Structured output: the model is asked for strict JSON matching our action
  schema; output is validated into CommandAction objects and unknown/invalid
  actions are dropped.

Environment variables:
    LLM_PROVIDER      "anthropic" | "openai"  (optional; auto-detected from keys)
    ANTHROPIC_API_KEY Anthropic key
    OPENAI_API_KEY    OpenAI key
    LLM_MODEL         Override the default model name (optional)
"""

from __future__ import annotations

import json
import os
import re

from app.models.layout import ActionType, CommandAction, Layout

DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"

_VALID_ACTION_TYPES = {a.value for a in ActionType}


class LLMError(Exception):
    """Raised when the LLM call or its output parsing fails."""


class LLMCommandParser:
    """Convert free-form commands into structured actions via an LLM."""

    def __init__(self) -> None:
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.provider = self._resolve_provider()
        self.model = os.environ.get("LLM_MODEL", "").strip() or self._default_model()

    def _resolve_provider(self) -> str | None:
        explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
        if explicit in ("anthropic", "openai"):
            # Honor explicit choice only if the matching key exists.
            if explicit == "anthropic" and self.anthropic_key:
                return "anthropic"
            if explicit == "openai" and self.openai_key:
                return "openai"
        if self.anthropic_key:
            return "anthropic"
        if self.openai_key:
            return "openai"
        return None

    def _default_model(self) -> str:
        if self.provider == "openai":
            return DEFAULT_OPENAI_MODEL
        return DEFAULT_ANTHROPIC_MODEL

    def is_configured(self) -> bool:
        """True if an API key is available and a provider is selected."""
        return self.provider is not None

    def parse(self, command: str, layout: Layout) -> tuple[list[CommandAction], str]:
        """Return (actions, explanation) for a free-form command.

        Raises LLMError if not configured or if the call/parse fails.
        """
        if not self.is_configured():
            raise LLMError("No LLM provider configured.")

        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(command, layout)
        raw = self._call_model(system_prompt, user_prompt)
        return self._parse_output(raw, layout)

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------
    def _build_system_prompt(self) -> str:
        return (
            "You are a physical-design assistant for a chip floorplanning tool. "
            "You translate a natural-language layout instruction into a strict "
            "JSON list of structured actions. You NEVER apply changes yourself; "
            "you only propose actions that the tool will preview before applying.\n\n"
            "Coordinate system: origin (0,0) is top-left. x increases to the "
            "right, y increases downward. Units are microns.\n\n"
            "Return ONLY a JSON object of this exact shape (no prose, no code "
            "fences):\n"
            "{\n"
            '  "actions": [ { "type": ..., "targets": [...], "reason": ..., "params": {...} } ],\n'
            '  "explanation": "one-sentence plain-English summary"\n'
            "}\n\n"
            "Valid action types and their params:\n"
            '- "move_blocks": move one or more blocks. targets = block ids. params is ONE of:\n'
            '    {"mode":"toward","anchor":"<block_id>","factor":0.0-1.0}  (move fraction of the way toward another block)\n'
            '    {"mode":"delta","dx":<microns>,"dy":<microns>}            (relative shift; +dx right, +dy down)\n'
            '    {"mode":"absolute","x":<microns>,"y":<microns>}           (set position; use for a single target)\n'
            '    {"mode":"region","region":"top_left|top_right|bottom_left|bottom_right|center","factor":0.0-1.0}\n'
            '    {"mode":"spread","factor":>1.0}                           (push targets apart from their shared center)\n'
            '    {"mode":"timing_optimize"}                                (cluster high-criticality connected targets)\n'
            '- "lock_blocks": pin blocks so they cannot move. targets = block ids. params = {}\n'
            '- "resize_blocks": params = {"delta_width":<microns>,"delta_height":<microns>}\n'
            '- "update_property": params = {"property":"fixed|power|criticality|clock_domain|voltage_domain","value":<value>}\n'
            '- "generate_candidates": params = {"count":2-3}. targets = []\n\n'
            "Rules:\n"
            "- Only reference block ids that exist in the provided layout.\n"
            "- Never move or resize a block whose \"fixed\" is true.\n"
            "- Prefer the simplest action set that satisfies the instruction.\n"
            "- Always include a short human-readable \"reason\" per action.\n"
        )

    def _build_user_prompt(self, command: str, layout: Layout) -> str:
        blocks = [
            {
                "id": b.id,
                "name": b.name,
                "type": b.type if isinstance(b.type, str) else b.type.value,
                "x": b.x,
                "y": b.y,
                "width": b.width,
                "height": b.height,
                "fixed": b.fixed,
                "criticality": b.criticality,
            }
            for b in layout.blocks
        ]
        nets = [
            {
                "id": n.id,
                "source": n.source,
                "sinks": n.sinks,
                "criticality": n.criticality,
            }
            for n in layout.nets
        ]
        context = {
            "chip": {
                "name": layout.chip.name,
                "width": layout.chip.width,
                "height": layout.chip.height,
            },
            "blocks": blocks,
            "nets": nets,
        }
        return (
            f"Layout:\n{json.dumps(context, indent=2)}\n\n"
            f'Instruction: "{command}"\n\n'
            "Return the JSON object now."
        )

    # ------------------------------------------------------------------
    # Provider calls
    # ------------------------------------------------------------------
    def _call_model(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover
            raise LLMError("httpx is required for LLM calls (pip install httpx).") from exc

        if self.provider == "anthropic":
            return self._call_anthropic(httpx, system_prompt, user_prompt)
        if self.provider == "openai":
            return self._call_openai(httpx, system_prompt, user_prompt)
        raise LLMError("No LLM provider configured.")

    def _call_anthropic(self, httpx, system_prompt: str, user_prompt: str) -> str:
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Anthropic request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Anthropic API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            return "".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            )
        except (KeyError, AttributeError) as exc:
            raise LLMError(f"Unexpected Anthropic response shape: {exc}") from exc

    def _call_openai(self, httpx, system_prompt: str, user_prompt: str) -> str:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"OpenAI request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"OpenAI API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected OpenAI response shape: {exc}") from exc

    # ------------------------------------------------------------------
    # Output parsing / validation
    # ------------------------------------------------------------------
    def _parse_output(
        self, raw: str, layout: Layout
    ) -> tuple[list[CommandAction], str]:
        payload = self._extract_json(raw)
        valid_ids = {b.id for b in layout.blocks}
        fixed_ids = {b.id for b in layout.blocks if b.fixed}

        actions: list[CommandAction] = []
        for item in payload.get("actions", []):
            if not isinstance(item, dict):
                continue
            atype = item.get("type")
            if atype not in _VALID_ACTION_TYPES:
                continue

            targets = [t for t in item.get("targets", []) if t in valid_ids]
            # Never let move/resize touch fixed blocks.
            if atype in (
                ActionType.MOVE_BLOCKS.value,
                ActionType.RESIZE_BLOCKS.value,
            ):
                targets = [t for t in targets if t not in fixed_ids]
                if not targets:
                    continue
            elif atype != ActionType.GENERATE_CANDIDATES.value and not targets:
                continue

            actions.append(
                CommandAction(
                    type=atype,
                    targets=targets,
                    reason=str(item.get("reason", "")),
                    params=item.get("params", {}) or {},
                )
            )

        explanation = str(payload.get("explanation", "")).strip()
        if not actions:
            raise LLMError(
                "The AI did not return any applicable actions for this command."
            )
        if not explanation:
            explanation = "Proposed layout changes based on your instruction."
        return actions, explanation

    def _extract_json(self, raw: str) -> dict:
        text = raw.strip()
        # Strip markdown code fences if present.
        if text.startswith("```"):
            text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Fallback: grab the first balanced-looking JSON object.
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError as exc:
                    raise LLMError(f"Could not parse LLM JSON output: {exc}") from exc
            raise LLMError("LLM output did not contain valid JSON.")
