# protocol.py  —  Pygnosis  |  1.8.9 (proto 47)  +  1.12.2 (proto 340)
#
# Packet-ID reference:
#   1.8.9  → https://wiki.vg/index.php?title=Protocol&oldid=7368
#   1.12.2 → https://wiki.vg/index.php?title=Protocol&oldid=13223
#
# Bugs fixed vs previous version:
#   [1.8  chunk]   addBitMask uint16 field was missing; shifted dataSize offset
#                  → "packet 0/33 larger than expected, 10499 bytes extra"
#   [1.8  chunk]   block index formula used wrong axis order (Z*16+X vs Z*256+X... wait no)
#   [1.12 join]    had extra Difficulty byte; removed from Join Game in 1.9+
#                  → IndexOutOfBoundsException: readerIndex(19)+length(4)>writerIndex(19)
#   [1.12 chunk]   longs were big-endian; spec requires LSB-first (little-endian) packing
#   [1.12 brand]   plugin message packet ID was 0x19; correct for 1.12.2 is 0x18

import asyncio
import json
import struct
import uuid
from typing import Dict

from network import encode_varint, decode_varint, ClientConnection

# ─────────────────────────────────────────────────────────────────────────────
PROTO_1_8  = 47
PROTO_1_12 = 340

SUPPORTED = {
    PROTO_1_8:  "1.8.9",
    PROTO_1_12: "1.12.2",
}


# ─────────────────────────────────────────────────────────────────────────────
# Base handler
# ─────────────────────────────────────────────────────────────────────────────
class ProtocolHandler:
    VERSION = "base"

    def __init__(self):
        self.login_packets:  Dict[int, object] = {}
        self.play_packets:   Dict[int, object] = {}
        self.status_packets: Dict[int, object] = {}

    def enc_str(self, s: str) -> bytes:
        b = s.encode("utf-8")
        return encode_varint(len(b)) + b

    def dec_str(self, buf: bytes, off: int = 0):
        n, c = decode_varint(buf, off)
        return buf[off + c: off + c + n].decode("utf-8"), off + c + n

    def enc_uuid_bytes(self, u: uuid.UUID) -> bytes:
        return struct.pack(">QQ", u.int >> 64, u.int & 0xFFFFFFFFFFFFFFFF)

    def enc_uuid_str(self, u: uuid.UUID) -> bytes:
        return self.enc_str(str(u))

    async def handle_packet(self, client: ClientConnection, pid: int, data: bytes, engine):
        try:
            if client.protocol_state == "HANDSHAKE":
                await self.handle_handshake(client, data, engine)
            elif client.protocol_state == "STATUS":
                h = self.status_packets.get(pid)
                if h:
                    await h(client, data, engine)
            elif client.protocol_state == "LOGIN":
                h = self.login_packets.get(pid)
                if h:
                    await h(client, data, engine)
                else:
                    print(f"  Unhandled LOGIN 0x{pid:02x}")
            elif client.protocol_state == "PLAY":
                h = self.play_packets.get(pid)
                if h:
                    await h(client, data, engine)
        except Exception as exc:
            import traceback
            print(f"Packet error pid=0x{pid:02x} state={client.protocol_state}: {exc}")
            traceback.print_exc()
            await client.close()

    async def handle_handshake(self, client, data, engine):
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Handshake handler
# ─────────────────────────────────────────────────────────────────────────────
class HandshakeHandler(ProtocolHandler):
    VERSION = "handshake"

    async def handle_handshake(self, client: ClientConnection, data: bytes, engine):
        off = 0
        proto, c = decode_varint(data, off);  off += c
        addr,  off = self.dec_str(data, off)
        port   = struct.unpack(">H", data[off: off + 2])[0]; off += 2
        nxt, _ = decode_varint(data, off)

        print(f"Handshake proto={proto} addr={addr}:{port} next={nxt}")

        if nxt == 1:
            client.protocol_state = "STATUS"
            client.handler = _get_handler(proto)
        elif nxt == 2:
            if proto not in SUPPORTED:
                print(f"Unsupported proto {proto}. Supported: {list(SUPPORTED.keys())}")
                await client.close()
                return
            client.protocol_version = proto
            client.handler = _get_handler(proto)
            client.protocol_state = "LOGIN"
            print(f"Accepted proto {proto} ({SUPPORTED[proto]})")
        else:
            print(f"Unknown next-state {nxt}")
            await client.close()


# ─────────────────────────────────────────────────────────────────────────────
# 1.8.9  (protocol 47)
# ─────────────────────────────────────────────────────────────────────────────
class Protocol_1_8(ProtocolHandler):
    """
    Clientbound play:
      0x00 Keep Alive  |  0x01 Join Game  |  0x02 Chat  |  0x03 Time Update
      0x05 Spawn Pos   |  0x08 Pos+Look   |  0x21 Chunk |  0x38 PlayerList
      0x39 Abilities

    Serverbound play:
      0x00 Keep Alive  |  0x01 Chat  |  0x04 PlayerPos  |  0x06 PlayerPosLook
      0x15 Settings    |  0x17 Plugin
    """
    VERSION = "1.8.9"
    keep_alive_packet_id  = 0x00
    keep_alive_id_encoder = staticmethod(lambda i: encode_varint(i & 0x7FFFFFFF))

    def __init__(self):
        super().__init__()
        self.status_packets = {0x00: self._status_req, 0x01: self._ping}
        self.login_packets  = {0x00: self._login_start}
        self.play_packets   = {
            0x00: self._keep_alive_resp,
            0x01: self._chat_recv,
            0x04: self._pos_recv,
            0x06: self._pos_look_recv,
            0x15: self._client_settings,
            0x17: self._plugin_msg,
        }

    async def _status_req(self, client, data, engine):
        n = len(engine.network_manager.clients) if engine.network_manager else 0
        resp = {
            "version":     {"name": "Pygnosis 1.8.9", "protocol": PROTO_1_8},
            "players":     {"max": 20, "online": n, "sample": []},
            "description": {"text": "Pygnosis | 1.8.9"},
        }
        await client.send_packet(0x00, self.enc_str(json.dumps(resp)))

    async def _ping(self, client, data, engine):
        await client.send_packet(0x01, data)

    async def _login_start(self, client, data, engine):
        username, _ = self.dec_str(data)
        client.username = username
        uid = uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + username)
        await client.send_packet(0x02, self.enc_uuid_str(uid) + self.enc_str(username))
        client.protocol_state = "PLAY"
        print(f"[1.8.9] {username} PLAY uid={uid}")

        await self._send_join_game(client)
        await self._send_spawn_position(client)
        await self._send_player_abilities(client)
        await self._send_time_update(client)
        await self._send_player_pos_look(client)
        await self._send_player_list_item(client, uid)
        await self._send_chunk(client, engine)

        if engine.network_manager:
            engine.network_manager.start_keep_alive(client)

    # ── Join Game 0x01 ─────────────────────────────────────────────────────
    # Fields: Int EID | UByte Gamemode | Byte Dimension | UByte Difficulty
    #         | UByte MaxPlayers | String LevelType | Bool ReducedDebug
    async def _send_join_game(self, client):
        data  = struct.pack(">i", 1)       # entity id
        data += struct.pack(">B", 0)       # gamemode: survival
        data += struct.pack(">b", 0)       # dimension: overworld (SIGNED byte in 1.8)
        data += struct.pack(">B", 2)       # difficulty: normal
        data += struct.pack(">B", 20)      # max players
        data += self.enc_str("default")    # level type
        data += b'\x00'                    # reduced debug info
        await client.send_packet(0x01, data)

    # ── Spawn Position 0x05 ────────────────────────────────────────────────
    async def _send_spawn_position(self, client):
        x, y, z = 0, 64, 0
        pos = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
        await client.send_packet(0x05, struct.pack(">Q", pos))

    # ── Player Abilities 0x39 ──────────────────────────────────────────────
    async def _send_player_abilities(self, client):
        await client.send_packet(0x39,
            struct.pack(">b", 0) + struct.pack(">ff", 0.05, 0.1))

    # ── Time Update 0x03 ───────────────────────────────────────────────────
    async def _send_time_update(self, client):
        await client.send_packet(0x03, struct.pack(">qq", 0, 6000))

    # ── Player Position and Look 0x08 ──────────────────────────────────────
    # X Y Z (double) | Yaw Pitch (float) | OnGround (byte)
    # NO teleport ID in 1.8
    async def _send_player_pos_look(self, client):
        data  = struct.pack(">ddd", 0.0, 65.0, 0.0)
        data += struct.pack(">ff", 0.0, 0.0)
        data += b'\x00'    # on-ground flag
        await client.send_packet(0x08, data)

    # ── Player List Item 0x38 ──────────────────────────────────────────────
    async def _send_player_list_item(self, client, uid: uuid.UUID):
        header  = encode_varint(0)          # action: add player
        header += encode_varint(1)          # count
        entry   = self.enc_uuid_bytes(uid)
        entry  += self.enc_str(client.username)
        entry  += encode_varint(0)          # no properties
        entry  += encode_varint(0)          # gamemode: survival
        entry  += encode_varint(0)          # ping: 0 ms
        entry  += b'\x00'                   # no display name
        await client.send_packet(0x38, header + entry)

    # ── Chunk Data 0x21 ────────────────────────────────────────────────────
    # 1.8.9 Notchian client S21PacketChunkData.readPacketData reads:
    #   Int   chunkX
    #   Int   chunkZ
    #   Bool  groundUpContinuous
    #   Short primaryBitMask       (signed short, NOT unsigned, NO addBitMask)
    #   Int   dataSize             (explicit byte count — client does NOT infer from frame)
    #   Byte[dataSize] data        (sections then biomes)
    #
    # Section layout per set bit in primaryBitMask (low→high):
    #   4096 × uint8  block IDs   (index = y*256 + z*16 + x)
    #   2048 × nibble metadata
    #   2048 × nibble block light
    #   2048 × nibble sky light
    #
    # Biomes: 256 × uint8 appended after all sections when continuous=true
    async def _send_chunk(self, client, engine):
        chunk = engine.graph.get("chunk_0_0")
        if not chunk:
            return
        raw = self._encode_chunk_1_8(chunk)
        await client.send_packet(0x21, raw)
        print(f"[1.8.9] chunk sent ({len(raw)} bytes)")
        chunk.update_coherence(0.2, "chunk sent to client")

    def _encode_chunk_1_8(self, chunk) -> bytes:
        SECTION = 3    # y=48..63; stone floor at local_y=12 (world y=60)

        ids = bytearray(4096)
        for lx in range(16):
            for lz in range(16):
                local_y = 12   # world y=60 → local y = 60 - SECTION*16 = 12
                ids[local_y * 256 + lz * 16 + lx] = 1   # stone

        section  = bytes(ids)                # 4096 block IDs
        section += bytes(2048)               # metadata nibbles: all 0
        section += bytes([0xFF] * 2048)      # block light: max
        section += bytes([0xFF] * 2048)      # sky light: max

        biomes = bytes([1] * 256)            # plains=1

        payload  = struct.pack(">i", chunk.cx)
        payload += struct.pack(">i", chunk.cz)
        payload += b'\x01'                            # groundUpContinuous
        payload += struct.pack(">h", 1 << SECTION)    # primaryBitMask (signed short)
        # dataSize must be VarInt in 1.8.9, NOT Int32.
        # Int32(10496)=b'\x00\x00\x29\x00'; client reads VarInt 0x00=0 → 10499 bytes extra.
        payload += encode_varint(len(section) + len(biomes))  # dataSize as VarInt
        payload += section
        payload += biomes
        return payload

    # ── serverbound ────────────────────────────────────────────────────────
    async def _keep_alive_resp(self, client, data, engine):
        ka_id, _ = decode_varint(data)
        if ka_id == (client.last_keep_alive_id & 0x7FFFFFFF):
            client.keep_alive_pending = False

    async def _chat_recv(self, client, data, engine):
        msg, _ = self.dec_str(data)
        print(f"[1.8.9] chat {client.username}: {msg}")
        if engine.network_manager:
            pkt = b'\x00' + self.enc_str(json.dumps({"text": f"<{client.username}> {msg}"})) + b'\x00'
            await engine.network_manager.broadcast_packet(0x02, pkt)

    async def _pos_recv(self, client, data, engine):
        if len(data) >= 24:
            _update_pos(client, engine, *struct.unpack(">ddd", data[:24]))

    async def _pos_look_recv(self, client, data, engine):
        if len(data) >= 24:
            _update_pos(client, engine, *struct.unpack(">ddd", data[:24]))

    async def _client_settings(self, client, data, engine):
        locale, off = self.dec_str(data)
        print(f"[1.8.9] {client.username} settings locale={locale}")

    async def _plugin_msg(self, client, data, engine):
        channel, _ = self.dec_str(data)
        print(f"[1.8.9] {client.username} plugin channel={channel}")


# ─────────────────────────────────────────────────────────────────────────────
# 1.12.2  (protocol 340)
# ─────────────────────────────────────────────────────────────────────────────
class Protocol_1_12(ProtocolHandler):
    """
    Clientbound play:
      0x1F Keep Alive  |  0x23 Join Game  |  0x0D Chat  |  0x0D Server Difficulty
      0x18 Plugin Msg  |  0x4E Time Update |  0x43 Spawn Pos  |  0x2C Abilities
      0x2F Pos+Look    |  0x20 Chunk Data  |  0x2E Player Info

    Serverbound play:
      0x00 Teleport Confirm  |  0x02 Chat  |  0x04 Settings
      0x09 Plugin            |  0x0B Keep Alive  |  0x0E PlayerPos
      0x0F PlayerPosLook
    """
    VERSION = "1.12.2"
    keep_alive_packet_id  = 0x1F
    keep_alive_id_encoder = staticmethod(lambda i: struct.pack(">q", i))

    def __init__(self):
        super().__init__()
        self.status_packets = {0x00: self._status_req, 0x01: self._ping}
        self.login_packets  = {0x00: self._login_start}
        self.play_packets   = {
            0x00: self._teleport_confirm,
            0x02: self._chat_recv,
            0x04: self._client_settings,
            0x09: self._plugin_msg,
            0x0B: self._keep_alive_resp,
            0x0E: self._pos_recv,
            0x0F: self._pos_look_recv,
        }

    async def _status_req(self, client, data, engine):
        n = len(engine.network_manager.clients) if engine.network_manager else 0
        resp = {
            "version":     {"name": "Pygnosis 1.12.2", "protocol": PROTO_1_12},
            "players":     {"max": 20, "online": n, "sample": []},
            "description": {"text": "Pygnosis | 1.12.2"},
        }
        await client.send_packet(0x00, self.enc_str(json.dumps(resp)))

    async def _ping(self, client, data, engine):
        await client.send_packet(0x01, data)

    async def _login_start(self, client, data, engine):
        username, _ = self.dec_str(data)
        client.username = username
        uid = uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + username)
        await client.send_packet(0x02, self.enc_uuid_str(uid) + self.enc_str(username))
        client.protocol_state = "PLAY"
        print(f"[1.12.2] {username} PLAY uid={uid}")

        await self._send_join_game(client)
        await self._send_server_difficulty(client)
        await self._send_server_brand(client)
        await self._send_spawn_position(client)
        await self._send_player_abilities(client)
        await self._send_time_update(client)
        await self._send_player_pos_look(client)
        await self._send_player_info(client, uid)
        await self._send_chunk(client, engine)

        if engine.network_manager:
            engine.network_manager.start_keep_alive(client)

    # ── Join Game 0x23 ─────────────────────────────────────────────────────
    # wiki.vg/index.php?title=Protocol&oldid=13223 (proto 340):
    #   Int EID | UByte Gamemode | Int Dimension | UByte Difficulty
    #   | UByte MaxPlayers | String LevelType | Bool ReducedDebug
    # NOTE: Difficulty IS still in 1.12.2 Join Game (removed in 1.20.2).
    #       The separate Server Difficulty packet (0x0D) is also sent.
    async def _send_join_game(self, client):
        data  = struct.pack(">i", 1)       # entity id
        data += struct.pack(">B", 0)       # gamemode: survival
        data += struct.pack(">i", 0)       # dimension: overworld (Int32 in 1.12)
        data += struct.pack(">B", 2)       # difficulty: normal
        data += struct.pack(">B", 20)      # max players
        data += self.enc_str("default")    # level type
        data += b'\x00'                    # reduced debug info
        await client.send_packet(0x23, data)

    # ── Server Difficulty 0x0D ─────────────────────────────────────────────
    # 1.12.2 adds a second field: Bool locked (new in 1.12)
    async def _send_server_difficulty(self, client):
        data  = struct.pack(">B", 2)  # difficulty: normal
        data += b'\x00'               # locked: false
        await client.send_packet(0x0D, data)

    # ── Plugin Message (server brand) 0x18 ────────────────────────────────
    # Packet ID in 1.12.2 is 0x18, NOT 0x19
    async def _send_server_brand(self, client):
        data  = self.enc_str("MC|Brand")
        data += self.enc_str("Pygnosis")
        await client.send_packet(0x18, data)

    # ── Spawn Position 0x46 ────────────────────────────────────────────────
    # 0x46 is correct for 1.12.2. (0x43 = Set Passengers, NOT Spawn Position)
    async def _send_spawn_position(self, client):
        x, y, z = 0, 64, 0
        pos = ((x & 0x3FFFFFF) << 38) | ((y & 0xFFF) << 26) | (z & 0x3FFFFFF)
        await client.send_packet(0x46, struct.pack(">Q", pos))

    # ── Player Abilities 0x2C ──────────────────────────────────────────────
    async def _send_player_abilities(self, client):
        await client.send_packet(0x2C,
            struct.pack(">b", 0) + struct.pack(">ff", 0.05, 0.1))

    # ── Time Update 0x47 ───────────────────────────────────────────────────
    # 0x47 is correct for 1.12.2. (0x44=Teams, 0x4E=Advancements — both wrong)
    async def _send_time_update(self, client):
        await client.send_packet(0x47, struct.pack(">qq", 0, 6000))

    # ── Player Position and Look 0x2F ──────────────────────────────────────
    # X Y Z (double) | Yaw Pitch (float) | Flags (byte) | TeleportID (VarInt)
    async def _send_player_pos_look(self, client):
        data  = struct.pack(">ddd", 0.0, 65.0, 0.0)
        data += struct.pack(">ff", 0.0, 0.0)
        data += b'\x00'          # flags: all absolute
        data += encode_varint(1) # teleport id
        await client.send_packet(0x2F, data)

    # ── Player Info 0x2E ───────────────────────────────────────────────────
    async def _send_player_info(self, client, uid: uuid.UUID):
        header  = encode_varint(0) + encode_varint(1)   # action=add, count=1
        entry   = self.enc_uuid_bytes(uid)
        entry  += self.enc_str(client.username)
        entry  += encode_varint(0)   # no properties
        entry  += encode_varint(0)   # gamemode: survival
        entry  += encode_varint(0)   # ping: 0
        entry  += b'\x00'            # no display name
        await client.send_packet(0x2E, header + entry)

    # ── Chunk Data 0x20 ────────────────────────────────────────────────────
    # 1.12.2 layout:
    #   int32   chunkX | int32 chunkZ | bool continuous
    #   VarInt  primaryBitMask | VarInt dataLength
    #   byte[]  data (sections, then biomes) | VarInt blockEntityCount (0)
    #
    # ChunkSection:
    #   uint16 blockCount | uint8 bitsPerBlock
    #   VarInt paletteLen | VarInt[] palette
    #   VarInt dataArrayLen | int64[] dataArray  (LSB-first packed)
    #
    # After all sections: block light (2048) + sky light (2048) + biomes (256)
    async def _send_chunk(self, client, engine):
        chunk = engine.graph.get("chunk_0_0")
        if not chunk:
            return
        raw = self._encode_chunk_1_12(chunk)
        await client.send_packet(0x20, raw)
        print(f"[1.12.2] chunk sent ({len(raw)} bytes)")
        chunk.update_coherence(0.2, "chunk sent to client")

    def _encode_chunk_1_12(self, chunk) -> bytes:
        SECTION = 3    # y=48..63; stone at local_y=12 (world y=60)
        bits    = 4
        palette = [0, 1]   # air=0, stone=1
        longs_count = (4096 * bits + 63) // 64   # = 256

        packed = bytearray(longs_count * 8)
        block_count = 0

        for lx in range(16):
            for lz in range(16):
                local_y   = 12   # 60 - SECTION*16
                block_idx = local_y * 256 + lz * 16 + lx
                pal_idx   = 1    # stone

                bit_offset = block_idx * bits
                long_idx   = bit_offset >> 6
                bit_start  = bit_offset & 63

                # LSB-first packing: read and write as little-endian
                val  = int.from_bytes(packed[long_idx*8: long_idx*8+8], "little")
                val |= (pal_idx & 0xF) << bit_start
                packed[long_idx*8: long_idx*8+8] = val.to_bytes(8, "little")
                block_count += 1

        section  = struct.pack(">H", block_count)
        section += bytes([bits])
        section += encode_varint(len(palette))
        for pid in palette:
            section += encode_varint(pid)
        section += encode_varint(longs_count)
        section += bytes(packed)

        # Light + biomes appended after all sections
        block_light = bytes([0xFF] * 2048)
        sky_light   = bytes([0xFF] * 2048)
        biomes      = bytes([1] * 256)

        full_data   = bytes(section) + block_light + sky_light + biomes

        payload  = struct.pack(">i", chunk.cx)
        payload += struct.pack(">i", chunk.cz)
        payload += b'\x01'
        payload += encode_varint(1 << SECTION)
        payload += encode_varint(len(full_data))
        payload += full_data
        payload += encode_varint(0)   # no block entities
        return payload

    # ── serverbound ────────────────────────────────────────────────────────
    async def _teleport_confirm(self, client, data, engine):
        pass  # consume teleport confirm; could validate tid

    async def _keep_alive_resp(self, client, data, engine):
        if len(data) >= 8:
            ka_id = int.from_bytes(data[:8], "big")
            if ka_id == client.last_keep_alive_id:
                client.keep_alive_pending = False

    async def _chat_recv(self, client, data, engine):
        msg, _ = self.dec_str(data)
        print(f"[1.12.2] chat {client.username}: {msg}")
        if engine.network_manager:
            pkt = b'\x00' + self.enc_str(json.dumps({"text": f"<{client.username}> {msg}"})) + b'\x00'
            await engine.network_manager.broadcast_packet(0x0D, pkt)

    async def _pos_recv(self, client, data, engine):
        if len(data) >= 24:
            _update_pos(client, engine, *struct.unpack(">ddd", data[:24]))

    async def _pos_look_recv(self, client, data, engine):
        if len(data) >= 24:
            _update_pos(client, engine, *struct.unpack(">ddd", data[:24]))

    async def _client_settings(self, client, data, engine):
        locale, off = self.dec_str(data)
        print(f"[1.12.2] {client.username} settings locale={locale}")

    async def _plugin_msg(self, client, data, engine):
        channel, _ = self.dec_str(data)
        print(f"[1.12.2] {client.username} plugin channel={channel}")


# ─────────────────────────────────────────────────────────────────────────────
def _update_pos(client, engine, x: float, y: float, z: float):
    player = engine.graph.get(f"player_{client.username}")
    if player:
        player.move_to((x, y, z))


_handlers: Dict[int, ProtocolHandler] = {
    PROTO_1_8:  Protocol_1_8(),
    PROTO_1_12: Protocol_1_12(),
}

def _get_handler(proto: int) -> ProtocolHandler:
    return _handlers.get(proto, _handlers[PROTO_1_8])
