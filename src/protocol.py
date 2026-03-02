# protocol.py
import asyncio
import uuid
import json
import struct
import random
from typing import Dict, Optional
from network import encode_varint, decode_varint, ClientConnection

# Protocol version ranges
SUPPORTED_VERSIONS = {
    "1.14": (477, 498),      # 1.14 – 1.14.4
}

class ProtocolHandler:
    """Base class for Minecraft protocol versions."""
    def __init__(self, version: str):
        self.version = version
        self.handshake_handler = None
        self.login_packets = {}
        self.play_packets = {}
        self.status_packets = {}

    async def handle_packet(self, client: ClientConnection, packet_id: int, payload: bytes, engine):
        try:
            if client.protocol_state == "HANDSHAKE":
                if self.handshake_handler:
                    await self.handshake_handler(client, payload, engine)
                else:
                    print(f"⚠️ No handshake handler for {self.version}")
            elif client.protocol_state == "LOGIN":
                handler = self.login_packets.get(packet_id)
                if handler:
                    await handler(client, payload, engine)
                else:
                    print(f"⚠️ Unhandled login packet 0x{packet_id:02x}")
            elif client.protocol_state == "PLAY":
                handler = self.play_packets.get(packet_id)
                if handler:
                    await handler(client, payload, engine)
                else:
                    print(f"⚠️ Unhandled play packet 0x{packet_id:02x}")
            elif client.protocol_state == "STATUS":
                handler = self.status_packets.get(packet_id)
                if handler:
                    await handler(client, payload, engine)
                else:
                    print(f"⚠️ Unhandled status packet 0x{packet_id:02x}")
        except Exception as e:
            print(f"🔥 Error in packet handler for {client}: {e}")
            await client.close()

    def encode_string(self, s: str) -> bytes:
        data = s.encode('utf-8')
        return encode_varint(len(data)) + data

    def decode_string(self, payload: bytes, offset: int = 0) -> tuple:
        length, consumed = decode_varint(payload, offset)
        return payload[consumed:consumed + length].decode('utf-8'), consumed + length

    def encode_uuid(self, uid: uuid.UUID) -> bytes:
        return struct.pack('>QQ', uid.int >> 64, uid.int & 0xFFFFFFFFFFFFFFFF)


class Protocol_1_14(ProtocolHandler):
    def __init__(self):
        super().__init__("1.14")
        self.handshake_handler = self.handle_handshake
        self.login_packets = {
            0x00: self.handle_login_start,
        }
        # Corrected serverbound packet IDs for 1.14 (wiki.vg)
        self.play_packets = {
            0x00: self.handle_teleport_confirm,      # Teleport Confirm
            0x03: self.handle_chat_message,          # Chat Message
            0x05: self.handle_client_settings,       # Client Settings
            0x0B: self.handle_plugin_message,        # Plugin Message
            0x10: self.handle_keep_alive_response,   # Keep Alive
            0x12: self.handle_player_position,       # Player Position
        }
        self.status_packets = {
            0x00: self.handle_status_request,
            0x01: self.handle_ping_request,
        }

    async def handle_handshake(self, client: ClientConnection, payload: bytes, engine):
        # Handled by HandshakeHandler
        pass

    async def handle_login_start(self, client: ClientConnection, payload: bytes, engine):
        username, _ = self.decode_string(payload)
        client.username = username
        # Use OfflinePlayer: prefix for offline UUIDs (like vanilla)
        uid = uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + username)
        data = self.encode_uuid(uid) + self.encode_string(username)
        await client.send_packet(0x02, data)          # Login success
        client.protocol_state = "PLAY"
        print(f"✅ {username} logged in as {uid}")

        # Send Join Game FIRST (mandatory)
        await self.send_join_game(client, engine)

        # Then all other essential packets
        await self.send_server_difficulty(client, engine)
        await self.send_spawn_position(client, engine)
        await self.send_player_position_look(client, engine)
        await self.send_update_view_position(client, engine)
        await self.send_player_abilities(client, engine)
        await self.send_time_update(client, engine)
        await self.send_player_info(client, engine)   # optional, but nice

        # Start keep-alive loop
        if engine.network_manager:
            engine.network_manager.start_keep_alive(client)

        # Send initial chunk
        chunk = engine.graph.get("chunk_0_0")
        if chunk:
            chunk_data = self.encode_chunk(chunk)
            await client.send_packet(0x21, chunk_data)   # Chunk Data = 0x21
            print(f"📦 Sent initial chunk data ({len(chunk_data)} bytes)")
            chunk.update_coherence(0.2, "chunk sent to client", sigma_topo=0.3)

            # Send Update Light packet (mandatory in 1.14)
            await self.send_update_light(client, chunk.cx, chunk.cz)

    async def send_player_info(self, client: ClientConnection, engine):
        """Send Player Info packet (0x33) – add player action."""
        # For now, only send info about this player. In a full implementation,
        # you would also send info about all online players to this client.
        data = encode_varint(0)                        # action: add player
        data += encode_varint(1)                       # number of players
        uid = uuid.uuid3(uuid.NAMESPACE_DNS, "OfflinePlayer:" + client.username)
        data += self.encode_uuid(uid)                  # player UUID
        data += self.encode_string(client.username)    # player name
        data += encode_varint(0)                       # number of properties (no skin)
        data += encode_varint(0)                       # gamemode (survival)
        data += encode_varint(0)                        # ping (0 ms)
        data += b'\x00'                                  # has display name? false
        await client.send_packet(0x33, data)            # 0x33 = Player Info

    async def send_join_game(self, client: ClientConnection, engine):
        packet_id = 0x25
        data = struct.pack('>i', 1)  # entity ID
        data += b'\x00'              # gamemode (survival)
        data += struct.pack('>i', 0) # dimension (overworld)
        data += b'\x02'              # difficulty (normal)
        data += b'\x14'              # max players (20)
        data += self.encode_string("default")  # level type
        data += b'\x00'               # reduced debug info (false)
        # NO view distance field here in 1.14!
        await client.send_packet(packet_id, data)

    async def send_server_difficulty(self, client: ClientConnection, engine):
        data = b'\x02' + b'\x00'      # normal, not locked
        await client.send_packet(0x0D, data)

    async def send_spawn_position(self, client: ClientConnection, engine):
        pos = (0 << 38) | ((0 & 0x3FFFFFF) << 12) | (64 & 0xFFF)  # packed X Z Y
        data = struct.pack('>Q', pos)
        await client.send_packet(0x42, data)

    async def send_player_position_look(self, client: ClientConnection, engine):
        data = struct.pack('>dddff', 0.0, 64.0, 0.0, 0.0, 0.0)  # x y z yaw pitch
        data += b'\x00'                # flags
        data += encode_varint(0)        # teleport ID
        await client.send_packet(0x35, data)   # 0x35 = Player Position & Look

    async def send_update_view_position(self, client: ClientConnection, engine):
        data = encode_varint(0) + encode_varint(0)  # chunk X Z
        await client.send_packet(0x40, data)

    async def send_player_abilities(self, client: ClientConnection, engine):
        # Flags: 0x00 = survival, no flying, no invulnerability
        data = b'\x00'
        data += struct.pack('>ff', 0.05, 0.1)          # flying speed, FOV mod
        await client.send_packet(0x31, data)            # 0x31 = Player Abilities

    async def send_time_update(self, client: ClientConnection, engine):
        data = struct.pack('>qq', 0, 6000)             # world age, time of day
        await client.send_packet(0x4E, data)

    async def send_update_light(self, client: ClientConnection, cx: int, cz: int):
        """Send Update Light packet (0x23) – required in 1.14 for lighting."""
        packet_id = 0x23
        data = struct.pack('>i', cx)
        data += struct.pack('>i', cz)
        # Trust edges (empty)
        data += encode_varint(0)  # sky light mask (VarInt 0)
        data += encode_varint(0)  # block light mask (VarInt 0)
        # Empty arrays (implied by masks)
        await client.send_packet(packet_id, data)

    def encode_chunk(self, chunk) -> bytes:
        """Chunk Data packet for 1.14 – 4 bits per block, no lighting, correct NBT."""
        x = struct.pack('>i', chunk.cx)
        z = struct.pack('>i', chunk.cz)
        full = b'\x00'                                 # FIX: must be False when not all sections present
        bitmask = encode_varint(1)                     # Section 0 present

        # Heightmaps NBT: compound with two long arrays (36 longs each)
        long_array_len = struct.pack('>i', 36)
        longs_zero = b'\x00' * (36 * 8)

        motion_name = struct.pack('>H', 15) + b'MOTION_BLOCKING'
        world_name = struct.pack('>H', 13) + b'WORLD_SURFACE'

        long_array_tag = b'\x0C'                       # Tag 12: Long Array
        heightmaps = (b'\x0A\x00\x00' +                # Compound, empty name
                     long_array_tag + motion_name + long_array_len + longs_zero +
                     long_array_tag + world_name + long_array_len + longs_zero +
                     b'\x00')                          # End tag

        # Biomes: 256 ints (1024 bytes), all plains (1)
        biomes = struct.pack('>256i', *([1] * 256))

        # Section data: one section at Y=0 with air palette
        section = struct.pack('>h', 0)                  # block count (0 = all air)
        section += b'\x04'                               # bits per block (min 4)
        section += encode_varint(1)                      # palette length
        section += encode_varint(0)                      # air ID
        section += encode_varint(256)                    # data array length (256 longs)
        section += b'\x00' * (256 * 8)                   # data array zeros

        data_size = encode_varint(len(section))
        data = section

        # Block entities: none
        entities = encode_varint(0)

        return x + z + full + bitmask + heightmaps + biomes + data_size + data + entities

    # --- Play packet handlers ---
    async def handle_teleport_confirm(self, client: ClientConnection, payload: bytes, engine):
        """Teleport Confirm (0x00) – sent by client after Player Position & Look."""
        teleport_id, _ = decode_varint(payload)
        # Optionally verify teleport ID

    async def handle_keep_alive_response(self, client: ClientConnection, payload: bytes, engine):
        """Keep Alive response (0x10) – 8-byte long."""
        if len(payload) == 8:
            received_id = int.from_bytes(payload, 'big')
            if received_id == client.last_keep_alive_id:
                client.keep_alive_pending = False
                if client.username:
                    player = engine.graph.get(f"player_{client.username}")
                    if player:
                        player.update_coherence(0.02, "keep-alive ack")

    async def handle_client_settings(self, client: ClientConnection, payload: bytes, engine):
        offset = 0
        locale, consumed = self.decode_string(payload, offset)
        offset += consumed
        view_distance = payload[offset]
        offset += 1
        chat_mode, consumed = decode_varint(payload, offset)
        offset += consumed
        chat_colors = bool(payload[offset])
        offset += 1
        displayed_skin_parts = payload[offset]
        offset += 1
        main_hand, _ = decode_varint(payload, offset)
        print(f"⚙️ {client.username} settings: locale={locale}, view distance={view_distance}, main hand={main_hand}")

    async def handle_plugin_message(self, client: ClientConnection, payload: bytes, engine):
        channel, consumed = self.decode_string(payload)
        print(f"📨 {client.username} plugin message on channel {channel}")

    async def handle_chat_message(self, client: ClientConnection, payload: bytes, engine):
        msg = payload.decode('utf-8')
        print(f"💬 {client.username}: {msg}")
        if engine.network_manager:
            # Proper chat packet: position (0=chat) and sender UUID
            data = b'\x00' + self.encode_string(msg) + self.encode_uuid(uuid.UUID(int=0))
            await engine.network_manager.broadcast_packet(0x02, data, exclude=client.client_id)

    async def handle_player_position(self, client: ClientConnection, payload: bytes, engine):
        if len(payload) < 25:
            return
        x, y, z, on_ground = struct.unpack('>ddd?', payload[:25])
        player = engine.graph.get(f"player_{client.username}")
        if player:
            player.move_to((x, y, z))
            player.update_coherence(0.05, "client move")

    # --- Status State ---
    async def handle_status_request(self, client: ClientConnection, payload: bytes, engine):
        response = {
            "version": {"name": "Pygnosis 1.14", "protocol": 477},
            "players": {"max": 20, "online": len(engine.network_manager.clients) if engine.network_manager else 0},
            "description": {"text": "Pygnosis MOGOPS Server"}
        }
        json_str = json.dumps(response)
        data = self.encode_string(json_str)
        await client.send_packet(0x00, data)

    async def handle_ping_request(self, client: ClientConnection, payload: bytes, engine):
        await client.send_packet(0x01, payload)


class HandshakeHandler(ProtocolHandler):
    """Temporary handler for the initial handshake packet."""
    def __init__(self):
        super().__init__("handshake")
        self.handshake_handler = self.handle_handshake

    async def handle_handshake(self, client: ClientConnection, payload: bytes, engine):
        offset = 0
        protocol_version, consumed = decode_varint(payload, offset)
        offset += consumed
        address, consumed = self.decode_string(payload, offset)
        offset += consumed
        port = struct.unpack('>H', payload[offset:offset+2])[0]
        offset += 2
        next_state, _ = decode_varint(payload, offset)
        print(f"🔍 Client protocol version: {protocol_version}")
        if next_state == 1:
            client.protocol_state = "STATUS"
            client.handler = get_handler("1.14")
        elif next_state == 2:
            if protocol_version < SUPPORTED_VERSIONS["1.14"][0] or protocol_version > SUPPORTED_VERSIONS["1.14"][1]:
                print(f"⚠️ Unsupported version {protocol_version}")
                await client.close()
                return
            client.protocol_version = protocol_version
            client.handler = get_handler("1.14")
            client.protocol_state = "LOGIN"
            print(f"✅ Client {client.username or 'unknown'} using protocol {protocol_version} (1.14)")
        else:
            print(f"⚠️ Invalid next state {next_state}")
            await client.close()


_protocol_handlers = {
    "1.14": Protocol_1_14(),
}

def get_handler(version: str) -> ProtocolHandler:
    return _protocol_handlers.get(version, _protocol_handlers["1.14"])
