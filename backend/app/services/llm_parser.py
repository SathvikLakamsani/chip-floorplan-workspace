"""LLM-backed natural-language command parser.

This is the open-ended counterpart to the deterministic rule-based parser.
It converts free-form instructions (e.g. "push the memory banks toward the
bottom-left and give the router more breathing room") into the same structured
CommandAction list that the rest of the system already knows how to apply.

Design goals:
- Provider-agnostic: supports Anthropic (Claude), OpenAI (GPT), and Google
  (Gemini).
- Zero-config safe: if no API key is present, `is_configured()` returns False
  and the caller falls back to the rule-based parser. No key => no crash.
- Structured output: the model is asked for strict JSON matching our action
  schema; output is validated into CommandAction objects and unknown/invalid
  actions are dropped.

Environment variables:
    LLM_PROVIDER      "anthropic" | "openai" | "gemini" (optional; auto-detected)
    ANTHROPIC_API_KEY Anthropic key
    OPENAI_API_KEY    OpenAI key
    GEMINI_API_KEY    Google Gemini key (GOOGLE_API_KEY also accepted)
    LLM_MODEL         Override the default model name (optional)
"""

from __future__ import annotations

import json
import os
import re

from app.models.layout import ActionType, CommandAction, Layout

DEFAULT_ANTHROPIC_MODEL = "claude-3-5-sonnet-latest"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"

_VALID_ACTION_TYPES = {a.value for a in ActionType}


class LLMError(Exception):
    """Raised when the LLM call or its output parsing fails."""


class LLMCommandParser:
    """Convert free-form commands into structured actions via an LLM."""

    def __init__(self) -> None:
        self.anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        self.openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.gemini_key = (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )
        self.provider = self._resolve_provider()
        self.model = os.environ.get("LLM_MODEL", "").strip() or self._default_model()

    def _resolve_provider(self) -> str | None:
        keys = {
            "anthropic": self.anthropic_key,
            "openai": self.openai_key,
            "gemini": self.gemini_key,
        }
        explicit = os.environ.get("LLM_PROVIDER", "").strip().lower()
        # Honor an explicit choice only if the matching key exists.
        if explicit in keys and keys[explicit]:
            return explicit
        # Otherwise auto-detect from whichever key is present.
        for provider in ("anthropic", "openai", "gemini"):
            if keys[provider]:
                return provider
        return None

    def _default_model(self) -> str:
        if self.provider == "openai":
            return DEFAULT_OPENAI_MODEL
        if self.provider == "gemini":
            return DEFAULT_GEMINI_MODEL
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
            "You translate ANY natural-language layout instruction into a strict "
            "JSON list of structured actions. You are the primary interpreter — "
            "handle open-ended, macro-level requests (adding/removing components, "
            "restructuring, resizing the die, wiring up nets), not just small "
            "nudges. You NEVER apply changes yourself; the tool previews your "
            "actions before applying.\n\n"
            "Coordinate system: origin (0,0) is top-left. x increases to the "
            "right, y increases downward. Units are microns.\n\n"
            "Return ONLY a JSON object of this exact shape (no prose, no code "
            "fences):\n"
            "{\n"
            '  "actions": [ { "type": ..., "targets": [...], "reason": ..., "params": {...} } ],\n'
            '  "explanation": "one-sentence plain-English summary"\n'
            "}\n\n"
            "You may return MULTIPLE actions to satisfy one instruction (e.g. add "
            "a block, then connect it with a net, then make room around it).\n\n"
            "Valid action types and their params:\n"
            "MOVEMENT & PROPERTIES:\n"
            '- "move_blocks": targets = block ids. params is ONE of:\n'
            '    {"mode":"toward","anchor":"<block_id>","factor":0.0-1.0}\n'
            '    {"mode":"delta","dx":<microns>,"dy":<microns>}\n'
            '    {"mode":"absolute","x":<microns>,"y":<microns>}\n'
            '    {"mode":"region","region":"top_left|top_right|bottom_left|bottom_right|center","factor":0.0-1.0}\n'
            '    {"mode":"spread","factor":>1.0}\n'
            '    {"mode":"separate","margin":<microns>}   (resolve overlaps between targets)\n'
            '    {"mode":"timing_optimize"}\n'
            '- "lock_blocks" / "unlock_blocks": targets = block ids. params = {}\n'
            '- "resize_blocks": targets = block ids. params = {"delta_width":<microns>,"delta_height":<microns>}\n'
            '- "update_property": targets = block ids. params = {"property":"fixed|power|criticality|clock_domain|voltage_domain|orientation|type|class","value":<value>}\n'
            '- "align_blocks": targets = block ids. params = {"edge":"left|right|top|bottom|centerx|centery"}\n'
            '- "distribute_blocks": targets = block ids (>=3). params = {"axis":"x|y"} (even spacing)\n'
            '- "add_keepout": targets = block ids. params = {"margin":<microns>}\n'
            '- "add_constraint": targets = block ids. params = {"constraint_type":"proximity|fixed|clock|keepout","priority":"low|medium|high"}\n'
            "STRUCTURAL EDITS (create / remove / duplicate):\n"
            '- "add_block": create a NEW block. targets = []. params = {"name":"<label>","type":"compute|sram|memory|noc|io|pll|clock|controller|analog|other","width":<microns>,"height":<microns>,"x":<optional>,"y":<optional>,"power":<optional W>,"criticality":0.0-1.0}. If x/y omitted it is placed near the core center and de-overlapped automatically.\n'
            '- "clone_block": duplicate existing blocks. targets = block ids. params = {"dx":<microns>,"dy":<microns>,"name":"<optional>"}\n'
            '- "remove_block": delete blocks (and their nets). targets = block ids. params = {}\n'
            '- "add_net": connect blocks. targets = []. params = {"source":"<block_id>","sinks":["<block_id>",...],"name":"<optional>","criticality":0.0-1.0,"type":"signal|clock|power|ground"}\n'
            '- "remove_net": delete nets. targets = NET ids. params = {}\n'
            '- "set_chip": resize the die/core. targets = []. params = {"width":<microns>,"height":<microns>} or {"die":{"x","y","width","height"},"core":{...}}\n'
            "META:\n"
            '- "generate_candidates": params = {"count":2-3}. targets = []\n\n'
            "Rules:\n"
            "- Only reference block ids / net ids that exist in the provided layout (except when creating new ones via add_block/add_net).\n"
            "- Never move, resize, align, or distribute a block whose \"fixed\" is true.\n"
            "- When the user asks to add something, ALWAYS use add_block (and add_net if a connection is implied) — do not refuse.\n"
            "- Choose a sensible type/class and size from context (e.g. an SRAM ~ 120x160, an IO pad ~ 40x40).\n"
            "- Prefer the simplest action set that satisfies the instruction.\n"
            "- Always include a short human-readable \"reason\" per action.\n"
        )

    def _build_user_prompt(self, command: str, layout: Layout) -> str:
        blocks = [
            {
                "id": b.id,
                "name": b.name,
                "type": b.type if isinstance(b.type, str) else b.type.value,
                "class": b.cls if isinstance(b.cls, str) else b.cls.value,
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
                "type": n.type if isinstance(n.type, str) else n.type.value,
            }
            for n in layout.nets
        ]
        core = layout.chip.core
        context = {
            "chip": {
                "name": layout.chip.name,
                "width": layout.chip.width,
                "height": layout.chip.height,
                "core": (
                    {"x": core.x, "y": core.y, "width": core.width, "height": core.height}
                    if core
                    else None
                ),
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
        if self.provider == "gemini":
            return self._call_gemini(httpx, system_prompt, user_prompt)
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

    def _call_gemini(self, httpx, system_prompt: str, user_prompt: str) -> str:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self.model}:generateContent"
        )
        try:
            resp = httpx.post(
                url,
                headers={
                    "x-goog-api-key": self.gemini_key,
                    "Content-Type": "application/json",
                },
                json={
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [
                        {"role": "user", "parts": [{"text": user_prompt}]}
                    ],
                    "generationConfig": {
                        "temperature": 0.2,
                        "responseMimeType": "application/json",
                    },
                },
                timeout=30.0,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"Gemini request failed: {exc}") from exc
        if resp.status_code != 200:
            raise LLMError(f"Gemini API error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                # A prompt/safety block returns no candidates.
                feedback = data.get("promptFeedback", {})
                raise LLMError(f"Gemini returned no candidates: {feedback}")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, AttributeError) as exc:
            raise LLMError(f"Unexpected Gemini response shape: {exc}") from exc

    # ------------------------------------------------------------------
    # Output parsing / validation
    # ------------------------------------------------------------------
    def _parse_output(
        self, raw: str, layout: Layout
    ) -> tuple[list[CommandAction], str]:
        payload = self._extract_json(raw)
        valid_ids = {b.id for b in layout.blocks}
        valid_net_ids = {n.id for n in layout.nets}
        fixed_ids = {b.id for b in layout.blocks if b.fixed}

        # Actions that create objects or act globally: no existing target required.
        no_target_required = {
            ActionType.ADD_BLOCK.value,
            ActionType.ADD_NET.value,
            ActionType.SET_CHIP.value,
            ActionType.GENERATE_CANDIDATES.value,
            ActionType.SET_OVERLAY.value,
            ActionType.EXPLAIN.value,
        }
        # Actions that may not touch fixed blocks.
        movement_actions = {
            ActionType.MOVE_BLOCKS.value,
            ActionType.RESIZE_BLOCKS.value,
            ActionType.ALIGN_BLOCKS.value,
            ActionType.DISTRIBUTE_BLOCKS.value,
        }

        actions: list[CommandAction] = []
        for item in payload.get("actions", []):
            if not isinstance(item, dict):
                continue
            atype = item.get("type")
            if atype not in _VALID_ACTION_TYPES:
                continue

            raw_targets = item.get("targets", []) or []

            if atype == ActionType.REMOVE_NET.value:
                # Targets are net ids here.
                targets = [t for t in raw_targets if t in valid_net_ids]
                if not targets:
                    continue
            elif atype in no_target_required:
                # Keep any valid block ids but don't require them.
                targets = [t for t in raw_targets if t in valid_ids]
            else:
                targets = [t for t in raw_targets if t in valid_ids]
                if atype in movement_actions:
                    targets = [t for t in targets if t not in fixed_ids]
                if not targets:
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
