# core.py
import asyncio
import heapq
import random
import uuid
from typing import Dict, Set, Optional, Any, List, Callable

# Global coherence budget (H₁₃ conservation)
_total_coherence = 0.0
_total_coherence_target = 1000.0

# Quiet mode: suppress routine decay messages
QUIET_DECAY = True
ROUTINE_REASONS = {"natural decay", "remote event"}

def adjust_global_coherence(delta: float):
    global _total_coherence
    _total_coherence = max(0.0, _total_coherence + delta)

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
        self._dirty_visuals = True

        adjust_global_coherence(initial_ci)

    def update_coherence(self, delta: float, reason: str = "", sigma_topo: float = 0.0):
        global _total_coherence
        old = self.coherence
        if sigma_topo > 0:
            available = _total_coherence - _total_coherence_target
            sigma_topo = min(sigma_topo, max(0, available))
        self.coherence = max(0.0, min(1.0, self.coherence + delta + sigma_topo))
        adjust_global_coherence(self.coherence - old)
        if reason != "natural decay" and (not QUIET_DECAY or reason not in ROUTINE_REASONS):
            print(f" {self.id[:12]} CI {old:.2f} → {self.coherence:.2f} ({reason})")
        self.active = self.coherence > 0.3
        self.mark_visuals_dirty()

    def mark_visuals_dirty(self):
        self._dirty_visuals = True

    def update_visuals(self):
        if not self._dirty_visuals:
            return
        self._mers["emissive"] = self.coherence * 0.8
        self._mers["roughness"] = 1.0 - self.coherence * 0.7
        self._animation_params["speed"] = 1.0 + self.coherence * 0.5
        self._animation_params["amplitude"] = self.coherence * 0.5
        self._lod_bias = -1.0 + self.coherence * 2.0
        self._dirty_visuals = False

    def to_network_dict(self) -> dict:
        self.update_visuals()
        return {
            "id": self.id,
            "type": self.type,
            "coherence": self.coherence,
            "mers": self._mers,
            "anim": self._animation_params,
            "lod_bias": self._lod_bias,
            "active": self.active,
        }

class CorrelationGraphManager:
    def __init__(self):
        self.operators: Dict[str, CorrelationOperator] = {}
        self.excited: List[tuple] = []  # min-heap (-coherence, oid)

    def add(self, op: CorrelationOperator, edges: List[str] = None):
        if op.id in self.operators:
            return
        self.operators[op.id] = op
        if edges:
            for e in edges:
                op.edges.add(e)
                if e in self.operators:
                    self.operators[e].edges.add(op.id)

    def remove(self, oid: str):
        if oid not in self.operators:
            return
        op = self.operators.pop(oid)
        adjust_global_coherence(-op.coherence)
        for n in op.edges:
            if n in self.operators:
                self.operators[n].edges.discard(oid)

    def get(self, oid: str) -> Optional[CorrelationOperator]:
        return self.operators.get(oid)

    def apply_commutator(self, oid_a: str, oid_b: str, strength: float = 0.1):
        if oid_a not in self.operators or oid_b not in self.operators:
            return
        a = self.operators[oid_a]
        b = self.operators[oid_b]
        dist = semantic_distance(a.type, b.type)
        delta = strength * (1.0 - dist)
        a.update_coherence(delta, f"commutator with {b.id[:8]}", sigma_topo=delta * 0.5)
        b.update_coherence(delta, f"commutator with {a.id[:8]}", sigma_topo=delta * 0.5)
        heapq.heappush(self.excited, (-a.coherence, a.id))
        heapq.heappush(self.excited, (-b.coherence, b.id))

    def propagate(self, max_steps: int = 12):
        seen = set()
        steps = 0
        while self.excited and steps < max_steps:
            _, oid = heapq.heappop(self.excited)
            if oid in seen:
                continue
            seen.add(oid)
            op = self.operators.get(oid)
            if op:
                for n in list(op.edges):
                    if random.random() < 0.4:
                        self.apply_commutator(oid, n, 0.09)
            steps += 1

class CoherenceScheduler:
    def __init__(self, graph: CorrelationGraphManager, engine=None):
        self.graph = graph
        self.engine = engine

    async def tick(self):
        for op in list(self.graph.operators.values()):
            if op.active:
                op.update_coherence(-0.012, "natural decay")
            elif random.random() < 0.03:
                op.update_coherence(0.08, "remote event")
        self.graph.propagate()

        if self.engine and self.engine.network_manager:
            # Future: trigger network updates per client
            pass

class PhysicsEngine:
    def __init__(self):
        self.graph = CorrelationGraphManager()
        self.scheduler = CoherenceScheduler(self.graph, engine=self)
        self.running = False
        self.tick_rate = 20
        self.boundary_store = {}
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
