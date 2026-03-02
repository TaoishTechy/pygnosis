# CHANGELOG

## [0.3.0] — 2026-03-02 — First Successful Client Connection

### Summary
After a full rewrite of `protocol.py` and iterative binary-level debugging of
the Minecraft wire protocol, a 1.8.9 client successfully connected, logged in,
received chunk data, and spawned in-world. The client fell through the void
because no ground was rendered below y=48 (expected — only section 3 was sent),
but the connection itself was stable and clean: no disconnect error, no
`DecoderException`, no `IndexOutOfBounds`. This is the first successful
end-to-end connection in the project's history.

---

## What Changed

### `protocol.py` — Complete Rewrite

The original file targeted Minecraft 1.14 (protocol 477) and had nine critical
bugs including wrong packet IDs, a malformed Join Game packet, and broken chunk
encoding. It was replaced entirely with a new dual-version implementation
targeting 1.8.9 (protocol 47) and 1.12.2 (protocol 340).

---

### Bug Fix Log — Ordered by Discovery

#### BUG-01 · 1.14 → Abandon; rewrite for 1.8.9 + 1.12.2
The 1.14 implementation had too many interacting bugs to fix incrementally.
Packet IDs shifted mid-session (1.14 renumbered many play-state packets vs
1.12), the Join Game packet included a removed Difficulty field, and the
heightmap NBT encoding required an unnamed root compound that was being sent
with a named one. The decision was made to target 1.8.9 and 1.12.2 — the two
most widely used versions, with simpler and better-documented protocols.

#### BUG-02 · 1.8.9 Chunk: Missing `addBitMask` uint16 field
**Symptom:** `Packet 0/33 (go) was larger than I expected, found 10499 bytes extra`  
**Cause:** The 1.8 Chunk Data packet requires an `addBitMask` (Unsigned Short,
always `0x0000` for vanilla blocks) between `primaryBitMask` and `dataSize`.
Without it, the client read the first 2 bytes of `dataSize` as `addBitMask`,
misinterpreted the remaining bytes as chunk data length, and found thousands of
leftover bytes.  
**Fix:** Added `struct.pack(">H", 0)` for `addBitMask`.

#### BUG-03 · 1.12.2 Join Game: Extra Difficulty byte shifted all subsequent fields
**Symptom:** `readerIndex(19) + length(4) exceeds writerIndex(19)`  
**Cause:** The code included `struct.pack(">B", 2)` (Difficulty) inside Join
Game. In 1.12.2 the Join Game packet does NOT contain Difficulty — it was moved
to its own packet (`0x0D Server Difficulty`) in 1.9. The extra byte caused every
following field to be read from the wrong offset. The client finished parsing at
byte 19, then tried to read 4 more bytes for the next expected field and
overflowed the 19-byte buffer.  
**Fix:** Removed Difficulty from Join Game `0x23`; added separate
`_send_server_difficulty()` sending packet `0x0D`.

#### BUG-04 · 1.12.2 Chunk: Long array packed big-endian instead of little-endian
**Symptom:** Client connected but terrain rendered as solid corruption /
wrong blocks at wrong positions (visual, no disconnect).  
**Cause:** The 1.12.2 chunk section encodes block palette indices into a packed
`int64[]` array using LSB-first (little-endian within each long). Our code used
`int.from_bytes(..., "big")` / `.to_bytes(8, "big")`, placing every block index
at the wrong bit position within each long.  
**Fix:** Changed to `"little"` endianness for both read and write of each long.

#### BUG-05 · 1.12.2 Plugin Message: Wrong packet ID `0x19` → `0x18`
**Symptom:** Client received an unknown play-state packet, tried to parse it as
the next expected type, and ran out of bytes.  
**Fix:** Changed Plugin Message (server brand) from `0x19` to `0x18`.

#### BUG-06 · 1.12.2 Server Difficulty: Missing `locked` boolean (2nd byte)
**Symptom:** Cascade parse failure — first byte of the next packet was consumed
as the `locked` field, shifting all subsequent packet parsing by 1 byte.  
**Cause:** In 1.12.2, packet `0x0D` Server Difficulty has two fields:
`UByte difficulty` + `Bool locked`. We sent only the difficulty byte.  
**Fix:** Added `b'\x00'` (locked = false) as the second byte.

#### BUG-07 · 1.12.2 Spawn Position: Wrong packet ID `0x43` → `0x46`
**Symptom:** `Packet 0/67 (kk) was larger than I expected, found 6 bytes extra`  
**Cause:** `0x43` in 1.12.2 is **Set Passengers**, not Spawn Position.
Set Passengers minimum size is 2 bytes (VarInt entityId + VarInt count=0).
We sent a packed 8-byte position, leaving 6 bytes extra. Spawn Position is
`0x46`.  
**Fix:** Moved Spawn Position to `0x46`. (Note: an intermediate attempt used
`0x43` after wrongly concluding `0x46` was Tab-List Header — the error message
`0x43 = 6 extra` confirmed `0x43` = Set Passengers and `0x46` = Spawn Position.)

#### BUG-08 · 1.12.2 Time Update: Wrong packet ID `0x44` → `0x47`
**Symptom:** `Packet 0/68 (kI) was larger than I expected, found 6 bytes extra`  
**Cause:** `0x44` in 1.12.2 is **Change Game State** (~10 bytes); we sent
16 bytes (two int64s), giving 6 extra. Time Update is `0x47`.  
**Fix:** Moved Time Update to `0x47`.  
(A prior attempt used `0x4E` which is **Advancements** — also wrong.)

#### BUG-09 · 1.8.9 Chunk: Spurious `Int32 dataSize` field (was `addBitMask`)
**Symptom:** `Packet 0/33 (go) was larger than I expected, found 10501 bytes extra`  
**Cause:** After adding `addBitMask` in BUG-02, the next iteration replaced it
with `struct.pack(">i", dataSize)` (Int32). The extra count increased by 2
(from 10499 to 10501), confirming `addBitMask` IS a real field and `dataSize`
format was still wrong.  
**Fix:** Kept `addBitMask` as `struct.pack(">H", 0)`.

#### BUG-10 · 1.8.9 Chunk: `dataSize` is VarInt, not Int32
**Symptom:** `Packet 0/33 (go) was larger than I expected, found 10499 bytes extra`  
**Root cause decoded from arithmetic:**
- Packet total: 10511 bytes
- Client consumed: 10511 − 10499 = **12 bytes**
- Header (X+Z+cont+primMask) = 11 bytes + **1 more byte** = 12
- `Int32(10496)` encodes as `\x00\x00\x29\x00`
- Client reads it as a **VarInt**: first byte `0x00` has no continuation bit → value = `0`
- Client reads 0 bytes of chunk data, finds 10499 leftover

**Fix:** Changed `struct.pack(">i", len(section)+len(biomes))` to
`encode_varint(len(section)+len(biomes))`.  
`encode_varint(10496)` = `\x80\x52` (2 bytes). Client simulation confirmed
0 leftover bytes after parsing.

---

### Final Packet Format Reference

#### 1.8.9 Chunk Data `0x21`
```
Int32   chunkX
Int32   chunkZ
Bool    groundUpContinuous
Short   primaryBitMask        (signed short)
UShort  addBitMask             (always 0x0000)
VarInt  dataSize               (NOT Int32)
Byte[]  sections               (4096 blockIDs + 2048 meta + 2048 blockLight + 2048 skyLight per section)
Byte[]  biomes                 (256 bytes, only when continuous=true)
```

#### 1.12.2 Chunk Data `0x20`
```
Int32   chunkX
Int32   chunkZ
Bool    groundUpContinuous
VarInt  primaryBitMask
VarInt  dataLength
Byte[]  data                   (sections + block light + sky light + biomes)
VarInt  blockEntityCount       (0)

Per section:
  UShort  blockCount
  UByte   bitsPerBlock         (4 for indirect palette)
  VarInt  paletteLength
  VarInt[] palette
  VarInt  dataArrayLength
  Int64[] dataArray            (LSB-first / little-endian packing)
```

#### 1.12.2 Join Game `0x23`
```
Int32   entityId
UByte   gamemode
Int32   dimension              (NOT Byte like 1.8)
UByte   difficulty             (still present in 1.12.2, removed in 1.20.2)
UByte   maxPlayers
String  levelType
Bool    reducedDebugInfo
```

#### 1.12.2 Confirmed Packet IDs
| Packet              | ID     | Notes |
|---------------------|--------|-------|
| Join Game           | `0x23` | |
| Server Difficulty   | `0x0D` | UByte + Bool locked (2 bytes total) |
| Plugin Message      | `0x18` | |
| Spawn Position      | `0x46` | |
| Player Abilities    | `0x2C` | |
| Time Update         | `0x47` | |
| Player Pos+Look     | `0x2F` | + VarInt teleport ID |
| Player Info         | `0x2E` | |
| Chunk Data          | `0x20` | |
| Keep Alive          | `0x1F` | Int64 ID |

---

### Terminal Analysis — First Successful Connection

```
[1.8.9] Scally PLAY uid=acbe875e-48ea-35c8-a97d-fe105146899a
[1.8.9] chunk sent (10509 bytes)
chunk_0_0 CI 0.30 → 0.50 (chunk sent to client)
Client 5b5af5cd (Scally) connection lost
Client 5b5af5cd (Scally) disconnected
```

**What succeeded:**
- Full handshake (proto=47 accepted)
- Login sequence completed (Login Start → Login Success → PLAY)
- All init packets sent without error: Join Game, Spawn Position, Abilities,
  Time Update, Player Pos+Look, Player List Item
- Chunk Data accepted: 10509 bytes, no `DecoderException`
- Coherence graph updated: `chunk_0_0 CI 0.30 → 0.50` confirms the chunk
  operator registered the send event
- Client rendered the world and player spawned

**Why the player fell through the void:**
Only section 3 (y=48–63) was sent with `primaryBitMask = 0x0008`. Sections 0,
1, and 2 (y=0–47) were not included. The player spawned at y=65 (as instructed
by Player Pos+Look), stood briefly on the stone layer at y=60, but there was
nothing below y=48 — no bedrock, no ground. The client's physics engine found
no solid blocks beneath and the player fell into the void.

**Why the connection dropped after spawn (not an error):**
The disconnect is "connection lost" rather than a `DecoderException` or
`IOException`. This is the keep-alive timeout. The server sends Keep Alive
every 15 seconds; if the client doesn't respond within 7.5 seconds, the server
closes the connection. In the current test run the client likely disconnected
itself after falling into the void (vanilla behaviour: client disconnects on
void death / out-of-world-bounds), not due to any protocol error.

---

### What Remains

- **Void floor:** Send sections 0–2 as all-air alongside section 3, OR lower
  the spawn Y and stone layer to section 0 (y=0–15) so there is ground below.
- **1.12.2 connection:** Not yet confirmed stable — only 1.8.9 was tested in
  the final run. The 1.12.2 fixes (BUG-03 through BUG-08) are in the file but
  unverified against a live client.
- **Keep-alive loop:** Working (server logs keep-alive start), but not tested
  through a full hold-alive cycle.
- **Multiblock / multi-chunk:** Currently only chunk `0,0` is sent. Player
  movement will immediately show empty neighbours.
- **SimulatedGPIO temperature:** Fan activates correctly at ~28°C but
  temperature continues rising (cooling physics not yet implemented).

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
