# network.py
import asyncio
import heapq
import time
import json
import os
import uuid
import random
import struct
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protocol import ProtocolHandler

from core import CorrelationOperator, CorrelationGraphManager, _total_coherence, adjust_global_coherence


# ─────────────────────────────────────────────────────────────────────────────
# PacketOperator — lightweight coherence node per received packet
# ─────────────────────────────────────────────────────────────────────────────
class PacketOperator(CorrelationOperator):
    def __init__(self, ptype: str, payload: bytes, src: str):
        super().__init__(ptype, initial_ci=0.2)
        self.src = src
        self.payload_len = len(payload)
        self.update_coherence(0.05 * len(payload) / 1024, "packet received")


# ─────────────────────────────────────────────────────────────────────────────
# ClientConnection
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ClientConnection:
    client_id: str
    transport: asyncio.Transport
    protocol_state: str = "HANDSHAKE"
    protocol_version: int = -1
    handler: Optional['ProtocolHandler'] = None
    username: Optional[str] = None
    keep_alive_pending: bool = False
    last_keep_alive_id: int = 0
    keep_alive_task: Optional[asyncio.Task] = None
    keep_alive_interval: float = 15.0   # seconds — 15s is safe for all versions
    _closed: bool = False

    async def send_packet(self, packet_id: int, data: bytes):
        if self._closed:
            return
        try:
            payload    = bytes([packet_id]) + data
            length     = encode_varint(len(payload))
            self.transport.write(length + payload)
        except Exception as e:
            print(f"⚠️  send_packet error pid=0x{packet_id:02x}: {e}")
            await self.close()

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            self.keep_alive_task = None
        try:
            self.transport.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# NetworkManager
# ─────────────────────────────────────────────────────────────────────────────
class NetworkManager:
    def __init__(self, engine, config_path: str):
        self.engine       = engine
        self.config       = json.load(open(config_path)) if os.path.exists(config_path) else {}
        self.clients: Dict[str, ClientConnection] = {}
        self.packet_graph = CorrelationGraphManager()
        self.server       = None
        self.read_timeout = self.config.get("read_timeout", 30.0)

    async def start(self, host: str, port: int):
        self.server = await asyncio.start_server(self.handle_client, host, port)
        print(f"🌍 NetworkManager listening on {host}:{port}")

    # ── per-client coroutine ──────────────────────────────────────────────────
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        from protocol import HandshakeHandler

        client_id = str(uuid.uuid4())
        client = ClientConnection(
            client_id  = client_id,
            transport  = writer.transport,
            handler    = HandshakeHandler(),
        )
        self.clients[client_id] = client
        print(f"🔌 Client {client_id[:8]} connected from {writer.get_extra_info('peername')}")

        try:
            while not client._closed:
                await self._read_one_packet(client, reader)
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            print(f"🔌 Client {client_id[:8]} ({client.username or 'unknown'}) connection lost")
        except Exception as e:
            import traceback
            print(f"🔥 Client {client_id[:8]} unexpected error: {e}")
            traceback.print_exc()
        finally:
            await client.close()
            self.clients.pop(client_id, None)
            print(f"🔌 Client {client_id[:8]} ({client.username or 'unknown'}) disconnected")

    # ── packet reader ─────────────────────────────────────────────────────────
    async def _read_one_packet(self, client: ClientConnection, reader: asyncio.StreamReader):
        # --- read VarInt length ---
        length    = 0
        shift     = 0
        num_bytes = 0
        while True:
            try:
                b = (await asyncio.wait_for(reader.readexactly(1), timeout=self.read_timeout))[0]
            except asyncio.TimeoutError:
                print(f"⏰ Client {client.client_id[:8]} timed out waiting for data")
                raise asyncio.CancelledError
            length |= (b & 0x7F) << shift
            shift  += 7
            num_bytes += 1
            if not (b & 0x80):
                break
            if num_bytes > 5:
                raise ValueError("VarInt too long — possible attack or garbage data")

        if length == 0:
            return   # empty packet — ignore

        # --- read payload ---
        try:
            payload = await asyncio.wait_for(reader.readexactly(length), timeout=10.0)
        except asyncio.TimeoutError:
            print(f"⏰ Client {client.client_id[:8]} timed out reading payload ({length} bytes)")
            raise asyncio.CancelledError

        packet_id      = payload[0]
        packet_payload = payload[1:]

        # coherence tracking
        pkt_op = PacketOperator(f"0x{packet_id:02x}", packet_payload, client.client_id)
        self.packet_graph.add(pkt_op)

        if client.handler:
            await client.handler.handle_packet(client, packet_id, packet_payload, self.engine)
        else:
            print(f"⚠️  No handler for client {client.client_id[:8]}")

    # ── keep-alive ────────────────────────────────────────────────────────────
    def start_keep_alive(self, client: ClientConnection):
        if client.keep_alive_task is not None:
            client.keep_alive_task.cancel()
        client.keep_alive_task = asyncio.create_task(self._keep_alive_loop(client))

    async def _keep_alive_loop(self, client: ClientConnection):
        """
        Version-aware keep-alive sender.

        1.8.9  → packet 0x00, ID as VarInt
        1.12.2 → packet 0x1F, ID as int64 big-endian

        The handler class exposes:
            keep_alive_packet_id  : int
            keep_alive_id_encoder : callable(int) -> bytes
        """
        try:
            while not client._closed and client.protocol_state == "PLAY":
                await asyncio.sleep(client.keep_alive_interval)
                if client._closed:
                    break

                handler = client.handler
                if handler is None:
                    break

                ka_id   = random.getrandbits(32)         # 32-bit fits both versions
                client.last_keep_alive_id  = ka_id
                client.keep_alive_pending  = True

                ka_pid     = getattr(handler, "keep_alive_packet_id",  0x1F)
                ka_encoder = getattr(handler, "keep_alive_id_encoder", lambda i: struct.pack(">q", i))

                await client.send_packet(ka_pid, ka_encoder(ka_id))

                # wait up to half the interval for a response
                deadline = asyncio.get_event_loop().time() + client.keep_alive_interval / 2
                while asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(0.2)
                    if not client.keep_alive_pending or client._closed:
                        break
                else:
                    print(f"⚠️  {client.username or client.client_id[:8]} keep-alive timeout — disconnecting")
                    await client.close()
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"🔥 keep-alive error for {client.username}: {e}")

    # ── broadcast ─────────────────────────────────────────────────────────────
    async def broadcast_packet(self, packet_id: int, data: bytes, exclude=None):
        for cid, client in list(self.clients.items()):
            if cid != exclude and not client._closed:
                await client.send_packet(packet_id, data)

    def get_updates_for_client(self, client_id: str, max_bytes: int) -> List[bytes]:
        # TODO: delta compression + entity tracking
        return []


# ─────────────────────────────────────────────────────────────────────────────
# VarInt helpers
# ─────────────────────────────────────────────────────────────────────────────
def encode_varint(value: int) -> bytes:
    out = bytearray()
    value &= 0xFFFFFFFF          # treat as unsigned 32-bit
    while True:
        byte   = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def decode_varint(buf: bytes, offset: int = 0) -> tuple:
    """Returns (value, bytes_consumed)."""
    value = 0
    shift = 0
    pos   = offset
    while True:
        if pos >= len(buf):
            raise ValueError(f"Incomplete VarInt at offset {offset}")
        b      = buf[pos]
        value |= (b & 0x7F) << shift
        pos   += 1
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            raise ValueError("VarInt too long")
    return value, pos - offset
