# COLAB-MCP-ADAPTER — Decisions & Recommendations Log

> **Purpose:** Persistent record of architectural decisions, recommendations, and dispositions.
> **Location:** `colab-mcp-adapter/DECISIONS.md` (version-controlled)
> **Updated:** 2026-10-31

---

## Decision Log

| ID | Date | Decision | Status | Authority |
|----|------|----------|--------|-----------|
| DEC-001 | 2026-10-30 | Adopt local Colab CLI wrapper architecture (no GCP/ADC) | ✅ Accepted | Explicit authorization |
| DEC-002 | 2026-10-30 | Implement 8 MCP tools across 4 phases (C-F) | ✅ Accepted | Explicit authorization |
| DEC-003 | 2026-10-30 | Freeze Colab MCP at v0.1.0-RC (2 commits) | ✅ Accepted | Explicit authorization (COLAB-BASELINE-ACCEPTANCE-001) |
| DEC-004 | 2026-10-30 | Global OpenCode config for `colab-researcher` agent | ✅ Implemented | Explicit authorization |
| DEC-005 | 2026-10-30 | Agent permissions: 6 Allow / 2 Ask (Ask for file exec + session stop) | ✅ Implemented | Explicit authorization |
| DEC-006 | 2026-10-31 | Create annotated release tag `v0.1.0` on commit `a846a28` | ✅ Implemented | Explicit authorization (WO-2026-10-31-001) |
| DEC-007 | 2026-10-31 | Author GitHub Actions CI workflow for Python 3.11/3.12/3.13 | ✅ Implemented | Explicit authorization (WO-2026-10-31-001) |
| DEC-008 | 2026-10-31 | Publish `v0.1.0` to GitHub `suniltnngl-gm/colab-mcp-adapter`; fast-forward `main` to `eba0cf0` and move the annotated tag | ✅ Implemented | Explicit authorization |

---

## Recommendation Log

| ID | Date | Recommendation | Status | Source |
|----|------|----------------|--------|--------|
| REC-001 | 2026-10-30 | Create `colab-researcher` agent with 6 Allow / 2 Ask permissions | ✅ Implemented | Operator recommendation |
| REC-002 | 2026-10-30 | Freeze Colab adapter at v0.1.0-RC; defer tag/push | ✅ Accepted | Operator recommendation |
| REC-003 | 2026-10-30 | Conduct OpenCode ecosystem inventory (read-only) | ✅ Complete | Operator authorization |
| REC-004 | 2026-10-30 | Investigate compute federation (COMPUTE-FEDERATION-RESEARCH-001) | ✅ Complete | Operator authorization |
| REC-005 | 2026-10-30 | Design federation architecture (COMPUTE-FEDERATION-DESIGN-001) | ✅ Complete | Operator authorization |
| REC-006 | 2026-10-31 | Implement Kaggle compute adapter with policy/quota gates | ✅ Complete | Operator authorization |

---

## Disposition Log

| ID | Date | Disposition | Workstream | Authority |
|----|------|-------------|------------|-----------|
| DISP-001 | 2026-10-30 | Colab MCP v0.1.0 baseline accepted as RC | Colab MCP | Explicit |
| DISP-002 | 2026-10-30 | Colab MCP frozen; tag/push deferred | Colab MCP | Explicit |
| DISP-003 | 2026-10-30 | Compute Federation Research complete (read-only) | Compute Federation | Explicit |
| DISP-004 | 2026-10-30 | Compute Federation Design complete (read-only) | Compute Federation | Explicit |
| DISP-005 | 2026-10-31 | OpenCode ecosystem inventory complete (read-only) | OpenCode Ecosystem | Explicit |
| DISP-006 | 2026-10-31 | Colab MCP release tag `v0.1.0` created and verified | Colab MCP | Explicit |
| DISP-007 | 2026-10-31 | opencode-os provider registry & Kaggle adapter committed | Compute Federation | Explicit |
| DISP-008 | 2026-10-31 | Colab MCP v0.1.0 published to `origin`; CI green on `main` (41219602179) and `v0.1.0` (41219616365) | Colab MCP | Explicit |

---

## OpenCode Agent Configuration

| Agent | Permissions | Model | Status |
|-------|-------------|-------|--------|
| `colab-researcher` | 6 Allow / 2 Ask | `opencode` | Active (validated in v2) |

### Permission Details

| Permission | Tool | Effect |
|------------|------|--------|
| Allow | `colab_colab_session_list` | Read-only |
| Allow | `colab_colab_session_get` | Read-only |
| Allow | `colab_colab_session_get_url` | Read-only |
| Allow | `colab_colab_session_log` | Read-only |
| Allow | `colab_colab_session_create` | Creates session |
| Allow | `colab_colab_code_execute` | Executes code |
| Ask | `colab_colab_file_execute` | Requires approval |
| Ask | `colab_colab_session_stop` | Destructive - requires approval |

---

## Workstream Status

| Workstream | Status | Authorization |
|------------|--------|---------------|
| Colab MCP Adapter v0.1.0 Release | ✅ Tagged `v0.1.0` | Authorized |
| CI/CD Workflow (`.github/workflows/ci.yml`) | ✅ Implemented | Authorized |
| Remote Publication | ✅ Published to `origin` (GitHub) | Authorized |
| `colab-researcher` Agent | ✅ Validated in v2 runtime | Authorized |
| OpenCode Ecosystem Inventory | ✅ Complete (read-only) | Authorized |
| Compute Federation Implementation (Kaggle) | ✅ Complete in `opencode-os` | Authorized |
| `opencode-os` Cleanup & Commit | ✅ Committed (`7ba82f9`) | Authorized |

---

## Key Boundaries

| Boundary | Status |
|----------|--------|
| Colab adapter v0.1.0 released from `eba0cf0` (annotated tag moved from baseline `a846a28`) | ✅ Enforced |
| No unconfirmed remote push without destination URL | ✅ Enforced |
| Colab Free strictly excluded from federation worker pool | ✅ Enforced |
| Compute jobs default to dry-run/simulation without approval | ✅ Enforced |
| WFH gate respected across all repositories | ✅ Enforced |

---

## Open Blockers & Clarifications

| Item | Status | Action Required |
|------|--------|-----------------|
| Colab MCP Git Remote URL | ✅ Resolved | `origin` = https://github.com/suniltnngl-gm/colab-mcp-adapter.git; `main` + `v0.1.0` pushed |
| Push `opencode-os` to origin | ⏳ Ready | Moved into `D:\`; 1 commit ahead of origin/master; awaiting push command |
