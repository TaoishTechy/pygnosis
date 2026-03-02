# robotics.py
from core import CorrelationOperator
import asyncio
import random

class SimulatedGPIO:
    def __init__(self):
        self.devices = {"arduino_fan": {"temperature": 22.0, "fan": False}}

    async def get_sensor(self, device: str, sensor: str):
        val = self.devices[device].get(sensor, 22.0)
        if sensor == "temperature":
            val += random.uniform(-1.0, 2.5)
        return round(val, 1)

    async def set_actuator(self, device: str, actuator: str, value):
        if device in self.devices and actuator in self.devices[device]:
            self.devices[device][actuator] = value
            print(f"   🔥 GPIO SIM → {device}/{actuator} = {value}")
            return True
        return False

class Robot(CorrelationOperator):
    def __init__(self, rid: str):
        self.sensors = {"temperature": 22.0}
        self.actuators = {"fan": False}
        super().__init__("Robot", f"robot_{rid}", 0.92)

    def update_sensor(self, temp: float):
        old_temp = self.sensors["temperature"]
        self.sensors["temperature"] = temp
        delta = 0.15 if abs(temp - old_temp) > 2.0 else 0.05
        sigma = 0.1 if delta > 0.1 else 0.0
        self.update_coherence(delta, f"sensor temp={temp}°C", sigma_topo=sigma)

    def set_actuator(self, name: str, value):
        self.actuators[name] = value
        self.update_coherence(0.2, f"actuator {name}={value}", sigma_topo=0.2)
        self.mark_visuals_dirty()

    def update_visuals(self):
        if self.actuators.get("fan") or self.sensors.get("temperature", 22) > 28:
            self._mers["emissive"] = 0.4
            self._animation_params["amplitude"] = 0.3
        else:
            self._mers["emissive"] = 0.1
            self._animation_params["amplitude"] = 0.05
        super().update_visuals()

class RoboticsPlugin:
    def __init__(self, engine):
        self.engine = engine
        self.gpio = SimulatedGPIO()
        self.robots = {}

    def spawn_robot(self, rid: str):
        robot = Robot(rid)
        self.robots[rid] = robot
        self.engine.graph.add(robot)
        print(f"   🤖 Robot {rid} spawned")

    async def on_tick(self):
        for robot in self.robots.values():
            temp = await self.gpio.get_sensor("arduino_fan", "temperature")
            robot.update_sensor(temp)
            if temp > 28.0 and not robot.actuators["fan"]:
                await self.gpio.set_actuator("arduino_fan", "fan", True)
                robot.set_actuator("fan", True)
                print("   🌡️  Greenhouse cooling ACTIVATED!")
            elif temp <= 25.0 and robot.actuators["fan"]:
                await self.gpio.set_actuator("arduino_fan", "fan", False)
                robot.set_actuator("fan", False)
                print("   🌬️  Fan turned off")
