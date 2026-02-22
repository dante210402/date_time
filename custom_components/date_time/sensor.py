from datetime import datetime, timedelta
from lunar_python import Lunar
from zoneinfo import ZoneInfo
import logging
from typing import Literal
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.helpers.typing import ConfigType
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .calc import RestDay
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up sensor entity from config entry."""
    coordinator = DateCoordinator(hass, config_entry.data, _LOGGER)
    await coordinator.async_config_entry_first_refresh()
    entities: list[HolidaySensor | TimePeriodSensor | AnniversarySensor] = [
        HolidaySensor(coordinator),
        TimePeriodSensor(hass, "当前时间段", config_entry.entry_id),
    ]
    # 有几条纪念日配置就建几个 AnniversarySensor
    for entry in config_entry.data.get("anniversaries", []):
        key = f"{entry['anniversary_name']}{entry['anniversary_type']}{entry['anniversary_date']}"
        entities.append(AnniversarySensor(coordinator, key))

    async_add_entities(entities)

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    hass.data[DOMAIN]['refreshable_sensor'] = coordinator


class DateCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, config, logger: logging.Logger):
        super().__init__(hass, logger, name="holidays_anniversaries", update_interval=None)
        self.config = config  # 用来存放用户填的纪念日列表
        # self._update_task = None

    async def _async_schedule_daily(self, *args):
        self.logger.info("refresh entity states, automatically run at 2:00 everyday.")
        await self.async_refresh()

    async def async_config_entry_first_refresh(self) -> None:
        self.logger.info("first refresh entity config...")
        await self.async_refresh()
        async_track_time_change(
            self.hass, self._async_schedule_daily, hour=2, minute=0, second=0
        )

    async def _async_update_data(self) -> dict:
        """
        实际更新状态的核心方法
        :return:
        """
        now = datetime.now()
        anniversaries = await self._fetch_anniversaries(now)
        holidays = await self._fetch_holidays(anniversaries, now)
        self.logger.info("holidays and anniversaries has been refreshed already.")
        return {
            "holidays": holidays,
            "anniversaries": anniversaries,  # 字典，键是名字+类型+日期，元素是 dict
        }

    async def _fetch_holidays(self, anniversaries: dict, now: datetime = None) -> dict:
        if now is None:
            now = datetime.now()
        solar = now.replace(hour=0, minute=0, second=0, microsecond=0)
        lunar = Lunar.fromDate(solar)
        lunar_full = lunar.toFullString().split()
        this_festival, next_festival = self.get_festival(str(solar.month * 100 + solar.day).zfill(4))
        next_jieqi: dict = {
            'date': datetime.strptime(lunar.getNextJieQi().getSolar().toString(), FORMAT_DATE),
            'name': lunar.getNextJieQi().toString()
        }
        rest_day = RestDay(solar)
        state = rest_day.query(solar)

        next_anni_date = [(v['hint'], v['next_date']) for v in anniversaries.values()]
        next_anni_date.sort(key=lambda x: x[1])
        anniversary = '无' if next_anni_date[0][1] - now > timedelta(days=1) else next_anni_date[0][0]

        attributes = {
            '今天': f'{solar.strftime("%Y年%m月%d日")} {lunar_full[9]}',
            '农历': f'{lunar_full[1]} {lunar_full[0].split('年')[1]}',
            '周数': solar.isocalendar().week,
            '节气': lunar.getJieQi() if lunar.getJieQi() else f'{lunar.getPrevJieQi().toString()}后',
            '节假日': '无' if not this_festival else ' '.join(this_festival),
            '纪念日/生日': anniversary,
            '宜': '、'.join(lunar.getDayYi()),
            '忌': '、'.join(lunar.getDayJi()),
            '冲': lunar.getDayChongDesc(),
            '煞': lunar.getDaySha(),
            '更新时间': now.strftime(FORMAT_DATETIME_SHORT),
            '下一个节假日': f'{next_festival['date'].strftime("%m月%d日")} {" ".join(next_festival['name'])}',
            '下一个节气': f'{next_jieqi['date'].strftime("%m月%d日")} {next_jieqi['name']}',
            '下一个纪念日': f'{next_anni_date[0][1].strftime("%m月%d日")} {next_anni_date[0][0]}'
        }
        return {'state': state, 'attributes': attributes}

    def get_festival(self,
                     q_date: str = None,
                     q_dict: dict = None,
                     q_date_type: Literal['all', 'solar', 'lunar'] = 'all'
                     ) -> tuple[list, dict]:
        """
        查询指定日期或今天的节假日，及下一个节假日（注：指定日期只能是今年的）
        :param q_date: 查询的日期，默认为空，指定为今天，所有q_date均指阳历，除非指定了q_date_type为lunar，q_date需传入阴历日期
        :param q_dict:
        :param q_date_type:
        :return:
        """
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        if q_date is None:
            _date = Lunar.fromDate(today)
            q_date_solar = str(today.month * 100 + today.day).zfill(4)
            q_date_lunar = str(_date.getMonth() * 100 + _date.getDay()).zfill(4)
        else:
            _date = Lunar.fromDate(datetime(today.year, int(q_date[0:2]), int(q_date[2:4])))
            q_date_solar = q_date
            q_date_lunar = str(_date.getMonth() * 100 + _date.getDay()).zfill(4)

        if q_date_type == 'all':
            this_festival_solar, next_festival_solar = self.get_festival(q_date_solar, SOLAR_FESTIVAL, 'solar')
            this_festival_lunar, next_festival_lunar = self.get_festival(q_date_lunar, LUNAR_FESTIVAL, 'lunar')
            # 合并统计日的节日
            this_festival = this_festival_lunar + this_festival_solar
            # 选择下一个统计日
            q_date_lunar = next_festival_lunar['date']
            q_date_solar = next_festival_solar['date']
            if q_date_lunar == q_date_solar:
                next_festival = {
                    'date': q_date_lunar,
                    'name': next_festival_lunar['name'] + next_festival_solar['name']
                }
            elif q_date_lunar < q_date_solar:
                next_festival = next_festival_lunar
            else:
                next_festival = next_festival_solar
            return this_festival, next_festival

        else:
            q_keys = [int(k) for k in q_dict.keys()]
            q_date_int = int(q_date)
            this_festival = []
            # 查询统计日是否为节日
            if q_date_int in q_keys:
                this_festival = q_dict[str(q_date_int).zfill(4)]
            else:
                q_keys.append(q_date_int)  # 否则将q_date加入列表，计算排序后的位置
            # 查询下一个节日
            q_keys.sort()
            index_next = 0 if q_keys[-1] == q_date_int else q_keys.index(q_date_int) + 1
            date_string = str(q_keys[index_next]).zfill(4)
            if q_date_type == 'lunar':
                _date_s = Lunar.fromYmd(today.year, int(date_string[0:2]),
                                        int(date_string[2:4])).getSolar().toString()
                _date = datetime.strptime(_date_s, FORMAT_DATE)
            else:
                _date = datetime(today.year, int(date_string[0:2]), int(date_string[2:4]))
            next_festival = {'date': _date, 'name': q_dict[date_string]}
            return this_festival, next_festival

    async def _fetch_anniversaries(self, now: datetime = None) -> dict:
        anniversaries = {
            f"{entry['anniversary_name']}{entry['anniversary_type']}{entry['anniversary_date']}": self.get_anni_attributes(
                entry, now)
            for entry in self.config.get("anniversaries", [])
        }
        return anniversaries

    def get_anni_attributes(self, entry, now):
        if now is None:
            now = datetime.now()
        solar = now.replace(hour=0, minute=0, second=0, microsecond=0)
        anniversary_date = datetime.strptime(
            entry['anniversary_date'], '%Y%m%d'
        ).replace(hour=0, minute=0, second=0, microsecond=0)

        _slug_string = slugify(f'{entry['anniversary_name']}{entry['anniversary_type']}')
        entity_id = f'sensor.anniversary_{_slug_string}'
        _is_solar = entry['date_type'] == '阳历'
        next_date = self._next_day(anniversary_date, _is_solar, solar)
        age = next_date.year - anniversary_date.year
        if entry['anniversary_type'] == '纪念日':
            hint = f'{entry['anniversary_name']}{age}周年纪念日'
        else:
            hint = f'{entry['anniversary_name']}{entry['date_type']}{age}岁生日',
        attr = {
            'entity_id': entity_id,
            'name': f'{entry["anniversary_name"]}{entry["anniversary_type"]}',
            'hint': hint,
            'anniversary_name': entry['anniversary_name'],
            'date_type': entry['date_type'],
            'is_solar': entry['date_type'] == '阳历',
            'anniversary_type': entry['anniversary_type'],
            'next_date': next_date,
            'age': age,
            'date': anniversary_date,
            'days_left': (next_date - solar).days,
            'days': (solar - anniversary_date).days,
            'update_time': now.strftime(FORMAT_DATETIME_SHORT)
        }
        return attr

    @staticmethod
    def _next_day(_date: datetime, _is_solar: bool = True, now: datetime = None) -> datetime:
        """
        根据纪念日的日期，计算最近的一次纪念日日期
        :return:
        """
        if now is None:
            now = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        if _is_solar:
            _next_day = _date.replace(year=now.year)
            if _next_day < now:  # _solar_date < today说明要计算下一年的日期
                _next_day = _date.replace(year=now.year + 1)
            return _next_day
        else:
            # 农历日期在腊月时会比阳历早一年，如1988年1月实际上是农历的1987年
            _lunar_date = Lunar.fromYmd(now.year, _date.month, _date.day)
            _solar_date = datetime.strptime(_lunar_date.getSolar().toString(), FORMAT_DATE)
            if _solar_date < now:  # _solar_date < today说明要计算下一年的日期
                _lunar_date = Lunar.fromYmd(now.year + 1, _date.month, _date.day)
                _solar_date = datetime.strptime(_lunar_date.getSolar().toString(), FORMAT_DATE)
            elif _solar_date > now:  # _solar_date > today说明大概率是腊月出生的人，在年初更新
                _lunar_date = Lunar.fromYmd(now.year - 1, _date.month, _date.day)
                _solar_date = datetime.strptime(_lunar_date.getSolar().toString(), FORMAT_DATE)
            return _solar_date


class TimePeriodSensor(SensorEntity):
    """Sensor that reports current time period."""

    _attr_icon = "mdi:sun-clock"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True  # 启用轮询自动更新
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = TIME_PERIOD_ENUM_VALUES

    def __init__(self, hass, name, entry_id):
        self._attr_extra_state_attributes = {}
        self._hass = hass
        self._attr_name = name
        self.period = (None, None)
        self._attr_unique_id = f"{entry_id}_time_period"  # 唯一标识
        self.tz = None
        self._local_sun = None
        self._update_time = None
        self._lighting_option = None
        self._voice_option = "DND"
        self._state = None
        # 修复2：初始化时异步加载日出日落时间
        self._hass.loop.create_task(self.async_update())

    @property
    def native_value(self):
        return self._state

    @property
    def name(self):
        return self._attr_name  # 传感器名称

    @property
    def unique_id(self):
        return self._attr_unique_id  # 关键：确保每个传感器唯一

    async def async_update(self):
        """异步更新数据（确保时区正确）"""
        local_now = datetime.now(self.tz)
        self.tz = ZoneInfo(self._hass.config.time_zone) if self.tz is None else self.tz
        # 日期变更时重新获取日出日落
        if self._update_time is None or local_now.day != self._update_time.day:
            self._local_sun = await self.async_get_sun_time()
            self._update_time = local_now

        self._state = self._time_period()
        for index, option_list in enumerate(LIGHTING_OPTION):
            if self._state in option_list[0]:
                self._lighting_option = option_list[1]
                break
        else:
            self._lighting_option = "未知错误"
        for index, option_list in enumerate(VOICE_OPTION):
            if self._state in option_list[0]:
                self._voice_option = option_list[1]
                break
        else:
            self._voice_option = "DND"
        self._attr_extra_state_attributes = {
            "日出时间": self._local_sun.get("sunrise").strftime(FORMAT_DATETIME),
            "日落时间": self._local_sun.get("sunset").strftime(FORMAT_DATETIME),
            "开灯选项": self._lighting_option,
            "语音打扰": self._voice_option,
            "更新时间": local_now.strftime(FORMAT_DATETIME_SHORT),
            "时间区间": f'[{self.period[0]}, {self.period[1]})'
        }

    async def async_get_sun_time(self) -> dict:
        """异步获取日出日落时间（修复时区转换）"""
        today = datetime.now(self.tz).date()  # 用本地日期

        # 替换：用 async_add_executor_job 执行同步函数，避免阻塞事件循环
        sunrise_utc = await self._hass.async_add_executor_job(
            get_astral_event_date, self._hass, "sunrise", today
        )
        sunset_utc = await self._hass.async_add_executor_job(
            get_astral_event_date, self._hass, "sunset", today
        )

        # 正确将UTC时间转换为本地时区
        return {
            "sunrise": sunrise_utc.astimezone(self.tz),
            "sunset": sunset_utc.astimezone(self.tz)
        }

    def _time_period(self) -> str:
        """输出时间段（基于正确的本地时间）"""
        if not self._local_sun:  # 确保日出日落时间已加载
            return "初始化中"

        local_now = datetime.now(self.tz)
        for start, end, label in TIME_PERIODS:
            s = self.get_datetime(start, base_date=local_now)
            e = self.get_datetime(end, base_date=local_now)
            # 处理23:00 - 0:00
            e = e + timedelta(days=1) if e < s else e
            if s <= local_now < e:
                self.period = (s.strftime('%H:%M'), e.strftime('%H:%M'))
                return label
        self.period = ("-1", "-1")
        return "未知错误"

    def get_datetime(self, raw_dt: str, base_date: datetime = None) -> datetime:
        if raw_dt in self._local_sun.keys():
            return self._local_sun[raw_dt]
        if base_date is None:
            base_date = datetime.now(self.tz)
        dt = datetime.strptime(raw_dt, "%H:%M")
        return base_date.replace(hour=dt.hour, minute=dt.minute, second=0, microsecond=0)


class HolidaySensor(CoordinatorEntity, SensorEntity):
    """Sensor that reports current holiday"""
    _attr_icon = "mdi:firework"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = HOLIDAY_STATE_ENUM_VALUES

    def __init__(self, coordinator: DateCoordinator):
        super().__init__(coordinator)
        self.update_time = datetime.now()
        self._attr_unique_id = "holiday_sensor"  # 唯一标识
        self._attr_name = 'Holiday'

    @property
    def name(self):
        return self._attr_name  # 传感器名称

    @property
    def native_value(self):
        return self.coordinator.data["holidays"].get("state")

    @property
    def extra_state_attributes(self):
        return self.coordinator.data["holidays"].get("attributes")

    @property
    def unique_id(self):
        return self._attr_unique_id  # 关键：确保每个传感器唯一

    @callback
    def _handle_coordinator_update(self) -> None:
        """处理协调器数据更新。"""
        self.async_write_ha_state()


class AnniversarySensor(CoordinatorEntity, SensorEntity):
    _attr_icon = "mdi:candelabra-fire"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "天"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: DateCoordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = slugify(self.key)  # 唯一标识

    @property
    def name(self):
        data = self.coordinator.data
        if not data:
            return f'{self.key} loading...'
        try:
            return data["anniversaries"][self.key]["name"]
        except(KeyError, TypeError):
            return f'{self.key} Unknown'

    @property
    def native_value(self):
        data = self.coordinator.data
        if not data:
            return f'{self.key} loading...'
        try:
            return data["anniversaries"][self.key]["days"]
        except(KeyError, TypeError):
            return f'{self.key} Unknown'

    @property
    def unique_id(self):
        return self._attr_unique_id  # 关键：确保每个传感器唯一

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data["anniversaries"][self.key]
        if not data:
            return {}
        return {
            "纪念年数": data.get('age'),
            "纪念日期": data.get('date'),
            "到期日期": data.get('next_date'),
            "倒数天数": data.get('days_left'),
            "纪念名称": data.get('hint'),
            "更新时间": data.get('update_time')
        }
