# network.py
import asyncio
import heapq
import time
import json
import os
import uuid
import random
import struct
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from protocol import ProtocolHandler

from core import CorrelationOperator, CorrelationGraphManager, _total_coherence, adjust_global_coherence

# --- PacketOperator for network coherence ---
class PacketOperator(CorrelationOperator):
    def __init__(self, ptype: str, payload: bytes, src: str):
        super().__init__(ptype, initial_ci=0.2)
        self.src = src
        self.payload_len = len(payload)
        self.update_coherence(0.05 * len(payload) / 1024, "packet received")

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
    keep_alive_interval: float = 20.0  # seconds
    _closed: bool = False

    async def send_packet(self, packet_id: int, data: bytes):
        if self._closed:
            return
        payload = bytes([packet_id]) + data
        length = encode_varint(len(payload))
        full_data = length + payload
        self.transport.write(full_data)

    async def close(self):
        if self._closed:
            return
        self._closed = True
        if self.keep_alive_task:
            self.keep_alive_task.cancel()
            self.keep_alive_task = None
        self.transport.close()

class NetworkManager:
    def __init__(self, engine, config_path: str):
        self.engine = engine
        self.config = json.load(open(config_path)) if os.path.exists(config_path) else {}
        self.clients: Dict[str, ClientConnection] = {}
        self.packet_graph = CorrelationGraphManager()
        self.server = None
        self.read_timeout = self.config.get("read_timeout", 30.0)  # seconds

    async def start(self, host: str, port: int):
        self.server = await asyncio.start_server(self.handle_client, host, port)
        print(f"🌍 NetworkManager listening on {host}:{port}")

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        from protocol import HandshakeHandler

        client_id = str(uuid.uuid4())
        transport = writer.transport
        client = ClientConnection(
            client_id=client_id,
            transport=transport,
            handler=HandshakeHandler()
        )
        self.clients[client_id] = client
        print(f"🔌 Client {client_id} connected")

        try:
            while True:
                await self._process_client_data(client, reader)
        except asyncio.CancelledError:
            pass
        except (ConnectionResetError, BrokenPipeError, asyncio.IncompleteReadError):
            print(f"🔌 Client {client_id} connection lost")
        except Exception as e:
            import traceback
            print(f"🔥 Unexpected error for client {client_id}: {e}")
            traceback.print_exc()
        finally:
            await client.close()
            if client_id in self.clients:
                del self.clients[client_id]
            print(f"🔌 Client {client_id} disconnected")

    async def _process_client_data(self, client: ClientConnection, reader: asyncio.StreamReader):
        # Read packet length (VarInt) with timeout
        try:
            # First byte with timeout
            len_data = await asyncio.wait_for(reader.readexactly(1), timeout=self.read_timeout)
        except asyncio.TimeoutError:
            print(f"⏰ Client {client.client_id} read timeout (no data for {self.read_timeout}s)")
            raise asyncio.CancelledError  # trigger disconnect

        byte = len_data[0]
        length = byte & 0x7F
        bytes_needed = 1
        while byte & 0x80:
            # Read next byte
            try:
                len_data = await asyncio.wait_for(reader.readexactly(1), timeout=5.0)
            except asyncio.TimeoutError:
                print(f"⏰ Client {client.client_id} read timeout during varint")
                raise asyncio.CancelledError
            byte = len_data[0]
            length = (length << 7) | (byte & 0x7F)
            bytes_needed += 1
            if bytes_needed > 5:
                raise ValueError("VarInt too long (possible attack)")

        # Read full packet payload
        try:
            payload = await asyncio.wait_for(reader.readexactly(length), timeout=5.0)
        except asyncio.TimeoutError:
            print(f"⏰ Client {client.client_id} read timeout for payload")
            raise asyncio.CancelledError

        packet_id = payload[0]
        packet_payload = payload[1:]

        # PacketOperator for coherence tracking
        pkt_op = PacketOperator(f"0x{packet_id:02x}", packet_payload, client.client_id)
        self.packet_graph.add(pkt_op)

        # Dispatch using current handler
        if client.handler:
            await client.handler.handle_packet(client, packet_id, packet_payload, self.engine)
        else:
            print(f"⚠️ No handler for client {client.client_id}")

    def start_keep_alive(self, client: ClientConnection):
        """Start the keep-alive loop for a client that has entered PLAY state."""
        if client.keep_alive_task is not None:
            client.keep_alive_task.cancel()
        client.keep_alive_task = asyncio.create_task(self._keep_alive_loop(client))

    async def _keep_alive_loop(self, client: ClientConnection):
        """Send keep-alive packets periodically and check for response."""
        try:
            while not client._closed and client.protocol_state == "PLAY" and client.client_id in self.clients:
                # Wait before sending next keep-alive
                await asyncio.sleep(client.keep_alive_interval)

                if client._closed:
                    break

                # Generate a random keep-alive ID
                keep_alive_id = random.getrandbits(64)
                client.last_keep_alive_id = keep_alive_id
                client.keep_alive_pending = True

                # Send keep-alive packet (0x20 in PLAY state for 1.14)
                await client.send_packet(0x20, struct.pack('>Q', keep_alive_id))

                # Wait for response (timeout half the interval)
                for _ in range(int(client.keep_alive_interval * 10)):  # check every 0.1s
                    await asyncio.sleep(0.1)
                    if not client.keep_alive_pending or client._closed:
                        break
                else:
                    # No response – disconnect client
                    print(f"⚠️ Client {client.username or client.client_id} timed out (keep-alive)")
                    await client.close()
                    break
        except asyncio.CancelledError:
            pass

    def _check_paradox(self, client: ClientConnection) -> bool:
        # Placeholder
        return False

    async def _reconcile_client(self, client: ClientConnection):
        pass

    async def _autopilot_loop(self):
        golden = self.config.get("autopoietic", {}).get("golden_ratio", 1.618)
        interval = self.config.get("autopoietic", {}).get("tune_interval", 30)
        while True:
            await asyncio.sleep(interval)
            metrics = self._collect_metrics()
            print(f"⚙️ Autopoietic tuning: metrics {metrics}")

    def _collect_metrics(self) -> dict:
        return {"rtt": 50, "loss": 0.01, "throughput": 1000}

    async def broadcast_packet(self, packet_id: int, data: bytes, exclude=None):
        for cid, client in self.clients.items():
            if cid != exclude and not client._closed:
                await client.send_packet(packet_id, data)

    def get_updates_for_client(self, client_id: str, max_bytes: int) -> List[bytes]:
        # TODO: implement entity tracking and delta compression
        return []

# --- VarInt helpers ---
def encode_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)

def decode_varint(buf: bytes, offset: int = 0) -> tuple:
    value = 0
    shift = 0
    pos = offset
    while True:
        if pos >= len(buf):
            raise ValueError("Incomplete varint")
        b = buf[pos]
        value |= (b & 0x7F) << shift
        pos += 1
        if not (b & 0x80):
            break
        shift += 7
        if shift > 35:
            raise ValueError("Varint too long")
    return value, pos - offset
