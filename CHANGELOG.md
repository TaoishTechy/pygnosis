# Changelog

## [1.0.3] - 2025-03-02
### Fixed (Protocol & Network)
- **Packet IDs for 1.14** – corrected to match protocol 477 (wiki.vg):
  - Player Info: `0x30` (was `0x33`)
  - Player Abilities: `0x2E` (was `0x31`)
  - Player Position & Look: `0x32` (was `0x35`)
  - Spawn Position: `0x43` (was `0x42`)
  - Time Update: `0x4A` (was `0x4E`)
  - Update Light: `0x24` (was `0x23`)
  - Chat Message (outgoing): `0x0F` (was `0x02`)
- **Join Game packet (0x25)** – removed erroneous `difficulty` byte and added missing `view distance` VarInt; packet now matches 1.14 specification.
- **Update Light packet** – corrected coordinate fields to VarInt (was Int) and added four masks as required.
- **NBT heightmaps in chunk data** – root compound is now unnamed (length 0), preventing client parsing errors.
- **`handle_handshake` in `Protocol_1_14`** – now raises `RuntimeError` to catch accidental calls.
- **Exception handling** – added try/except around packet handlers to log errors and close client gracefully.

### Improved
- **Robotics temperature simulation** – added cooling when fan is active to prevent runaway heating.
- **Error logging** – tracebacks are now printed for unexpected exceptions, aiding debugging.

## [1.0.2] - 2025-03-01
### Fixed
- **Chunk data packet** – set `full` flag to `False` (`b'\x00'`) when only one chunk section is sent; previously `True` caused the client to read beyond the buffer and disconnect.
- **Connection drops due to missing `IncompleteReadError` handling** – now catch `asyncio.IncompleteReadError` alongside `ConnectionResetError` and `BrokenPipeError`.
- **Read timeouts** – added `asyncio.wait_for()` with a configurable timeout (30 seconds) when reading the first byte of a packet, and a shorter timeout (5 seconds) for subsequent bytes, preventing resource exhaustion.
- **Player abilities flags** – corrected from `0x0A` (creative + flying) to `0x00` (survival, no flying), aligning with normal gameplay.
- **Chat packet format** – now includes the required `position` (byte) and `sender` (UUID) fields; previously only the message was sent, causing client-side parsing errors.
- **UUID generation** – changed to use the `"OfflinePlayer:" + username` prefix, matching vanilla Minecraft’s offline UUID scheme and avoiding collisions with online-mode servers.
- **Keep‑alive task leak** – added a `_closed` flag and ensure the task is cancelled immediately in `close()`; the loop now checks this flag and self‑cancels.
- **Varint reading inefficiency** – improved by reading the first byte, then reading additional bytes in a single loop with timeouts, reducing the number of `readexactly` calls.

### Removed
- **Unused `RingBuffer` class** – previously allocated per client but never used; removed to avoid confusion and reduce memory footprint.

### Changed
- **Global `network_manager` references** – replaced with dependency injection via `engine.network_manager`, eliminating circular imports and improving testability.
- **Exception handling in packet handlers** – wrapped all handler calls in a try‑except block; any exception now logs the error and closes the client gracefully.

## [1.0.1] - 2025-03-01
### Fixed
- **Client disconnecting immediately after login** – resolved by correcting multiple protocol packet IDs and field layouts for Minecraft 1.14.

### `protocol.py`
- **Join Game packet (0x25)**: removed erroneous `view distance` VarInt field, which corrupted the packet and caused the client to disconnect.
- **Clientbound packet IDs** updated to match [wiki.vg](https://wiki.vg/Protocol) for 1.14:
  - Player Info: `0x33` (was `0x34`)
  - Player Position & Look: `0x35` (was `0x36`)
  - Player Abilities: `0x31` (was `0x32`)
  - Chunk Data: `0x21` (was `0x22`)
  - Keep Alive (outgoing): `0x20` (was `0x00`)
- **Serverbound packet handling** remapped to correct IDs:
  - Chat Message: `0x03` (was `0x0E`)
  - Plugin Message: `0x0B` (was `0x0A`)
  - Keep Alive response: `0x10` (was `0x0B`)
  - Player Position: `0x12` (was `0x10`)
- **Packet sending order**: ensured Join Game is sent first, followed by other essential packets as required by the protocol.

### `network.py`
- **Keep-alive sender**: corrected the packet ID used in the keep-alive loop to `0x20` (clientbound keep alive), matching the updated protocol.

### Result
Minecraft 1.14 clients now connect successfully and remain connected without immediate disconnection.
