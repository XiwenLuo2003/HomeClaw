"""WeatherTool（P3，次优先）：离线可复现的 mock 天气工具。

SAGE 原 WeatherTool 走 OpenWeatherMap API（需 key、不可复现）。此处提供 mock 版：
  - 默认返回确定性天气（供离线评测/演示，可复现）；
  - 若设置环境变量 OPENWEATHER_API_KEY，可切换到真实 API（保留接口，不强依赖）。
用于个性化用例如"把灯调成符合天气的颜色"。
"""
from __future__ import annotations

import os
from typing import Dict, Optional


_MOCK_WEATHER: Dict[str, Dict] = {
    "quebec city": {"condition": "sunny", "cloud_cover": 10, "temp_c": 22},
    "montreal": {"condition": "cloudy", "cloud_cover": 80, "temp_c": 18},
    "default": {"condition": "sunny", "cloud_cover": 20, "temp_c": 20},
}


class WeatherTool:
    """天气查询工具（mock 优先，可选真实 API）。"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")

    def get(self, location: str = "default") -> Dict:
        """返回 {condition, cloud_cover, temp_c}。有 key 时可接真实 API（此处仍回退 mock）。"""
        loc = (location or "default").strip().lower()
        return dict(_MOCK_WEATHER.get(loc, _MOCK_WEATHER["default"]))

    def is_sunny(self, location: str = "default") -> bool:
        return self.get(location)["cloud_cover"] < 50
