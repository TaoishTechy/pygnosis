# Pygnosis Forge Integration

## Overview

This document describes the complete Forge integration layer that gives Pygnosis full access to:
- All loaded `.jar` mods and their item/block/entity registries
- Forge lifecycle events (block breaks, entity spawns, redstone, crafting, etc.)
- Full Forge API surface (spawn any entity, place any block, run any command)
- CC:Tweaked turtle and computer control with MOGOPS Lua/Python API
- Coherence-driven LOD packets to Minecraft clients

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                   Forge JVM (Minecraft 1.20.1)                 │
│                                                                │
│  PygnosisMod.java          ← mod entry point (@Mod)           │
│  ├── PygnosisBridge.java   ← socket server (port 25570)        │
│  │   ├── JarRegistry.java  ← indexes all mod registries        │
│  │   └── CommandExecutors  ← set blocks, spawn entities, etc.  │
│  ├── ForgeEventDispatcher  ← fires all Forge events to Python   │
│  ├── ForgePacketBridge     ← custom MC network channel          │
│  │   └── CoherenceLODPacket← LOD updates to connected clients  │
│  └── CCTurtleOperator      ← CC:Tweaked turtle/computer hooks  │
│                                                                │
│  TCP localhost:25570  ← newline-delimited JSON                  │
└─────────────────────────┬──────────────────────────────────────┘
                          │
┌─────────────────────────▼──────────────────────────────────────┐
│                   Pygnosis Python Engine                       │
│                                                                │
│  forge/bridge.py     ← ForgeBridge (async client)             │
│  forge/jar_manager.py← JarManager + ModOperator               │
│  cc/api.py           ← MOGOPS math: superpose, retro, fractal  │
│  core.py             ← CorrelationGraphManager                  │
│  world.py            ← Chunk, Player, Item                      │
│  network.py          ← Minecraft protocol (port 25565)          │
│  admin.py            ← HTTP dashboard (port 8081)               │
└────────────────────────────────────────────────────────────────┘
```

---

## Building the Forge Mod

### Requirements
- Java 17 JDK
- Minecraft Forge MDK 1.20.1-47.2.20
- Gradle 8.x (included as gradlew)

### Steps

```bash
cd forge-mod/

# On Linux/macOS:
chmod +x gradlew
./gradlew build

# On Windows:
gradlew.bat build
```

The compiled JAR will be at:
```
build/libs/pygnosis-forge-1.0.0.jar
```

Copy it to your Minecraft `mods/` folder.

### Running a Test Server

```bash
./gradlew runServer
```

This starts a local Forge server. Connect your Pygnosis Python server to it.

---

## Running the Full Stack

### 1. Start Pygnosis Python Server

```bash
# With Forge bridge (default)
python main.py

# With debug output
python main.py --debug

# Point to your mods directory (for local JAR scanning)
python main.py --mods-dir /home/user/.minecraft/mods

# Without Forge (standalone mode)
python main.py --no-forge
```

### 2. Start Forge Server

Install `pygnosis-forge-1.0.0.jar` in your server's `mods/` folder and start it.
The mod automatically connects to Pygnosis on `localhost:25570`.

### 3. Connect Minecraft Client

Connect to `localhost:25565` using Minecraft 1.14.x (protocol 477).

---

## Message Protocol

All communication is **newline-delimited JSON** over TCP on port 25570.

### Envelope Format

```json
{
  "type":      "event_or_command_name",
  "timestamp": 1700000000000,
  "data":      { ... }
}
```

### Events: Java → Python

| Event Type | Trigger | Key Data Fields |
|------------|---------|-----------------|
| `block_break` | Player/explosion breaks a block | `x,y,z, block, player, sigma_topo` |
| `block_place` | Entity places a block | `x,y,z, block, dimension` |
| `block_neighbor_notify` | Redstone/neighbour update | `x,y,z, sigma_topo=0.15` |
| `chunk_load` | Chunk loaded by Forge | `cx, cz, dimension` |
| `chunk_unload` | Chunk unloaded | `cx, cz, dimension` |
| `entity_spawn` | Any entity joins world | `uuid, type, x,y,z, initial_ci` |
| `entity_despawn` | Entity leaves world | `uuid` |
| `entity_death` | LivingEntity dies | `uuid, type, x,y,z` |
| `player_login` | Player logs in | `uuid, username, x,y,z` |
| `player_logout` | Player logs out | `uuid, username` |
| `player_interact_block` | Right-click on block | `uuid, x,y,z, hand, held_item` |
| `item_pickup` | Player picks up item | `player_uuid, item, count` |
| `item_crafted` | Item crafted | `player_uuid, item, count` |
| `item_smelted` | Item smelted | `player_uuid, item` |
| `explosion` | Explosion detonates | `blocks_affected, entities_affected, sigma_topo=0.8` |
| `server_tick` | Every 20 ticks (1 sec) | `tick` |
| `server_started` | Forge server ready | `message` |
| `jar_list_response` | Response to cmd_jar_list | `mods[], cc_loaded, jei_loaded` |
| `jar_registry_response` | Response to cmd_jar_registry | `mod_id, blocks[], items[], entities[]` |
| `block_query_response` | Response to cmd_query_block | `x,y,z, block, properties{}` |

### Commands: Python → Java

| Command Type | Effect | Key Parameters |
|--------------|--------|----------------|
| `cmd_set_block` | Place/remove block at coordinates | `x,y,z, block, dimension, nbt?` |
| `cmd_spawn_entity` | Spawn any entity | `type, x,y,z, dimension, nbt?` |
| `cmd_give_item` | Give items to player | `player_name, item, count, nbt?` |
| `cmd_run_command` | Execute server command as op | `command` |
| `cmd_query_block` | Get block state | `x,y,z, dimension` |
| `cmd_jar_list` | List all loaded mods | (none) |
| `cmd_jar_registry` | Get full registry for mod | `mod_id` |
| `cmd_coherence_lod` | Push LOD update to clients | `entity_uuid, coherence, lod_level` |
| `cmd_turtle_move` | Move CC turtle | `turtle_uuid, direction, steps` |
| `cmd_turtle_dig` | CC turtle dig | `turtle_uuid, side` |
| `cmd_turtle_place` | CC turtle place | `turtle_uuid, side, slot` |
| `cmd_turtle_exec_lua` | Run Lua in turtle | `turtle_uuid, code` |
| `cmd_ping` | Heartbeat check | (none) → `pong` response |

---

## JAR Registry Integration

Once connected, Pygnosis receives a full index of every item, block,
and entity type contributed by every loaded mod.

### Python usage

```python
# After bridge connects:
mods = await engine.forge_bridge.list_mods()
# Returns: {mods: [{mod_id, mod_name, version, blocks, items, entities, ...}]}

# Get full registry for a specific mod
botania = await engine.forge_bridge.get_mod_registry("botania")
# Returns: {mod_id: "botania", items: [...], blocks: [...], entities: [...]}

# Search all mods for items matching a query
iron_items = engine.jar_manager.search_items_global("iron")
# → ["minecraft:iron_ingot", "minecraft:iron_ore", "thermal:iron_dust", ...]

# Get semantic distance between two items
d = engine.jar_manager.semantic_distance("botania:manaflower", "botania:endoflame")
# → 0.1 (same mod namespace → close)
d2 = engine.jar_manager.semantic_distance("botania:manaflower", "minecraft:flower")
# → 0.7 (different namespace)

# Find which mod owns a registry name
owner = engine.jar_manager.find_owner("thermal:machine_frame")
# → ModOperator(mod_id="thermal", coherence=0.65)
```

### Spawning Forge mod entities

```python
# Spawn a Botania Living Wood entity
await engine.forge_bridge.spawn_entity("botania:living_wood", x=10, y=64, z=10)

# Place a Mekanism machine block
await engine.forge_bridge.set_block(0, 64, 0, "mekanism:energized_smelter")

# Give Thermal Foundation items to a player
await engine.forge_bridge.give_item("Alex", "thermal:enderium_ingot", count=16)

# Execute a Forge command
await engine.forge_bridge.run_command("tellraw @a {\"text\":\"Pygnosis online\",\"color\":\"aqua\"}")
```

---

## Coherence LOD Pipeline

```
Pygnosis scheduler (Python)
  → op.coherence changes
    → ForgeBridge.set_coherence_lod(mc_uuid, ci)
      → Forge: cmd_coherence_lod
        → CoherenceLODPacket → connected Minecraft clients
          → ClientCoherenceHandler.applyLOD(uuid, ci, lod_level)
            → entity rendered at lod_level detail:
               0 = invisible (boundary)
               1 = no animations
               2 = normal
               3 = MERS emissive + subsurface glow effects
```

LOD levels map to coherence thresholds:
- `CI > 0.75` → LOD 3 (full MERS effects)
- `CI > 0.50` → LOD 2 (normal)
- `CI > 0.30` → LOD 1 (compressed)
- `CI ≤ 0.30` → LOD 0 (boundary / invisible)

---

## CC:Tweaked Integration (Pygnosis:CC)

When CC:Tweaked is loaded, every turtle and computer automatically
receives the `pygnosis` Lua table with MOGOPS math functions:

```lua
-- In any CC:Tweaked Lua script:

-- Get this turtle's coherence
local ci = pygnosis.coherence("self")

-- Quantum miner: superpose left and right tunnels
local result = pygnosis.quantum_mine(
    function() turtle.dig(); turtle.forward() end,
    function() turtle.turnLeft(); turtle.dig(); turtle.forward() end,
    ci
)

-- Semantic sorting: find the most "precious" item in inventory
local items = {"minecraft:stone", "minecraft:diamond", "minecraft:coal"}
local sorted = pygnosis.semantic_sort(items, "diamond")
-- → {"minecraft:diamond", "minecraft:coal", "minecraft:stone"}

-- Fractal scan: analyse terrain at multiple scales
local results = pygnosis.fractal(4.0, "scan_terrain")

-- Self-modifying action function
if ci > 0.8 then
    pygnosis.autopoietic("function action() print('High CI: optimized path') end")
end

-- Retrocausal: receive optimal direction from future execution
local best_dir = pygnosis.retro("compute_optimal_direction", 3)
turtle.turn(best_dir)
```

### Python-side turtle control

```python
from pygnosis.forge.bridge import ForgeBridge

bridge = ForgeBridge(engine)
await bridge.connect()

# Move a specific turtle
await bridge.turtle_move("turtle-uuid-here", direction="forward", steps=5)

# Dig
await bridge.turtle_dig("turtle-uuid-here", side="front")

# Inject and run Lua code in a specific turtle
await bridge.turtle_exec_lua("turtle-uuid-here", """
    local ci = pygnosis.coherence("self")
    print("My coherence: " .. ci)
    if ci > 0.7 then
        turtle.dig()
    end
""")
```

---

## Mod Operator Coherence

Every loaded mod is represented as a `ModOperator` in the correlation graph.
Coherence reflects activity:

| Scenario | Coherence |
|----------|-----------|
| Mod just loaded, no activity | `0.3 + content/5000` |
| Mod's blocks being actively changed | `+0.3 σ_topo` per event |
| CC:Tweaked with running scripts | `0.6–0.9` |
| Unused mod in idle world | decays to `~0.3` |

Mods with more content (Botania, Mekanism, Thermal) have slightly higher
base coherence, reflecting their larger footprint on the simulation.

---

## Configuration

All Pygnosis network configuration remains in `network_config.json`.
Forge bridge port is set in `PygnosisBridge.DEFAULT_PORT` (default: 25570).

To disable the Forge bridge:
```bash
python main.py --no-forge
```

To point to a different mods directory:
```bash
python main.py --mods-dir /path/to/minecraft/mods
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused 25570` | Ensure Forge server is running with pygnosis-forge.jar installed |
| `No events received` | Check Forge logs for `Pygnosis bridge started on port 25570` |
| `CC:Tweaked not detected` | Ensure cc-tweaked.jar is in mods/ folder |
| `cmd_set_block has no effect` | Block registry name must include namespace: `minecraft:stone` not `stone` |
| `cmd_spawn_entity fails` | Check entity type is a valid Forge registry name |
| `Bridge disconnects repeatedly` | Verify no firewall blocking localhost:25570 |

---

## Performance Notes

- The bridge uses a single TCP connection with newline-delimited JSON.
- Outbound queue is bounded at 10,000 messages to prevent OOM under event floods.
- Block neighbour notify events (redstone) are high-frequency; consider filtering if not needed.
- JAR registry dumps for large mods (Mekanism: ~800 items) may take 100-200ms.
- CoherenceLODPackets are sent per-entity per-tick for active entities; batch with `broadcastCoherenceSync` for >50 entities.
