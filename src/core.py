# core.py
import asyncio
import heapq
import random
import uuid
import json
from typing import Dict, Set, Optional, Any, List, Callable

# Global coherence budget (H₁₃ conservation)
_total_coherence = 0.0
_total_coherence_target = 1000.0  # arbitrary, can be adjusted

# Quiet mode: suppress routine decay messages
QUIET_DECAY = True
ROUTINE_REASONS = {"natural decay", "remote event"}

def adjust_global_coherence(delta: float):
    global _total_coherence
    _total_coherence = max(0.0, _total_coherence + delta)
    # Could trigger load balancing (H₁₄) if needed

def semantic_distance(type_a: str, type_b: str) -> float:
    return 0.0 if type_a == type_b else 0.5

class CorrelationOperator:
    """Base class with visual attributes and lazy evaluation."""
    def __init__(self, op_type: str, oid: str = None, initial_ci: float = 0.5):
        self.type = op_type
        self.id = oid or str(uuid.uuid4())
        self.coherence = max(0.0, min(1.0, initial_ci))
        self.state: dict = {}
        self.edges: Set[str] = set()
        self.active = self.coherence > 0.3

        # Visual attributes (computed lazily)
        self._mers = {"metalness": 0.0, "emissive": 0.0, "roughness": 0.5, "subsurface": 0.0}
        self._animation_params = {"speed": 1.0, "amplitude": 0.0, "phase": 0.0}
        self._lod_bias = 0.0
        self._dirty_visuals = True   # marks that visual attributes need recomputation

        # Register global coherence change
        adjust_global_coherence(initial_ci)

    def update_coherence(self, delta: float, reason: str = "", sigma_topo: float = 0.0):
        """Update coherence with a topological term (sigma_topo) that can add extra.
           The total change is delta + sigma_topo, but sigma_topo is drawn from global budget."""
        global _total_coherence
        old = self.coherence
        # sigma_topo must be taken from global budget if positive, or returned if negative
        if sigma_topo > 0:
            # ensure we have enough global coherence
            available = _total_coherence - _total_coherence_target
            sigma_topo = min(sigma_topo, max(0, available))
        elif sigma_topo < 0:
            # returning coherence to global pool
            pass
        total_delta = delta + sigma_topo
        new_ci = max(0.0, min(1.0, self.coherence + total_delta))
        actual_delta = new_ci - self.coherence
        self.coherence = new_ci
        self.active = self.coherence > 0.3
        # Update global coherence
        adjust_global_coherence(actual_delta)
        # Only print if change is significant or reason is not routine
        if abs(actual_delta) > 0.05 or (QUIET_DECAY and reason not in ROUTINE_REASONS):
            print(f" {self.id[:12]:<12} CI {old:.2f} → {self.coherence:.2f} ({reason})")
        self._dirty_visuals = True

    def mark_visuals_dirty(self):
        self._dirty_visuals = True

    def update_visuals(self):
        """Recompute visual attributes from current coherence. To be overridden."""
        # Base mapping
        self._mers["emissive"] = min(1.0, self.coherence * 0.8)
        self._mers["roughness"] = max(0.1, 1.0 - self.coherence * 0.7)
        self._animation_params["amplitude"] = self.coherence * 0.5
        self._animation_params["speed"] = 0.8 + self.coherence * 0.4
        self._lod_bias = (self.coherence - 0.5) * 2.0
        self._dirty_visuals = False

    def ensure_visuals(self):
        if self._dirty_visuals:
            self.update_visuals()

    @property
    def mers(self):
        self.ensure_visuals()
        return self._mers

    @property
    def animation_params(self):
        self.ensure_visuals()
        return self._animation_params

    @property
    def lod_bias(self):
        self.ensure_visuals()
        return self._lod_bias

    def to_network_dict(self) -> Dict[str, Any]:
        self.ensure_visuals()
        return {
            "id": self.id,
            "type": self.type,
            "coherence": self.coherence,
            "mers": self._mers.copy(),
            "anim": self._animation_params.copy(),
            "lod_bias": self._lod_bias,
        }


# Registry of block types and their structure constants (commutators)
# Format: (dx, dy, dz) -> (target_block_type_pattern, resulting_action)
# For simplicity, we define a sparse structure.
_block_interactions = {
    # stone (id 1) can be broken by player (special case, handled via events)
    # redstone wire example: if adjacent redstone changes, update
    # We'll simulate with a simple rule: any block change triggers a small excitation in neighbors
}

def register_block_interaction(block_type: str, neighbor_offset: tuple, target_type: str, action: Callable):
    """Register a rule for commutator [block, neighbor]."""
    key = (block_type, neighbor_offset)
    _block_interactions[key] = (target_type, action)


class CorrelationGraphManager:
    def __init__(self):
        self.operators: Dict[str, CorrelationOperator] = {}
        self.excited = []  # priority queue (-ci, id)

    def add(self, op: CorrelationOperator):
        self.operators[op.id] = op
        if op.active:
            heapq.heappush(self.excited, (-op.coherence, op.id))

    def get(self, oid: str) -> Optional[CorrelationOperator]:
        return self.operators.get(oid)

    def apply_commutator(self, id1: str, id2: str, strength: float = 0.25, sigma_topo: float = 0.0):
        """Apply a commutator between two operators, possibly using structure constants."""
        o1 = self.operators.get(id1)
        o2 = self.operators.get(id2)
        if not o1 or not o2:
            return
        # Basic interaction: both gain/lose coherence
        delta = strength * (o1.coherence + o2.coherence) / 2
        o1.update_coherence(delta * 0.6, f"comm with {id2}", sigma_topo=sigma_topo*0.6)
        o2.update_coherence(delta * 0.6, f"comm with {id1}", sigma_topo=sigma_topo*0.6)
        o1.edges.add(id2)
        o2.edges.add(id1)
        if o1.active:
            heapq.heappush(self.excited, (-o1.coherence, o1.id))
        if o2.active:
            heapq.heappush(self.excited, (-o2.coherence, o2.id))

    def propagate(self, max_steps: int = 8):
        """Propagate excitement through the graph."""
        steps = 0
        seen = set()
        while self.excited and steps < max_steps:
            _, oid = heapq.heappop(self.excited)
            if oid in seen:
                continue
            seen.add(oid)
            op = self.operators.get(oid)
            if op:
                for n in list(op.edges):
                    # Use structure constants if available for specific types
                    # Here we just apply a small commutator with random chance
                    if random.random() < 0.4:
                        self.apply_commutator(oid, n, 0.09)
            steps += 1


class CoherenceScheduler:
    def __init__(self, graph: CorrelationGraphManager, engine=None):
        self.graph = graph
        self.engine = engine  # reference to physics engine for network callbacks

    async def tick(self):
        """One simulation tick: decay, remote events, then propagate."""
        for op in list(self.graph.operators.values()):
            if op.active:
                op.update_coherence(-0.012, "natural decay")
            elif random.random() < 0.03:
                op.update_coherence(0.08, "remote event")
        self.graph.propagate()

        # After simulation, trigger network updates if engine has network manager
        if self.engine and self.engine.network_manager:
            # For each client, generate and send updates
            for client_id, client in self.engine.network_manager.clients.items():
                updates = self.engine.network_manager.get_updates_for_client(client_id, 1024)
                # In real implementation, updates would be packets; for now just log
                if updates:
                    pass  # we'll trust network manager to handle sending


class PhysicsEngine:
    def __init__(self):
        self.graph = CorrelationGraphManager()
        self.scheduler = CoherenceScheduler(self.graph, engine=self)
        self.running = False
        self.tick_rate = 20
        # Boundary store: simple dict mapping chunk_id to compressed data (bytes)
        self.boundary_store = {}
        # Network manager (set by main after creation)
        self.network_manager = None

    async def start(self):
        self.running = True
        print("🚀 PhysicsEngine started (20 tps)")
        while self.running:
            start = asyncio.get_running_loop().time()
            await self.scheduler.tick()
            elapsed = asyncio.get_running_loop().time() - start
            await asyncio.sleep(max(0, 1 / self.tick_rate - elapsed))

    def stop(self):
        self.running = False
