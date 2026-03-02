# 🌌 Pygnosis

> **A coherence-driven, correlation-graph-based Minecraft server engine with robotics integration**

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=flat-square&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)
[![Protocol](https://img.shields.io/badge/Minecraft-1.14.x-orange?style=flat-square)](https://wiki.vg/Protocol)
[![Status](https://img.shields.io/badge/Status-Experimental-purple?style=flat-square)]()

Pygnosis is an experimental, research-grade Minecraft server written entirely in Python. Rather than treating the game world as a static grid of blocks, it models every object — blocks, entities, players, robots, packets — as a **correlation operator** in a dynamic sparse graph. Simulation priority is allocated by a **coherence scheduler** that concentrates CPU and memory where they matter most, and nearly nothing where they don't.

The project also bridges the virtual world to physical hardware (Arduino, ESP32, Raspberry Pi) through a JSON-configured GPIO microservice, enabling real-world automation from inside Minecraft.

---

## ✨ Feature Highlights

- **Correlation Graph Engine** — every game object is a graph node with a coherence value; edges propagate state updates
- **Coherence-Driven Scheduler** — operators below threshold are compressed to a boundary store; above threshold they run in full continuum
- **Boundary / Continuum Duality** — inactive chunks are zlib-compressed in-memory; loaded chunks expand into NumPy-backed block matrices
- **Full Minecraft 1.14 Protocol** — handshake, login, status ping, keep-alive, chat, player position, join-game
- **Ring Buffer Networking** — lock-free ring buffers for zero-copy I/O; VarInt encoding; per-connection async write queues
- **Autopoietic Parameter Tuning** — network parameters (timeouts, buffer sizes) self-adjust via a feedback loop using the golden ratio φ ≈ 1.618
- **Paradox Detection** — server-client state checksums; divergence above threshold triggers full state reconciliation
- **Robotics Plugin** — robots as composite correlation operators; sensor/actuator bridge to a GPIO microservice
- **HTTP Admin Dashboard** — live operator listing, coherence stats, robot actuator control via aiohttp
- **MERS Visual Attributes** — per-operator metalness, emissive, roughness, subsurface values update lazily from coherence
- **LOD Networking** — entity update detail level is a function of coherence and distance
- **ComputerCraft Extension (Pygnosis:CC)** — in-game Lua/Python scripting with quantum superposition, temporal recursion, fractal execution, and self-modifying autopoietic code (design doc included)

---

## 📦 Package Structure

```
pygnosis/
├── core.py        # CorrelationOperator, Graph, Scheduler, PhysicsEngine
├── world.py       # Chunk, Block palette, Inventory, Player, Item entities
├── robotics.py    # Robot operator, SimulatedGPIO, RoboticsPlugin
├── network.py     # RingBuffer, VarInt, PacketOperator, ClientConnection, NetworkManager
├── protocol.py    # Protocol_1_14 — handshake / login / play / status handlers
├── admin.py       # aiohttp HTTP admin server & dashboard
└── main.py        # Entry point with argparse (--debug flag)
```

Design documents for additional subsystems live in `docs/`:
- `Physics_Engine.md` — plugin architecture, JIT kernels, multiprocessing federation
- `block-character-inventory_Management.md` — block update propagation, entity AI, inventory ops
- `Robotics-Framework.md` — JSON config schemas, GPIO microservice, hardware drivers
- `TCPIP-IPX_Enhanced_Protocol_Networking_Framework.md` — packet-as-operator, semantic grammar, LOD networking
- `Pygnosis_CC___Correlation_ComputerCraft_Framework.md` — in-game scripting environment
- `Foundational_Math.md` / `Graphical_Mods.md` — underlying theoretical frameworks

---

## 🚀 Quick Start

### Requirements

```
Python 3.11+
aiohttp
```

Optional for performance:
```
numba       # JIT-compiled physics kernels
numpy       # block matrix storage
zstandard   # chunk compression (falls back to zlib)
```

### Install & Run

```bash
git clone https://github.com/TaoishTechy/pygnosis
cd pygnosis
pip install aiohttp
python main.py
```

With debug output:
```bash
python main.py --debug
```

The server starts three services:
| Service | Address | Purpose |
|---------|---------|---------|
| Minecraft protocol | `0.0.0.0:25565` | Vanilla client connections (1.14.x) |
| HTTP admin | `http://localhost:8081` | Operator dashboard, robot control |
| Physics engine | internal | 20 TPS coherence-driven simulation loop |

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                   main.py                        │
│   PhysicsEngine ─ AdminServer ─ RoboticsPlugin  │
│              └──── NetworkManager               │
└────────┬────────────────────────────────────────┘
         │
┌────────▼────────────────────────────────────────┐
│              core.py                            │
│  CorrelationOperator                            │
│    ├─ coherence (float 0–1)                     │
│    ├─ edges (Set[str])                          │
│    └─ MERS visual attrs (lazy)                  │
│  CorrelationGraphManager (priority heap)        │
│  CoherenceScheduler (decay + propagate)         │
│  PhysicsEngine (asyncio 20 TPS loop)            │
└────────┬──────────────┬──────────────┬──────────┘
         │              │              │
   world.py       network.py     robotics.py
  Chunk/Block   RingBuffer       Robot
  Inventory     PacketOperator   SimulatedGPIO
  Player/Item   NetworkManager   RoboticsPlugin
                protocol.py
               Protocol_1_14
```

### Coherence Lifecycle

```
New operator → CI = initial value
     │
     ▼
CI > 0.3 → ACTIVE (simulated every tick, graph propagation)
     │
     ▼ (decay -0.012/tick, no player proximity)
CI < 0.3 → BOUNDARY (compressed, minimal memory footprint)
     │
     ▼ (player approaches / event triggered)
     └──→ ACTIVE again (inflate from boundary store)
```

---

## ⚙️ Configuration

Network behaviour is controlled by `network_config.json` (auto-generated with defaults if absent):

```json
{
  "protocols": ["1.14"],
  "ring_buffer_size": 16536,
  "coherence": {
    "update_interval": 0.05,
    "lod_levels": [
      {"max_distance": 10,  "detail": "full"},
      {"max_distance": 50,  "detail": "compressed"},
      {"max_distance": 200, "detail": "boundary"}
    ]
  },
  "autopoietic": {
    "enabled": true,
    "tune_interval": 5.0,
    "golden_ratio": 1.618
  },
  "paradox": {
    "threshold": 1.5,
    "checksum_interval": 1.0
  }
}
```

Robotics hardware is configured via JSON files in `config/robotics/`:
- `robots.json` — robot body, sensors, actuators, controller class
- `mappings.json` — game events → hardware commands
- `automations.json` — threshold rules (e.g., temperature > 30 → broadcast warning)
- `hardware_profiles.json` — serial/HTTP/MQTT device definitions

---

## 🤖 Robotics Integration

Robots are first-class correlation operators. The `RoboticsPlugin` polls a `GPIOClient` (real HTTP, or the included `SimulatedGPIO` for testing) every tick:

```python
robotics.spawn_robot("greenhouse")
# Robot monitors temperature, activates fan relay above 28°C
```

The GPIO Microservice supports three driver types out of the box:

| Driver | Protocol | Typical Hardware |
|--------|----------|-----------------|
| Serial | USB/UART | Arduino, Micro:bit |
| HTTP   | REST     | ESP8266/32 |
| MQTT   | pub/sub  | distributed sensor networks |

Physical ↔ virtual synchronisation is bidirectional: real-world sensor readings update the robot operator's coherence and MERS visual attributes; in-game lever triggers send HTTP commands to actuators.

---

## 🌐 Protocol Support

| Version | Protocol Numbers | Status |
|---------|-----------------|--------|
| 1.14 – 1.14.4 | 477 – 498 | ✅ Implemented |
| 1.15 – 1.20   | —         | 🔲 Planned (handler stubs ready) |

The `NetworkManager` accepts raw TCP connections, buffers data in per-client `RingBuffer` instances, decodes VarInt-prefixed packets, and dispatches to versioned `ProtocolHandler` subclasses. Unsupported protocol versions receive a graceful disconnect with an explanatory message.

---

## 🔬 Design Philosophy

Pygnosis treats game-state management as a problem in **sparse information dynamics** rather than brute-force tick processing. The key insight is that most of a Minecraft world is idle at any given moment. Rather than simulating every block and entity every tick, the coherence graph ensures:

1. **Only active regions consume CPU** — coherence decay naturally quiesces untouched areas.
2. **Memory scales with activity** — boundary-stored chunks occupy kilobytes; continuum chunks expand only when needed.
3. **Updates propagate locally** — block changes excite neighbours through commutator evaluation, not a global scan.
4. **Network mirrors simulation priority** — LOD levels for entity updates follow coherence, so high-importance entities get more bandwidth.

This enables theoretical support for far larger worlds and more connected clients than a conventional uniform-tick server at equivalent hardware cost.

---

## 🗺️ Roadmap

- [ ] 1.15 – 1.20 protocol handlers
- [ ] Full chunk packet encoding (Chunk Data 0x22)
- [ ] NumPy block matrix integration (replace `dict` block storage)
- [ ] Numba JIT kernels for light propagation and fluid simulation
- [ ] Pygnosis:CC — in-game Lua/Python scripting (ComputerCraft-style)
- [ ] Multiprocessing federation for disjoint chunk regions
- [ ] Web dashboard with live coherence graph visualisation
- [ ] Real GPIO microservice (production-grade, separate process)
- [ ] MQTT driver for distributed sensor networks
- [ ] Plugin API (load custom `.py` physics plugins from `/physics/configs/`)

---

## 🤝 Contributing

Contributions welcome. Please open an issue before large PRs.

Areas of particular interest:
- Protocol completeness (chunk encoding, entity metadata)
- Performance benchmarking under load
- Numba kernel implementations for physics
- Hardware driver implementations
- Test coverage for the coherence scheduler

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

*All configurations and code should be used ethically, in service of creativity, learning, and exploration.*
