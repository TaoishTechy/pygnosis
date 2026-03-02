# Changelog

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
