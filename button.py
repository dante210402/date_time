from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.config_entries import ConfigEntry
from datetime import datetime
import logging
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, _config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """初始化按钮实体"""
    # 从hass数据中获取传感器实例
    sensor = hass.data[DOMAIN].get('refreshable_sensor')
    if sensor:
        async_add_entities([RefreshButton(hass, sensor)])


class RefreshButton(ButtonEntity):
    """自定义按钮实体"""

    # 实体基本信息
    _attr_name = "立即刷新"
    _attr_unique_id = "date_time_refresh_button"
    _attr_icon = "mdi:refresh"  # 按钮图标

    def __init__(self, hass: HomeAssistant, sensor):
        self.hass = hass
        self.sensor = sensor

    async def async_press(self) -> None:
        """按钮被点击时执行的操作"""
        # 这里添加按钮点击后的逻辑
        self.hass.states.async_set(
            self.entity_id,
            "pressed",
            {"last_pressed": datetime.now().isoformat()}
        )
        # 可调用服务、发送指令等
        await self.sensor.async_refresh()
        _LOGGER.info("Refreshed")


