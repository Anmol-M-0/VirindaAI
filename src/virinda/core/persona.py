from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PersonaProfile:
    name: str
    description: str
    system_prompt_modifier: str
    speech_rate_multiplier: float = 1.0
    concise: bool = False


BUILTIN_PERSONAS: dict[str, PersonaProfile] = {
    "default": PersonaProfile(
        name="default",
        description="Balanced, helpful, and natural ambient voice assistant.",
        system_prompt_modifier="Respond naturally, accurately, and politely.",
        speech_rate_multiplier=1.0,
        concise=False,
    ),
    "concise": PersonaProfile(
        name="concise",
        description="Telegraphic, brief responses optimized for rapid voice interaction.",
        system_prompt_modifier="Be extremely brief, direct, and concise. Omit filler words and pleasantries. Max 1-2 sentences unless asked for detail.",
        speech_rate_multiplier=1.1,
        concise=True,
    ),
    "technical": PersonaProfile(
        name="technical",
        description="Deep technical accuracy, exact code terminology, and architectural precision.",
        system_prompt_modifier="Provide precise technical details, architectural nuances, and exact terminology.",
        speech_rate_multiplier=1.0,
        concise=False,
    ),
    "creative": PersonaProfile(
        name="creative",
        description="Expressive, empathetic, and imaginative conversationalist.",
        system_prompt_modifier="Be warm, creative, engaging, and imaginative in your answers.",
        speech_rate_multiplier=0.95,
        concise=False,
    ),
}


class PersonaManager:
    """Manages active assistant persona and system prompt tailoring."""

    def __init__(self, default_persona: str = "default") -> None:
        self._personas = dict(BUILTIN_PERSONAS)
        self._active_persona_name = (
            default_persona if default_persona in self._personas else "default"
        )

    @property
    def active_persona(self) -> PersonaProfile:
        return self._personas.get(self._active_persona_name, self._personas["default"])

    def set_persona(self, persona_name: str) -> PersonaProfile:
        name = persona_name.lower().strip()
        if name not in self._personas:
            raise ValueError(
                f"Unknown persona '{persona_name}'. Available: {list(self._personas.keys())}"
            )
        self._active_persona_name = name
        return self.active_persona

    def register_persona(self, profile: PersonaProfile) -> None:
        self._personas[profile.name.lower()] = profile

    def list_personas(self) -> list[PersonaProfile]:
        return list(self._personas.values())
