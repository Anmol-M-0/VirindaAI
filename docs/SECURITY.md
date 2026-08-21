# Security and Privacy

MarinaAI is local-first, not privacy-magical. Data remains on the local machine by default, but optional hosted providers necessarily receive the messages sent to them.

## Defaults

- The default provider is the offline echo provider.
- SQLite is stored in the user data directory or `MARINA_DATA_DIR`.
- Raw microphone audio is not persisted by the runtime.
- API keys are read from environment variables and are never written into the SQLite database.

## Operational guidance

Keep `MARINA_DATA_DIR` on a trusted local filesystem. Restrict the directory to the user account. Do not put secrets in `.env` files committed to the repository.

The systemd unit uses `NoNewPrivileges=true` as a baseline; production deployments should additionally review filesystem/network restrictions for the chosen audio and desktop integration.
