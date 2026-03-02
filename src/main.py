# main.py
import asyncio
import os
import sys
import argparse
from core import PhysicsEngine
from world import Chunk, Player, Item
from robotics import RoboticsPlugin
from admin import AdminServer
import network
import protocol

async def main(debug=False):
    if debug:
        print("🔧 Debug mode enabled")
        from core import QUIET_DECAY
        import core
        core.QUIET_DECAY = False  # Show all coherence updates

    engine = PhysicsEngine()
    admin = AdminServer(engine)
    robotics = RoboticsPlugin(engine)

    config_path = os.path.join(os.path.dirname(__file__), "network_config.json")
    net_mgr = network.NetworkManager(engine, config_path)
    engine.network_manager = net_mgr

    network.network_manager = net_mgr
    protocol.network_manager = net_mgr

    # World setup
    chunk = Chunk(0, 0, engine=engine)
    chunk.inflate()
    engine.graph.add(chunk)

    player = Player("Alex", engine=engine)
    player.inventory.add_item("diamond", 5)
    engine.graph.add(player)

    diamond_item = Item("diamond", (1, 64, 1))
    engine.graph.add(diamond_item)

    print("\n🛠️  Player mining stone...")
    chunk.set_block(5, 60, 5, "air")
    player.inventory.add_item("stone", 1)

    block_vis = chunk.get_block_visual(5, 60, 5)
    print(f"   Block visual after mining: {block_vis}")

    robotics.spawn_robot("greenhouse")

    await admin.start()
    await net_mgr.start(host="0.0.0.0", port=25565)
    asyncio.create_task(engine.start())

    print("\n🎮 Pygnosis server running with Network Framework! (Ctrl+C to stop)")
    print("   → Open http://localhost:8081 in your browser")
    print("   → Minecraft clients can connect to localhost:25565")
    if debug:
        print("   → Debug mode: verbose logging enabled")

    try:
        while True:
            await asyncio.sleep(2)
            await robotics.on_tick()
            if "arduino_fan" in robotics.gpio.devices:
                robotics.gpio.devices["arduino_fan"]["temperature"] += 1.8

            if debug:
                print("\n📡  Visual data snapshot (would be sent to clients):")
                for op in list(engine.graph.operators.values())[:3]:
                    data = op.to_network_dict()
                    print(f"   {data['id'][:12]} ci={data['coherence']:.2f} "
                          f"emissive={data['mers']['emissive']:.2f} "
                          f"lod_bias={data['lod_bias']:.2f}")
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n🛑 Shutting down...")
        engine.stop()
        if net_mgr.server:
            net_mgr.server.close()
            await net_mgr.server.wait_closed()
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pygnosis Minecraft Server")
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()
    asyncio.run(main(debug=args.debug))
