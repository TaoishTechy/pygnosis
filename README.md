# Pygnosis

[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Pygnosis** is an experimental Minecraft server written in Python, featuring a unique *coherence-based physics engine* and a real‑time web dashboard. It supports Minecraft **1.8.9** (protocol 47) and **1.12.2** (protocol 340), and demonstrates how a correlation‑driven model can influence rendering properties (MERS) and entity behaviour.

> ⚠️ **This is a proof‑of‑concept / research project.**  
> It is not intended for production use and lacks many standard server features.

---

## ✨ Features

- ✅ **Dual‑protocol support** – Handles both 1.8.9 and 1.12.2 clients.
- 🧠 **Coherence Engine** – Every entity (player, chunk, item, robot) has a *coherence* value that affects its visual properties (metalness, emissive, roughness, subsurface). Coherence propagates through a graph and is globally conserved.
- 🌐 **Live Admin Dashboard** – Built with `aiohttp`, Chart.js, and Three.js. Monitor operators, inspect MERS values, compress chunks, and spawn robots – all from your browser.
- 🤖 **Robotics Plugin** – Simulated GPIO with temperature sensors and a fan actuator. The robot’s behaviour (fan on/off) influences its coherence and visual appearance.
- 🗺️ **Boundary Store** – Chunks can be compressed to a lightweight boundary representation to save memory, and inflated when needed.
- 📦 **Minimal dependencies** – Only requires `aiohttp` for the web server and dashboard.

---

## 📋 Requirements

- Python **3.7+**
- [aiohttp](https://docs.aiohttp.org/) (install via `pip`)
- A Minecraft client (1.8.9 or 1.12.2) for testing

---

## 🔧 Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/TaoishTechy/pygnosis.git
   cd pygnosis
   ```

2. (Optional) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. Install the required package:
   ```bash
   pip install aiohttp
   ```

That’s it! Pygnosis uses only the standard library plus `aiohttp`.

---

## 🚀 Usage

Start the server with:

```bash
python src/main.py
```

To enable verbose debug output (shows coherence changes, packet details):

```bash
python src/main.py --debug
```

Once running:

- **Minecraft clients** can connect to `localhost:25565` (or your server’s IP).
- Open the **admin dashboard** at [http://localhost:8081](http://localhost:8081).

The server will automatically detect the client’s protocol version and use the correct packet format.

---

## ⚙️ Configuration

The file `network_config.json` in the `src/` directory controls network behaviour:

```json
{
  "protocols": ["1.8", "1.12.2"],
  "default_protocol": "1.8",
  "read_timeout": 30.0,
  "ring_buffer_size": 16384,
  "autopoietic": {
    "enabled": false,
    "tune_interval": 30,
    "golden_ratio": 1.618
  },
  "paradox": {
    "threshold": 1.5,
    "checksum_interval": 1.0
  }
}
```

- `read_timeout` – seconds before a client is considered dead.
- `autopoietic` / `paradox` – reserved for future coherence‑based experiments.

---

## 🌐 Admin Dashboard

The dashboard provides real‑time insight into the coherence graph.

### Endpoints

- `/` – Interactive HTML dashboard.
- `/api/status` – Server tick rate, operator count, global coherence, etc.
- `/api/operators` – List all operators with their current MERS and LOD bias.
- `/api/operator/<id>` – Detailed view of a single operator.
- `/api/edges` – Graph edges between operators.
- `/api/entities` – Players, items, and robots with their positions/inventories.
- `/api/history` – Time‑series of global coherence (for Chart.js).
- `/api/control/<action>` – POST actions like `compress_chunk` or `spawn_robot`.
- `/ws` – WebSocket endpoint for live updates (basic placeholder).

### Dashboard Controls

- **Compress Chunk (0,0)** – Moves the chunk at (0,0) to the boundary store, freeing memory.
- **Spawn Robot** – Creates a new robot with a random ID; its temperature sensor and fan can be observed.

---

## 🧠 How It Works

### Correlation Operators

Every object in the world (players, chunks, items, robots) is a `CorrelationOperator`. Each operator has:

- `coherence` – a float between 0 and 1, representing its “importance” or “activity”.
- `_mers` – Metalness, Emissive, Roughness, Subsurface – visual properties that are automatically updated based on coherence.
- `_animation_params` – Speed, amplitude, phase for shader‑based animations.
- `edges` – references to other operators, forming a graph.

Coherence changes propagate through the graph via *commutators*, simulating a loose form of quantum‑inspired interaction. The global coherence sum is conserved (`_total_coherence`).

### Network Handling

- `network.py` implements an asynchronous TCP server using `asyncio`.
- Incoming packets are parsed according to the protocol version (handshake → login → play).
- `protocol.py` contains version‑specific packet definitions and handlers.
- Keep‑alive logic is version‑aware (different packet IDs and ID encodings).

### Robotics Plugin

- `robotics.py` simulates a simple greenhouse environment.
- A robot reads a temperature sensor (with random fluctuations) and controls a fan.
- Temperature changes affect the robot’s coherence, which in turn alters its emissive value – a visible feedback loop.

### Chunks and Boundary Store

- Chunks are initially “boundary” objects (only metadata). When a player moves nearby, the chunk is *inflated* – its block data is loaded (or generated).
- After being unused, a chunk can be *compressed* back to the boundary store, discarding block‑level detail but keeping summary information.

---

## 🤝 Contributing

Contributions are welcome! This project is experimental, so feel free to open issues or pull requests for:

- Bug fixes
- Additional protocol versions
- Enhanced coherence models
- Dashboard improvements

Please follow the existing code style and include docstrings for new classes/methods.

---

## 📄 License

This project is licensed under the MIT License – see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgements

- Packet structures derived from [wiki.vg](https://wiki.vg/).
- Inspired by concepts from autopoietic systems and coherence‑based rendering.

---

*Happy hacking!*  
– The Pygnosis Team
