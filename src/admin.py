# admin.py
import asyncio
import json
import time
from collections import deque
from aiohttp import web
from core import _total_coherence

class AdminServer:
    def __init__(self, engine, host="0.0.0.0", port=8081):
        self.engine = engine
        self.host = host
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        self.coherence_history = deque(maxlen=60)
        self.time_history = deque(maxlen=60)
        self.start_time = time.time()

    def setup_routes(self):
        self.app.router.add_get("/api/status", self.status)
        self.app.router.add_get("/api/operators", self.list_operators)
        self.app.router.add_get("/api/operator/{oid}", self.get_operator)
        self.app.router.add_get("/api/edges", self.get_edges)
        self.app.router.add_get("/api/entities", self.get_entities)
        self.app.router.add_get("/api/history", self.get_history)
        self.app.router.add_post("/api/control/{action}", self.control)
        self.app.router.add_get("/ws", self.websocket_handler)
        self.app.router.add_get("/", self.dashboard)

    async def status(self, request):
        self.coherence_history.append(_total_coherence)
        self.time_history.append(time.time() - self.start_time)
        return web.json_response({
            "tick_rate": self.engine.tick_rate,
            "total_operators": len(self.engine.graph.operators),
            "active": sum(1 for o in self.engine.graph.operators.values() if o.active),
            "global_coherence": round(_total_coherence, 2),
            "boundary_chunks": len(self.engine.boundary_store),
            "clients": len(self.engine.network_manager.clients) if self.engine.network_manager else 0,
        })

    async def list_operators(self, request):
        ops = []
        for op in self.engine.graph.operators.values():
            op.update_visuals()          # Fixed: was ensure_visuals()
            data = op.to_network_dict()
            data["ci"] = round(data["coherence"], 2)
            data["emissive"] = round(data["mers"]["emissive"], 2)
            data["roughness"] = round(data["mers"]["roughness"], 2)
            data["metalness"] = round(data["mers"]["metalness"], 2)
            data["lod_bias"] = round(data["lod_bias"], 2)
            ops.append(data)
        return web.json_response(ops)

    async def get_operator(self, request):
        oid = request.match_info["oid"]
        op = self.engine.graph.get(oid)
        if op:
            data = op.to_network_dict()
            data["state"] = op.state
            data["edges"] = list(op.edges)
            return web.json_response(data)
        return web.json_response({"error": "Not found"}, status=404)

    async def get_edges(self, request):
        edges = []
        seen = set()
        for oid, op in self.engine.graph.operators.items():
            for n in op.edges:
                key = tuple(sorted([oid, n]))
                if key not in seen:
                    seen.add(key)
                    edges.append({"from": oid, "to": n})
        return web.json_response(edges)

    async def get_entities(self, request):
        entities = []
        for op in self.engine.graph.operators.values():
            if op.type in ["Player", "Item", "Robot"]:
                data = op.to_network_dict()
                if op.type == "Player":
                    data["pos"] = op.pos
                    data["inventory"] = op.inventory.to_dict()
                elif op.type == "Item":
                    data["pos"] = op.pos
                    data["item_type"] = op.item_type
                elif op.type == "Robot":
                    data["sensors"] = op.sensors
                    data["actuators"] = op.actuators
                entities.append(data)
        return web.json_response(entities)

    async def get_history(self, request):
        return web.json_response({
            "time": list(self.time_history),
            "coherence": list(self.coherence_history),
        })

    async def control(self, request):
        action = request.match_info["action"]
        data = await request.json()
        if action == "compress_chunk":
            cx, cz = data.get("cx", 0), data.get("cz", 0)
            chunk = self.engine.graph.get(f"chunk_{cx}_{cz}")
            if chunk:
                chunk.compress()
                return web.json_response({"status": "compressed"})
        elif action == "spawn_robot":
            rid = data.get("rid", "admin")
            self.engine.robotics.spawn_robot(rid)
            return web.json_response({"status": "spawned"})
        return web.json_response({"error": "Invalid action"}, status=400)

    async def websocket_handler(self, request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        while True:
            msg = await ws.receive_json()
            if msg["type"] == "subscribe":
                # Placeholder for real-time updates
                await ws.send_json(self.engine.graph.to_network_dict()[:3])
        return ws

    async def dashboard(self, request):
        html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Pygnosis Admin Dashboard</title>
    <style>
        body { background: #121212; color: #eee; font-family: Arial; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #444; padding: 8px; text-align: left; }
        .mers-indicator { display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin: 0 2px; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <script src="https://threejs.org/build/three.min.js"></script>
</head>
<body>
    <h1>Pygnosis Admin Dashboard</h1>
    <canvas id="coherenceChart" width="400" height="200"></canvas>
    <h2>Operators</h2>
    <table id="operatorTable">
        <thead><tr><th>ID</th><th>Type</th><th>CI</th><th>MERS</th><th>LOD Bias</th><th>Active</th></tr></thead>
        <tbody></tbody>
    </table>
    <button onclick="compressChunk()">Compress Chunk (0,0)</button>
    <button onclick="spawnRobot()">Spawn Robot</button>
    <script>
        function initChart() { let ctx = document.getElementById('coherenceChart').getContext('2d');
            new Chart(ctx, {type: 'line', data: {labels: [], datasets: [{label: 'Global Coherence', data: []}]}, options: {scales: {y: {beginAtZero: true}}}});}
        function updateScatter() { /* Placeholder */ }
        async function updateOperators(){ let r=await fetch('/api/operators'); let ops=await r.json(); let tbody=document.querySelector('#operatorTable tbody'); tbody.innerHTML='';
            ops.forEach(op=>{ let row=tbody.insertRow(); row.innerHTML=`
                <td><a href="/api/operator/${op.id}" target="_blank" style="color:#aaccff;">${op.id.substring(0,8)}</a></td>
                <td>${op.type}</td><td>${op.ci}</td>
                <td><span class="mers-indicator" style="background:hsl(${op.emissive*360},100%,50%)"></span>E:${op.emissive}
                <span class="mers-indicator" style="background:hsl(${op.roughness*360},100%,50%)"></span>R:${op.roughness}
                <span class="mers-indicator" style="background:hsl(${op.metalness*360},100%,50%)"></span>M:${op.metalness}</td>
                <td>${op.lod_bias}</td><td>${op.active?'✅':'❌'}</td>`;});}
        async function compressChunk(){ await fetch('/api/control/compress_chunk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cx:0,cz:0})}); }
        async function spawnRobot(){ await fetch('/api/control/spawn_robot',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rid:'admin_'+Date.now()})}); }
        window.onload=function(){ initChart(); setInterval(updateOperators,2000); };
    </script>
</body>
</html>"""
        return web.Response(text=html, content_type="text/html")

    async def start(self):
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        print(f"🌐 Admin dashboard → http://{self.host}:{self.port}")
