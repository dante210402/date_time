"""Config flow for Date and Time Sensor integration."""
import re
import voluptuous as vol
from datetime import datetime
from lunar_python import Lunar
from homeassistant import config_entries
from .const import DOMAIN


# 定义性别枚举验证器
DATE_TYPE_OPTIONS = ["阳历", "阴历"]
ANNIVERSARY_TYPE_OPTIONS = ["生日", "纪念日"]

class DateAndTimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for date and time Sensor."""

    VERSION = 1

    def __init__(self):
        self.anniversaries = []


    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        if user_input is not None:
            try:
                # 验证当前输入的纪念日信息
                validated_data = self._validate_input(user_input)
                # 将验证通过的纪念日添加到列表
                self.anniversaries.append(validated_data)

                # 跳转到“确认是否继续添加”的步骤
                return await self.async_step_confirm_add()

            except vol.Invalid as e:
                # 验证失败：显示错误并重新渲染表单
                errors["base"] = str(e)
        await self.async_step_confirm_add()
        # 定义配置表单的字段
        data_schema = vol.Schema({
            # 纪念日名称（必填）
            vol.Required("anniversary_name"): vol.All(
                str,
                vol.Length(min=1, max=50, msg="请输入纪念日/生日名称（可不写纪念日/生日几个字）")
            ),
            # 日期类型（下拉选择）
            vol.Required("date_type", default="阳历"): vol.In(
                DATE_TYPE_OPTIONS,
                msg="请选择日期类型（阳历或农历）"
            ),
            # 纪念类型（下拉选择）
            vol.Required("anniversary_type", default="生日"): vol.In(
                ANNIVERSARY_TYPE_OPTIONS,
                msg="请选纪念日/生日类型（生日或纪念日）"
            ),
            # 纪念日日期（必填）
            vol.Required("anniversary_date"): vol.All(
                str,
                vol.Length(min=8, max=8, msg="日期必须是8位数字"),
                msg="请输入8位数字日期（格式：yyyymmdd）"
            )
        })

        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "date_format_example": "示例：20231001（表示2023年10月1日）"
            }
        )

    async def async_step_confirm_add(self, user_input=None):
        """确认步骤：询问用户是否继续添加下一个纪念日"""
        # 1. 若用户提交了选择（点击“继续”或“结束”）
        if user_input is not None:
            # 判断用户选择：继续添加→返回user步骤；结束→创建配置条目
            if user_input["continue_add"]:
                return await self.async_step_user()  # 循环：重新进入填写表单步骤
            else:
                # 结束添加：将所有纪念日列表存入配置数据
                return self.async_create_entry(
                    title=f"纪念日/生日组（共{len(self.anniversaries)}个）",  # 配置条目标题
                    data={"anniversaries": self.anniversaries}  # 存储所有纪念日
                )

        hint = f"已添加{len(self.anniversaries)}个纪念日/生日，是否继续添加下一个？" if len(self.anniversaries) > 0 else "是否需要添加纪念日/生日？"
        # 2. 首次进入确认步骤：显示选择表单（继续/结束）
        return self.async_show_form(
            step_id="confirm_add",
            data_schema=vol.Schema({
                # 布尔选择：是否继续添加
                vol.Required("continue_add", default=True): bool
            }),
            description_placeholders={
                "current_count": str(len(self.anniversaries)),
                "hint": hint
            }
        )


    @staticmethod
    def _validate_input(user_input: dict) -> dict:
        """验证输入数据的自定义方法"""
        # 基础验证
        base_schema = vol.Schema({
            vol.Required("anniversary_name"): str,
            vol.Required("date_type"): vol.In(DATE_TYPE_OPTIONS),
            vol.Required("anniversary_type"): vol.In(ANNIVERSARY_TYPE_OPTIONS),
            vol.Required("anniversary_date"): str
        })
        data = base_schema(user_input)

        # 验证日期是否为纯数字
        date_value = data["anniversary_date"]
        year = int(date_value[0:4])
        month = int(date_value[4:6])
        day = int(date_value[6:8])
        if not re.match(r"^\d{8}$", date_value):
            raise vol.Invalid("日期必须是8位数字（仅包含0-9）")

        # 验证年月日是否合法
        if data["date_type"] == "阳历":
            try:
                # 验证用户输入并创建配置条目
                datetime(year, month, day)
            except ValueError as e:
                raise vol.Invalid(str(e))
        else:
            try:
                # 验证阴历日期是否真实存在
                # 注意：阴历月份和日期需符合农历规则（如腊月是12月，闰月会特殊处理）
                Lunar(year, month, day, 0, 0, 0)
            except Exception as e:
                raise vol.Invalid(f"阴历日期格式错误：{str(e)}")

        return data
