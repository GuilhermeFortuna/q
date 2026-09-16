# Q — Quantitative Trading & Research Platform

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/PLATFORM-LINUX%20(FEDORA%20%C2%B7%20WAYLAND%20%C2%B7%20NVIDIA)-090d16?style=for-the-badge&logo=linux&logoColor=white&labelColor=05070a">
    <img alt="Platform" src="https://img.shields.io/badge/PLATFORM-LINUX%20(FEDORA%20%C2%B7%20WAYLAND%20%C2%B7%20NVIDIA)-090d16?style=for-the-badge&logo=linux&logoColor=white&labelColor=05070a">
  </picture>
</p>

<p align="center">
  <a href="https://github.com/users/GuilhermeFortuna/projects/2"><img src="https://img.shields.io/badge/PROJECT%20BOARD-ACTIVE-0052cc?style=for-the-badge&logo=github&logoColor=white" alt="Project Board"></a>
  <a href="https://github.com/GuilhermeFortuna/q_contracts"><img src="https://img.shields.io/badge/SCHEMAS-q__contracts-blueviolet?style=for-the-badge&logo=json" alt="Contracts"></a>
  <a href="https://github.com/GuilhermeFortuna/q_backend"><img src="https://img.shields.io/badge/CORE%20ENGINE-RUST%20%2B%20PYTHON-orange?style=for-the-badge&logo=rust" alt="Core Engine"></a>
  <a href="https://github.com/GuilhermeFortuna/q_frontend"><img src="https://img.shields.io/badge/UI-TAURI%20%2B%20QT%206-38bdf8?style=for-the-badge&logo=tauri" alt="UI Stack"></a>
  <a href="#execution-guarantees"><img src="https://img.shields.io/badge/SAFETY-FAIL--CLOSED-emerald?style=for-the-badge&logo=shield" alt="Safety"></a>
</p>

---

## 🏛 Executive Overview

**Q** is an institutional-grade, multi-repository quantitative trading, strategy research, backtesting, and automated execution platform engineered for **Linux (Fedora · Wayland · NVIDIA)**.

Engineered around strict mathematical causality, deterministic execution, and ultra-low-latency local visualization, Q bridges high-level financial research with zero-copy binary streaming and fail-closed broker execution.

### Core Capabilities

- **High-Throughput Research Engine:** 50k+ lines of vector-accelerated strategy formulation, composable exit rules, walk-forward analysis, genetic strategy search (DAG Genomes), Optuna hyperparameter optimization, and neural feature intelligence.
- **Unified Deterministic Semantics:** Shared computational primitives for indicator math, tick/bar kernels, and fill models implemented in **Rust (`q_core`)** and bound via PyO3 and `cxx-qt`, enforcing zero divergence between backtests and live execution.
- **Fail-Closed Execution Plane:** Order intent state is atomically persisted to a PostgreSQL ledger prior to submission, enforcing at-most-once execution, strict lease-based worker heartbeats, and instantaneous kill-switch intervention.
- **Contract-Isolated Broker Edge:** Dedicated Wine-isolated micro-proxies communicate with MetaTrader 5 over versioned loopback wire contracts, keeping the native Linux environment completely decoupled from proprietary Windows binaries.
- **Columnar & Binary Streaming:** End-to-end Apache Arrow IPC and Redis Streams replace JSON polling for market tick/bar fanout, streaming updates directly into GPU scene-graph buffers at 60+ FPS.

---

## 📐 System Architecture: The Three Planes

Q enforces a strict separation of concerns across three distinct operational planes:

```
┌──────────────────────────────── Linux Workstation ────────────────────────────────┐
│                                                                                    │
│  EXECUTION PLANE                 RESEARCH / CONTROL PLANE        PRESENTATION      │
│                                                                                    │
│  ┌───────── Wine Prefix ──────┐  ┌──────────────────────────┐  ┌───────────────┐   │
│  │ MT5 Terminal (B3 / Futures)│  │ q_backend API (FastAPI)  │  │ q_terminal    │   │
│  │ mt5 data gateway (stdlib)  │  │  · REST Control API      │◄─┤  Qt 6 / QML   │   │
│  │ mt5 execution edge (stdlib)│  │  · Arrow WebSocket Stream│  │  q_core (Rust)│   │
│  │ [Tier B: MQL5 EA]          │  │ Dramatiq Worker Pool     │  │  Live Trading │   │
│  └──────────┬─────────────────┘  │ Redis Streams (Fan-Out)  │  │  + Operations │   │
│             │ Loopback wire      │ PostgreSQL (Ledger,      │  └───────────────┘   │
│             │ contracts from     │   Outbox, Run Storage)   │  ┌───────────────┐   │
│             │ q_contracts        │ Parquet Lake + DuckDB    │  │ q_frontend    │   │
│  ┌──────────▼─────────────────┐  └─────────▲────────────────┘  │  Tauri 2      │◄──┤
│  │ Execution Worker (Python)  │            │                   │  React 19     │   │
│  │  Orchestration, Ledger,    ├─────Outbox─┘                   │  Research UI  │   │
│  │  Leases, Reconciliation    │                                └───────────────┘   │
│  │  q_core for Evaluation     │                                                    │
│  └────────────────────────────┘                                                    │
│                                                                                    │
│  q_core (Rust) is compiled into: PyO3 wheel (q_backend / worker) · cxx-qt (q_terminal)│
└────────────────────────────────────────────────────────────────────────────────────┘
```

### 1. Execution Plane
- **Isolation:** MetaTrader 5 runs inside a dedicated Wine prefix. Only standard-library Python scripts run inside Wine, exposing minimal, versioned HTTP loopback endpoints (`/v1/health`, `quote`, `check`, `submit`, `lookup`, `positions`, `deals`).
- **Safety First:** The Linux execution worker orchestrates orders with intent-before-submission durability, lease management, and deal reconciliation against the PostgreSQL ledger.
- **Latency Tiers:**
  - **Tier A (Closed-bar, M15+):** Seconds decision loop. Orchestrated by Python worker, evaluated deterministically in `q_core`.
  - **Tier B (Intrabar tick-reactive, 10–50 ms):** Pre-authorized local risk limits executed directly in an MQL5 Expert Advisor with Linux supervisory heartbeat and kill switch.

### 2. Research & Control Plane
- **`q_backend` (FastAPI):** Exposes transactional REST endpoints and high-speed Arrow WebSocket streaming.
- **Job Orchestration:** Dramatiq distributed worker pool backed by Redis executes CPU-heavy backtests, Optuna sweeps, and walk-forward runs.
- **Storage Tier:** Parquet data lake managed by an immutable dataset catalog, queried via DuckDB.
- **Transactional Outbox & Relay:** Every state change commits atomically to PostgreSQL with an outbox row, relayed monotonically into Redis Streams (`XADD`).

### 3. Presentation Plane (Semantic UI Boundary)
Q intentionally partitions user interfaces by **semantic responsibility**, not by data volume:
- **`q_frontend` (Research UI):** Tauri 2 + React 19 + TypeScript + Tailwind CSS v4. Hosts strategy authoring, backtesting analysis, Optuna Pareto frontiers, walk-forward validation, feature discovery, and dataset exploration. Large research datasets render on WebGL2 canvases.
- **`q_terminal` (Operations UI):** Native Qt 6 / QML application integrated with `q_core` via `cxx-qt`. Displays live quotes, forming bars, open positions, active deployments, order audits, and execution kill-switches with zero-copy GPU scene-graph rendering.

---

## 📦 Multi-Repository Topology

The Q platform is organized into five specialized repositories. **Dependencies flow strictly downward:**

```
q_contracts ────────────► q_core ────────────► q_backend ────────────► q_frontend
(Schemas & Types)         (Rust Engine)       (Python Control)        (Research UI)
                             │
                             └───────────────► q_terminal
                                               (Operations UI)
```

| Repository | Tech Stack | Responsibility | Key Deliverables |
| :--- | :--- | :--- | :--- |
| [**`q_contracts`**](https://github.com/GuilhermeFortuna/q_contracts) | JSON Schema, Arrow, YAML | Single source of truth for all cross-process protocols, wire formats, manifests, and stream topics. | Generated Python, TypeScript, and Rust type definitions; `COMPAT.md`. |
| [**`q_core`**](https://github.com/GuilhermeFortuna/q_core) *(Q-007)* | Rust, PyO3, cxx-qt, Arrow-rs | Deterministic computation: technical indicators, candle/tick backtesting kernels, fill models, exit rules, columnar ring buffers. | Python wheel (`q-py`), native library for `q_terminal`, parity test suites. |
| [**`q_backend`**](https://github.com/GuilhermeFortuna/q_backend) | Python 3.12+, FastAPI, Redis, Postgres, DuckDB | Control API, research orchestration, Dramatiq worker pool, outbox relay, dataset catalog, Wine MT5 gateway/edge scripts. | API container, systemd user services, transactional ledger. |
| [**`q_frontend`**](https://github.com/GuilhermeFortuna/q_frontend) | Tauri 2, React 19, Vite 6, Tailwind v4 | Research workbench: strategy studio, multi-objective optimization, feature intelligence, PDF report generator. | Native desktop bundle (Linux `.AppImage` / `.deb`). |
| [**`q_terminal`**](https://github.com/GuilhermeFortuna/q_terminal) *(Q-008)* | Qt 6, QML, Rust, C++ | Live trading terminal: real-time streaming charts, deployment manager, risk monitors, emergency flatten controls. | High-performance Wayland desktop application. |

---

## 🛡️ Core Engineering Invariants

1. **One Implementation of Shared Semantics:** Backtests and live trading MUST produce identical numerical outputs. All indicator formulas, signal math, exit rules, and fill logic exist once in `q_core` (Rust).
2. **Schema-Governed Inter-Process Communication:** No ad-hoc JSON payloads. Every message, stream frame, lake manifest, and gateway payload is strictly defined in `q_contracts`.
3. **Strict Wine Boundary:** No Linux process may link or import `MetaTrader5`. MT5 is strictly isolated inside Wine behind standard-library edge micro-services.
4. **Fail-Closed Execution & Single-Submission Intent:** Every order is identified by an immutable UUID intent recorded in PostgreSQL prior to dispatch. If a broker timeout or unknown state occurs, the intent is locked and resolved via inspection—**never automatically resent**.
5. **Columnar, Zero-Copy Stream Processing:** High-rate market data travels in Apache Arrow IPC batches or aligned memory buffers directly to rendering shaders, bypassing per-row object allocations.
6. **Immutable, Catalog-Addressed Data Lake:** Datasets are immutable once published. Consumers access files exclusively via cryptographic checksum manifests obtained through the dataset catalog.
7. **No UI Process Controls Backend Lifecycle:** All services run as systemd user units (`q-api.service`, `q-outbox-relay.service`, `mt5-edge.service`, etc.). UIs connect to services, never spawn them.

---

## 🔄 Multi-Repository Pinning & Coordination

To keep multi-repo development seamless without heavy registry ceremony:

- **Vendored Code:** Consumer repos (`q_backend`, `q_frontend`, `q_terminal`) vendor generated schemas into a local `contracts/` directory.
- **Commit Pinning:** The authoritative pin is recorded in `CONTRACTS_REV` inside each consumer repo.
- **Verification:** Consumer CI validates that vendored files match clean code generation at the pinned commit:
  ```bash
  make contracts-check
  ```
- **Global Compatibility Matrix:** [`q_contracts/COMPAT.md`](https://github.com/GuilhermeFortuna/q_contracts/blob/main/COMPAT.md) logs the verified, tested commit pins across all repositories.

---

## 🚦 Roadmap & Board Milestones

Project delivery is tracked in the **[Q GitHub Project Board](https://github.com/users/GuilhermeFortuna/projects/2)**.

### Board Status Workflow

| Status | Definition |
| :--- | :--- |
| **`Blocked`** | Prerequisites incomplete, or technical specification/plan pending review. |
| **`Todo`** | Prerequisite satisfied, implementation plan approved, ready to build. |
| **`In Progress`** | Actively under active development. |
| **`In Review`** | Implementation committed on a local task branch, checks run, awaiting human review and merge. |
| **`Done`** | Automated tests passing, cross-repo verification clean, acceptance documented. |

### Working with AI agents

Agents are launched from the workspace root with `./work` (requires `uv` and an authenticated `gh`):

```bash
./work start Q-010 --agent claude              # Todo → In Progress, branch Q-010-…, launch Claude Code
./work start Q-010 --agent codex --effort high --worktree
./work start Q-010 --agent cursor --model sonnet-5 --effort high
./work start Q-010 --agent antigravity --dry-run  # print the prompt, change nothing
./work board show Q-010
./work finish Q-010 [--push]                    # In Review → merge --no-ff into development → Done
./work finish Q-029                             # in q_core, also bumps, checks, tags and pushes the release
```

Agents finish by running `./work board set <ID> in-review -m "…"` (or `blocked`). Task branches
stay local and are kept after `finish`. Workspace rules for agents live in [`AGENTS.md`](AGENTS.md).
Full command reference: [`docs/work-cli.md`](docs/work-cli.md).
If `./work finish` fails after merging (for example the push is rejected or removing the
worktree fails), the task stays `In Review`; re-running `./work finish <ID>` is safe. Codex's
default sandbox will prompt for approval when the agent runs `./work board set`, since it
needs network access for `gh` and writes to `uv`'s cache outside the workspace.

### Architectural Roadmap

- [x] **Batch 01 — New Repository Foundations:** Bootstrap `q_contracts` (control API, stream envelope, Wine edge contracts, lake manifests, code generators) *(Q-001 → Q-006)*; scaffold the Rust `q_core` workspace *(Q-007)*; scaffold the Qt/QML `q_terminal` application *(Q-008)*.
- [ ] **Batch 02 — Streaming Transport:** Stream payload and replay contracts, PostgreSQL transactional outbox, outbox relay and Redis Streams, job events and live market data on the stream, Arrow WebSocket endpoint, snapshot/history endpoints, and `q_frontend` job progress over the stream. *(Q-009 → Q-016)*
- [ ] **Batch 03 — Service Lifecycle & Data Catalog:** Dataset catalog over the existing lake, systemd user units with readiness, and the Tauri shell no longer owning backend processes. *(Q-017 → Q-019)*
- [ ] **Later — Terminal Slice:** End-to-end streaming vertical slice: live tick/bar stream → `q_terminal` GPU scene graph, plus a catalog-driven historical load.
- [ ] **Later — Automated Live Execution:** Wine execution edge, intent idempotency engine, fail-closed reconciliation, and operational trading surfaces in `q_terminal`.

---

## ⚡ Quick Start for Developers

Clone the meta-workspace and initialize sibling repositories:

```bash
# Clone the core repositories into the workspace
git clone https://github.com/GuilhermeFortuna/q_contracts.git
git clone https://github.com/GuilhermeFortuna/q_backend.git
git clone https://github.com/GuilhermeFortuna/q_frontend.git
```

### Research / Backtests (one command)

From the workspace root, with Docker running and NVIDIA Container Toolkit installed:

```bash
./research              # warm start: reuse q-backend:dev when fingerprint matches
./research --rebuild    # force one image rebuild
```

This builds (or reuses) the shared `q-backend:dev` image, fail-closed CUDA-probes the
worker GPU, brings up containerized Postgres, Redis, API, and Dramatiq worker, points
the Research UI at the live API (`VITE_ENABLE_MSW=false`), and launches `pnpm tauri:dev`.
**Ctrl+C** stops the UI and runs `docker compose … down` without deleting volumes,
images, build cache, or host environments.

Image-defining inputs (any change triggers a rebuild): `Dockerfile`, `pyproject.toml`,
`uv.lock`, `docker/entrypoint.sh`, and `docker/metatrader5-stub/**`. Application source,
contracts, and Alembic trees are bind-mounted and do not require a rebuild.

CUDA prerequisites (vendor install guide — do not auto-install privileged packages):
https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html

Verify before first GPU Research launch:

```bash
nvidia-smi
nvidia-ctk --version
docker run --rm --gpus all q-backend:dev python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

Run only one neural-training job at a time on a single consumer GPU. Native CPU-only
backend work remains available outside `./research` (`Q_TORCH_DEVICE` defaults to `cpu`).

Host market/lake data is bind-mounted from `q_backend/data/` into the containers.

### Manual (native) backend

```bash
# Verify contracts suite
cd q_contracts && make check

# Start the backend services (API + Dramatiq worker)
cd ../q_backend
uv sync
uv run uvicorn q_backend.api.main:app --reload --port 8000
# in another terminal: uv run worker

# Launch the research desktop frontend
cd ../q_frontend
pnpm install
pnpm tauri:dev
```

---

<p align="center">
  <sub>Engineered with precision for quantitative finance and automated market operations.</sub>
</p>
