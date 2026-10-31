# Integration Change Ledger (append‑only)

Each row records a change that impacts an integration point. Existing identifiers from the master ledger are preserved.

| Ledger ID | Integration ID | Change Type | Commit SHA | Author | Timestamp | Backup Evidence |
|-----------|----------------|------------|------------|--------|-----------|-----------------|
| **LC‑1** | MCP‑COLAB | modify (lint‑fix) | e3f8c9d2a5b7c1d9e6f4a2b3c8d9e1f2a4b5c6d7 | suniltnngl‑gm | 2026‑10‑31T13:02:45+05:30 | ci.yml SHA256: 026A6AA029010C7DD9CD8AEBFB02D15FA5A9DF47AF0C89D3CD7A9CF6467B2F54; pyproject.toml SHA256: 2E8F5927AEC996209A8EBE136C851EB74A1F0FB1B41203298FD5875D7D67EC5A |
| **LC‑2** | PLUGIN‑GCAL | none (no remote) | – | – | – | – |
| **LC‑3** | PLUGIN‑GDOCS | none (no remote) | – | – | – | – |
| **LC‑4** | PLUGIN‑GDRIVE | none (no remote) | – | – | – | – |
| **LC‑5** | AGENT‑RESEARCHER | none (config only) | – | – | – | – |
| **LC‑6** | PROVIDER‑KAGGLE | none (local only) | – | – | – | – |

*The ledger is append‑only; new changes must be added as additional rows.*