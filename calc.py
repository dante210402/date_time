# -*- coding:utf-8 -*-
"""
@文档：calc.py
@版本：v1.0
@作者：LUOLin
@邮箱：maidouqq@163.com
@创建时间：2025/08/27 22:25
@文档说明：
v1.0:
"""
import json
import os.path
import logging
from typing import Literal
from lunar_python import Lunar, LunarMonth
from datetime import datetime
import requests
from .const import FORMAT_DATE, SOLAR_FESTIVAL, LUNAR_FESTIVAL

from homeassistant.util.json import load_json

_LOGGER = logging.getLogger(__name__)
BASE_DIR: str = os.path.dirname(__file__)


class RestDay:
    """
    每年查询一次，并将结果存于holiday.json中，保存一整年的节假日信息
    这个类目前只用于判断工作日、调休日
    """
    # 采用节假日api调用，建议每年12月份开始更新查询
    host_api: str = r'https://api.jiejiariapi.com/v1/holidays'
    path: str = os.path.join(BASE_DIR, 'holiday.json')
    has_json: bool = os.path.exists(path)
    holidays: dict = None
    holiday_dates: list[datetime] = None

    def __init__(self, now: datetime = None) -> None:
        if now is None:
            self.now: datetime = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            self.now: datetime = now.replace(hour=0, minute=0, second=0, microsecond=0)
        self.get_this_year_holidays()

    def get_this_year_holidays(self) -> dict:
        """
        获取本地节假日数据
        :return:
        """
        if self.has_json:
            with open(self.path, 'rb') as file:
                holidays_full = json.load(file)
            if str(self.now.year) in holidays_full.keys():
                self.holidays = holidays_full[str(self.now.year)]
                self.holiday_dates = [datetime.strptime(s, FORMAT_DATE) for s in self.holidays.keys()]
                return self.holidays

        self.holidays = self.update()
        self.holiday_dates = [datetime.strptime(s, FORMAT_DATE) for s in self.holidays.keys()]
        return self.holidays

    def update(self) -> dict:
        """
        更新holiday全年信息到holiday.json
        :return:
        """
        today = datetime.today()
        # 更新除夕
        _str = f'12{LunarMonth.fromYm(today.year, 12).toString()[-4:-2]}'
        if _str not in LUNAR_FESTIVAL.keys():
            _, value = LUNAR_FESTIVAL.popitem()
            LUNAR_FESTIVAL[_str] = value
        # api请求
        if self.holidays:
            url = f'{self.host_api}/{str(self.now.year + 1)}'
            response = requests.get(url=url)
            if response.status_code != 200:
                _LOGGER.info(f'{url.split("/")[-1]}年度的节假日信息api尚未更新')
                return {}
            json_data = {
                f'{str(self.now.year)}': self.holidays,
                f'{str(self.now.year + 1)}': response.json()
            }
        else:
            url = f'{self.host_api}/{str(self.now.year)}'
            response = requests.get(url=url)
            if response.status_code != 200:
                _LOGGER.warning(f'{url.split("/")[-1]}年度的节假日信息api更新失败')
                return {}
            self.holidays = response.json()
            json_data = {
                f'{str(self.now.year)}': self.holidays
            }
        with open(self.path, 'w', encoding='utf-8') as file:
            json.dump(json_data, file, ensure_ascii=False)

        # 把api获取到的字典直接传给返回值，用于get_this_year_holidays
        return response.json()

    def query(self, q_date: datetime = None) -> str:
        """
        获取指定天或今天的节假日信息
        :param q_date: 查询的指定日期，默认为None，如果是None，则指定为今天
        :return:
        """
        q_date = q_date.replace(hour=0, minute=0, second=0, microsecond=0) if q_date else self.now
        if q_date in self.holiday_dates:
            if self.holidays[q_date.strftime(FORMAT_DATE)]['isOffDay']:
                return '节假日'
            else:
                return '调休日'
        if q_date.weekday() in [5, 6]:
            return '休息日'
        else:
            return '工作日'



if __name__ == '__main__':
    pass
