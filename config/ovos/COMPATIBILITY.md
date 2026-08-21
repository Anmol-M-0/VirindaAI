# OVOS configuration profiles

`config/ovos/` contains the **production stable profile**. It matches the legacy Persona/OpenAI solver API used by
OpenVoiceOS's current stable constraints.

`config/ovos/experimental-agent/` contains the newer Persona agent configuration (`ovos-chat-openai-plugin`). It is
kept separate because the current development OpenAI plugin requires newer Persona and plugin-manager versions than
the stable constraints provide.

Do not merge the two profiles.
