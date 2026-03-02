# world.py
from typing import Dict, Any, Optional, Tuple
from core import CorrelationOperator, adjust_global_coherence
import random

class Chunk(CorrelationOperator):
    """A 16x256x16 region with block palette and per-block MERS."""
    def __init__(self, cx: int, cz: int, engine=None):
        super().__init__("Chunk", f"chunk_{cx}_{cz}", 0.15)
        self.cx, self.cz = cx, cz
        self.engine = engine   # reference to physics engine for boundary store
        self.boundary = True
        self.palette = ["air", "stone", "dirt", "grass"]
        self.block_ids = {}          # (lx,ly,lz) -> palette index
        self.metadata = {}
        self.block_mers = {}          # (lx,ly,lz) -> dict
        self._dirty_block_visuals = set()

    def inflate(self):
        if not self.boundary:
            return
        key = f"{self.cx},{self.cz}"
        if self.engine and key in self.engine.boundary_store:
            data = self.engine.boundary_store[key]
            self.block_ids, self.palette, self.metadata, self.block_mers = data
            print(f"   Loaded chunk {self.cx},{self.cz} from boundary store")
        else:
            print(f"   Inflating chunk {self.cx},{self.cz} (new)")
            for x in range(16):
                for z in range(16):
                    self.block_ids[(x, 60, z)] = 1   # stone
        self.boundary = False
        self.update_coherence(0.7, "inflated by player", sigma_topo=0.3)

    def compress(self):
        if self.boundary:
            return
        key = f"{self.cx},{self.cz}"
        data = (self.block_ids, self.palette, self.metadata, self.block_mers)
        if self.engine:
            self.engine.boundary_store[key] = data
            print(f"   Compressed chunk {self.cx},{self.cz} to boundary store")
        self.block_ids = {}
        self.palette = []
        self.metadata = {}
        self.block_mers = {}
        self.boundary = True
        self.update_coherence(-0.7, "compressed to boundary", sigma_topo=-0.3)

    def set_block(self, lx: int, ly: int, lz: int, block: str):
        if block not in self.palette:
            self.palette.append(block)
        idx = self.palette.index(block)
        self.block_ids[(lx, ly, lz)] = idx
        self.update_coherence(0.12, f"block change {block}", sigma_topo=0.05)
        self._dirty_block_visuals.add((lx, ly, lz))

    def get_block_visual(self, lx: int, ly: int, lz: int) -> dict:
        if (lx, ly, lz) in self._dirty_block_visuals or self._dirty_visuals:
            self.update_visuals()
            self._dirty_block_visuals.discard((lx, ly, lz))
        mers = self.block_mers.get((lx, ly, lz), self._mers)
        return {"mers": mers, "anim": self._animation_params}

    def update_visuals(self):
        super().update_visuals()
        if random.random() < 0.1:
            self._mers["subsurface"] = self.coherence * 0.3

class Inventory:
    def __init__(self, name: str):
        self.name = name
        self.slots = [None] * 36

    def add_item(self, item_type: str, count: int = 1):
        for i, slot in enumerate(self.slots):
            if slot and slot[0] == item_type and slot[1] < 64:
                slot[1] += count
                return
            elif not slot:
                self.slots[i] = [item_type, count]
                return

    def to_dict(self) -> list:
        return self.slots

class Player(CorrelationOperator):
    def __init__(self, name: str, pos: tuple = (0, 64, 0), engine=None):
        self.pos = pos
        self.inventory = Inventory(name)
        super().__init__("Player", f"player_{name}", 0.98)
        self.engine = engine

    def move_to(self, new_pos):
        old_pos = self.pos
        self.pos = new_pos
        old_cx, old_cz = old_pos[0]//16, old_pos[2]//16
        new_cx, new_cz = new_pos[0]//16, new_pos[2]//16
        if (old_cx, old_cz) != (new_cx, new_cz) and self.engine:
            # would load/unload chunks
            pass
        self.update_coherence(0.1, "moved")

    def update_visuals(self):
        holding_torch = any(slot and slot[0] == "torch" for slot in self.inventory.slots if slot)
        self._mers["emissive"] = 0.3 if holding_torch else 0.0
        super().update_visuals()

class Item(CorrelationOperator):
    def __init__(self, item_type: str, pos: tuple):
        self.item_type = item_type
        self.pos = pos
        super().__init__("Item", f"item_{item_type}", 0.25)

    def update_visuals(self):
        if self.item_type == "diamond":
            self._mers["emissive"] = 0.5
            self._mers["roughness"] = 0.1
        elif self.item_type == "stone":
            self._mers["roughness"] = 0.9
        super().update_visuals()
