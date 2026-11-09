"""设备仿真类（迁移自 HomeBench visual_home/device.py）。

M2 说明：
- 本文件保留 HomeBench 的 16 类设备及其 operations / attributes 的**执行语义**，
  作为 SimulateExecutor 的后端（改内存状态）。
- 仅迁移"仿真执行"所需部分：__init__ / 各操作方法 / initialize / get_status，
  以及 device_map。原文件中用于数据集生成的 generate_instructions /
  generate_unexist_instructions / random_initialize 与仿真执行无关，未迁移，
  以保持文件精简并规避原文件 PetFeeder.generate_instructions 的语法错误。
- CurtainDevice 的属性/操作名在原始 HomeBench 中带前导空格（" degree"/"set_ degree"），
  为与数据集/方法签名保持一致，此处**原样保留**。
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


class _BaseDevice:
    """公共能力：initialize / get_status。"""

    name: str = "device"

    def initialize(self, state: str, attributes: Optional[Dict[str, Any]] = None):
        self.state = state
        if attributes:
            self.attributes = attributes

    def get_status(self) -> Dict[str, Any]:
        return {"state": getattr(self, "state", None), "attributes": self.attributes}


class LightDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "light"
        self.state = state
        self.attributes = {
            "brightness": {"value": 100, "lowest": "0", "highest": "100"},
            "color": {"value": (255, 255, 255)},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_brightness": self.set_brightness,
            "set_color": self.set_color,
        }

    def turn_on(self):
        self.state = "on"
        pass  # (silenced) print("Device is now ON.")

    def turn_off(self):
        self.state = "off"
        pass  # (silenced) print("Device is now OFF.")

    def set_brightness(self, brightness: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set brightness while device is off.")
        else:
            self.attributes["brightness"]["value"] = brightness
            pass  # (silenced) print(f"Brightness set to {brightness}.")

    def set_color(self, color: Tuple[int, int, int]):
        if self.state == "off":
            pass  # (silenced) print("Cannot set color while device is off.")
        else:
            self.attributes["color"]["value"] = color
            pass  # (silenced) print(f"Color set to {color}.")


class AirConditionerDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "air_conditioner"
        self.state = state
        self.attributes = {
            "temperature": {"value": 25, "lowest": "16", "highest": "30"},
            "mode": {"value": "cool", "options": ["cool", "heat", "fan_only", "dry"]},
            "fan_speed": {"value": "auto", "options": ["auto", "low", "medium", "high"]},
            "swing": {"value": "auto", "options": ["auto", "up", "middle", "down"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_temperature": self.set_temperature,
            "set_mode": self.set_mode,
            "set_fan_speed": self.set_fan_speed,
            "set_swing": self.set_swing,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_temperature(self, temperature: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set temperature while device is off.")
        else:
            self.attributes["temperature"]["value"] = temperature

    def set_mode(self, mode: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set mode while device is off.")
        elif mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode

    def set_fan_speed(self, fan_speed: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set fan speed while device is off.")
        elif fan_speed not in self.attributes["fan_speed"]["options"]:
            pass  # (silenced) print(f"Invalid fan speed: {fan_speed}.")
        else:
            self.attributes["fan_speed"]["value"] = fan_speed

    def set_swing(self, swing: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set swing while device is off.")
        elif swing not in self.attributes["swing"]["options"]:
            pass  # (silenced) print(f"Invalid swing: {swing}.")
        else:
            self.attributes["swing"]["value"] = swing


class HeatingDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "heating"
        self.state = state
        self.attributes = {
            "temperature": {"value": 25, "lowest": "16", "highest": "30"},
            "mode": {"value": "heat", "options": ["heat", "fan_only"]},
            "fan_speed": {"value": "auto", "options": ["auto", "low", "medium", "high"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_temperature": self.set_temperature,
            "set_mode": self.set_mode,
            "set_fan_speed": self.set_fan_speed,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_temperature(self, temperature: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set temperature while device is off.")
        else:
            self.attributes["temperature"]["value"] = temperature

    def set_mode(self, mode: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set mode while device is off.")
        elif mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode

    def set_fan_speed(self, fan_speed: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set fan speed while device is off.")
        elif fan_speed not in self.attributes["fan_speed"]["options"]:
            pass  # (silenced) print(f"Invalid fan speed: {fan_speed}.")
        else:
            self.attributes["fan_speed"]["value"] = fan_speed


class FanDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "fan"
        self.state = state
        self.attributes = {
            "speed": {"value": "auto", "options": ["auto", "low", "medium", "high"]},
            "swing": {"value": "auto", "options": ["auto", "up", "middle", "down"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_speed": self.set_speed,
            "set_swing": self.set_swing,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_speed(self, speed: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set speed while device is off.")
        elif speed not in self.attributes["speed"]["options"]:
            pass  # (silenced) print(f"Invalid speed: {speed}.")
        else:
            self.attributes["speed"]["value"] = speed

    def set_swing(self, swing: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set swing while device is off.")
        elif swing not in self.attributes["swing"]["options"]:
            pass  # (silenced) print(f"Invalid swing: {swing}.")
        else:
            self.attributes["swing"]["value"] = swing


class GarageDoorDevice(_BaseDevice):
    def __init__(self, state: str = "closed"):
        self.name = "garage_door"
        self.state = state
        self.attributes = {}
        self.operations = {"open": self.open, "close": self.close}

    def open(self):
        self.state = "open"

    def close(self):
        self.state = "closed"


class BlindsDevice(_BaseDevice):
    def __init__(self, state: str = "closed"):
        self.name = "blinds"
        self.state = state
        self.attributes = {}
        self.operations = {"open": self.open, "close": self.close}

    def open(self):
        self.state = "open"

    def close(self):
        self.state = "closed"


class CurtainDevice(_BaseDevice):
    def __init__(self, state: str = "closed"):
        self.name = "curtain"
        self.state = state
        # 注意：HomeBench 原始定义中属性/操作名带前导空格，原样保留以对齐数据集
        self.attributes = {" degree": {"value": 0, "lowest": 0, "highest": "100"}}
        self.operations = {
            "open": self.open,
            "close": self.close,
            "set_ degree": self.set_degree,
        }

    def open(self):
        self.state = "open"

    def close(self):
        self.state = "closed"

    def set_degree(self, degree: int):
        self.attributes[" degree"]["value"] = degree


class AirPurifiersDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "air_purifiers"
        self.state = state
        self.attributes = {
            "mode": {"value": "auto", "options": ["auto", "sleep"]},
            "fan_speed": {"value": "auto", "options": ["auto", "low", "medium", "high"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_mode": self.set_mode,
            "set_fan_speed": self.set_fan_speed,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_mode(self, mode: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set mode while device is off.")
        elif mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode

    def set_fan_speed(self, fan_speed: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set fan speed while device is off.")
        elif fan_speed not in self.attributes["fan_speed"]["options"]:
            pass  # (silenced) print(f"Invalid fan speed: {fan_speed}.")
        else:
            self.attributes["fan_speed"]["value"] = fan_speed


class WaterHeaterDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "water_heater"
        self.state = state
        self.attributes = {
            "temperature": {"value": 60, "lowest": "30", "highest": "100"},
            "mode": {"value": "heating", "options": ["heating", "eco"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_temperature": self.set_temperature,
            "set_mode": self.set_mode,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_temperature(self, temperature: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set temperature while device is off.")
        else:
            self.attributes["temperature"]["value"] = temperature

    def set_mode(self, mode: str):
        if self.state == "off":
            pass  # (silenced) print("Cannot set mode while device is off.")
        elif mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode


class MediaPlayerDevice(_BaseDevice):
    def __init__(self, state: str = "stopped"):
        self.name = "media_player"
        self.state = state
        self.attributes = {"volume": {"value": 50, "lowest": "0", "highest": "100"}}
        self.operations = {
            "play": self.play,
            "pause": self.pause,
            "stop": self.stop,
            "set_volume": self.set_volume,
            "set_song": self.set_song,
            "set_artist": self.set_artist,
            "set_style": self.set_style,
        }

    def play(self):
        self.state = "playing"

    def pause(self):
        self.state = "paused"

    def stop(self):
        self.state = "stopped"

    def set_volume(self, volume: int):
        self.attributes["volume"]["value"] = volume

    def set_song(self, song: str):
        pass  # (silenced) print(f"Song set to {song}.")

    def set_artist(self, artist: str):
        pass  # (silenced) print(f"Artist set to {artist}.")

    def set_style(self, style: str):
        pass  # (silenced) print(f"Style set to {style}.")


class VacuumRobotDevice(_BaseDevice):
    def __init__(self, state: str = "stopped"):
        self.name = "vacuum_robot"
        self.state = state
        self.attributes = {
            "battery": {"value": 100, "lowest": 0, "highest": 100},
            "mode": {"value": "auto", "options": ["auto", "strong", "sleep"]},
        }
        self.operations = {
            "start": self.start,
            "pause": self.pause,
            "stop": self.stop,
            "charge": self.charge,
            "set_mode": self.set_mode,
            "set_cleaning_area": self.set_cleaning_area,
        }

    def start(self):
        self.state = "cleaning"

    def pause(self):
        self.state = "paused"

    def stop(self):
        self.state = "stopped"

    def charge(self):
        self.state = "charging"

    def set_mode(self, mode: str):
        if mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode

    def set_cleaning_area(self, area: str):
        pass  # (silenced) print(f"Cleaning area set to {area}.")


class AromatherapyDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "aromatherapy"
        self.state = state
        self.attributes = {
            "intensity": {"value": 50, "lowest": "0", "highest": "100"},
            "interval": {"value": 30, "lowest": "10", "highest": "60"},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_intensity": self.set_intensity,
            "set_interval": self.set_interval,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_intensity(self, intensity: int):
        self.attributes["intensity"]["value"] = intensity

    def set_interval(self, interval: int):
        self.attributes["interval"]["value"] = interval


class TrashDevice(_BaseDevice):
    def __init__(self, state: str = "not_full"):
        self.name = "trash"
        self.state = state
        self.attributes = {}
        self.operations = {"pack": self.pack}

    def pack(self):
        self.state = "empty"


class HumidifierDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "humidifier"
        self.state = state
        self.attributes = {
            "mode": {"value": "auto", "options": ["auto", "sleep"]},
            "intensity": {"value": 50, "lowest": 0, "highest": 100},
            "tank": {"value": 100, "lowest": 0, "highest": 100},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_mode": self.set_mode,
            "set_intensity": self.set_intensity,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_mode(self, mode: str):
        if mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        elif self.attributes["tank"]["value"] != 0:
            self.attributes["mode"]["value"] = mode

    def set_intensity(self, intensity: int):
        if self.attributes["tank"]["value"] != 0:
            self.attributes["intensity"]["value"] = intensity


class DehumidifiersDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "dehumidifiers"
        self.state = state
        self.attributes = {
            "mode": {"value": "auto", "options": ["auto", "sleep"]},
            "intensity": {"value": 50, "lowest": "0", "highest": "100"},
            "tank": {"value": 0, "lowest": "0", "highest": "100"},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_mode": self.set_mode,
            "set_intensity": self.set_intensity,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_mode(self, mode: str):
        if mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        elif self.attributes["tank"]["value"] != 100:
            self.attributes["mode"]["value"] = mode

    def set_intensity(self, intensity: int):
        if self.attributes["tank"]["value"] != 100:
            self.attributes["intensity"]["value"] = intensity


class PetFeederDevice(_BaseDevice):
    def __init__(self, state: str = "off"):
        self.name = "pet_feeder"
        self.state = state
        self.attributes = {
            "feeding_interval": {"value": 24, "lowest": 1, "highest": 24},
            "feeding_weight": {"value": 50, "lowest": 0, "highest": 100},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_feeding_interval": self.set_feeding_interval,
            "set_feeding_weight": self.set_feeding_weight,
            "feed": self.feed,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_feeding_interval(self, feeding_interval: int):
        self.attributes["feeding_interval"]["value"] = feeding_interval

    def set_feeding_weight(self, feeding_weight: int):
        self.attributes["feeding_weight"]["value"] = feeding_weight

    def feed(self):
        if self.state == "off":
            pass  # (silenced) print("Cannot feed while device is off.")
        else:
            pass  # (silenced) print("Feeding.")


class BedDevice(_BaseDevice):
    """无 state 的设备，仅有 attributes。"""

    def __init__(self, state: str = None):
        self.name = "bed"
        self.state = state
        self.attributes = {
            "angle": {"value": 0, "lowest": 0, "highest": 60},
            "massage": {"value": "off", "options": ["off", "low", "medium", "high"]},
        }
        self.operations = {
            "set_angle": self.set_angle,
            "set_massage": self.set_massage,
        }

    def set_angle(self, angle: int):
        self.attributes["angle"]["value"] = angle

    def set_massage(self, massage: str):
        self.attributes["massage"]["value"] = massage


# 设备类型 → 类 的映射（对齐 HomeBench device_map）
device_map = {
    "light": LightDevice,
    "heating": HeatingDevice,
    "fan": FanDevice,
    "air_conditioner": AirConditionerDevice,
    "garage_door": GarageDoorDevice,
    "blinds": BlindsDevice,
    "curtain": CurtainDevice,
    "media_player": MediaPlayerDevice,
    "vacuum_robot": VacuumRobotDevice,
    "trash": TrashDevice,
    "humidifier": HumidifierDevice,
    "dehumidifiers": DehumidifiersDevice,
    "aromatherapy": AromatherapyDevice,
    "water_heater": WaterHeaterDevice,
    "air_purifiers": AirPurifiersDevice,
    "pet_feeder": PetFeederDevice,
    "bed": BedDevice,
}


# ============================================================================ #
# SAGE 特有设备类（P2：SAGE 数据集含 SmartThings 真实设备，如 TV/冰箱/洗碗机等，
# HomeBench 16 类未覆盖。此处按 HomeBench 风格（state + attributes + operations）
# 补齐，使 SAGE 抽象场景里的每个设备都有可执行的仿真后端。）
# ============================================================================ #
class TVDevice(_BaseDevice):
    """电视（对应 SAGE main TV / frame TV）。支持频道、音量、开关。"""

    def __init__(self, state: str = "off"):
        self.name = "tv"
        self.state = state
        self.attributes = {
            "volume": {"value": 30, "lowest": "0", "highest": "100"},
            "channel": {"value": 1, "lowest": "1", "highest": "999"},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_volume": self.set_volume,
            "set_channel": self.set_channel,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_volume(self, volume: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set volume while TV is off.")
        else:
            self.attributes["volume"]["value"] = volume

    def set_channel(self, channel: int):
        if self.state == "off":
            pass  # (silenced) print("Cannot set channel while TV is off.")
        else:
            self.attributes["channel"]["value"] = channel


class FridgeDevice(_BaseDevice):
    """冰箱（含冷藏 + 冷冻两个温区，对应 SAGE fridge/freezer 组件）。"""

    def __init__(self, state: str = "on"):
        self.name = "fridge"
        self.state = state
        self.attributes = {
            "fridge_temperature": {"value": 4, "lowest": "1", "highest": "7"},
            "freezer_temperature": {"value": -18, "lowest": "-24", "highest": "-14"},
            "mode": {"value": "normal", "options": ["normal", "eco", "power_cool"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "set_fridge_temperature": self.set_fridge_temperature,
            "set_freezer_temperature": self.set_freezer_temperature,
            "set_mode": self.set_mode,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def set_fridge_temperature(self, temperature: int):
        self.attributes["fridge_temperature"]["value"] = temperature

    def set_freezer_temperature(self, temperature: int):
        self.attributes["freezer_temperature"]["value"] = temperature

    def set_mode(self, mode: str):
        if mode not in self.attributes["mode"]["options"]:
            pass  # (silenced) print(f"Invalid mode: {mode}.")
        else:
            self.attributes["mode"]["value"] = mode


class DishwasherDevice(_BaseDevice):
    """洗碗机（对应 SAGE dishwasher，含运行阶段与洗涤程序）。"""

    def __init__(self, state: str = "off"):
        self.name = "dishwasher"
        self.state = state
        self.attributes = {
            "job_state": {"value": "idle", "options": ["idle", "prewash", "wash", "rinse", "dry"]},
            "course": {"value": "auto", "options": ["auto", "eco", "heavy", "intensive", "quick"]},
        }
        self.operations = {
            "turn_on": self.turn_on,
            "turn_off": self.turn_off,
            "start": self.start,
            "stop": self.stop,
            "set_course": self.set_course,
        }

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"

    def start(self):
        if self.state == "off":
            pass  # (silenced) print("Cannot start while dishwasher is off.")
        else:
            self.attributes["job_state"]["value"] = "wash"

    def stop(self):
        self.attributes["job_state"]["value"] = "idle"

    def set_course(self, course: str):
        if course not in self.attributes["course"]["options"]:
            pass  # (silenced) print(f"Invalid course: {course}.")
        else:
            self.attributes["course"]["value"] = course


class SwitchDevice(_BaseDevice):
    """通用开关（对应 SAGE switch，如插座/景观灯）。"""

    def __init__(self, state: str = "off"):
        self.name = "switch"
        self.state = state
        self.attributes = {}
        self.operations = {"turn_on": self.turn_on, "turn_off": self.turn_off}

    def turn_on(self):
        self.state = "on"

    def turn_off(self):
        self.state = "off"


# 把 SAGE 特有设备并入 device_map（与 HomeBench 16 类共用同一 SimulateExecutor）
device_map["tv"] = TVDevice
device_map["frame_tv"] = TVDevice
device_map["fridge"] = FridgeDevice
device_map["dishwasher"] = DishwasherDevice
device_map["switch"] = SwitchDevice
