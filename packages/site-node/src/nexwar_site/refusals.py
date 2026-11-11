"""派单被拒的原因代号(W53 设计 D10):最常见的十来种拒绝带一个代号和一句英文。

站点的拒绝原话是中文(给人看的,写在派遣器各处);App、网页按代号给「去处理」的按钮,英文界面显示
英文那句(没代号的照旧显示原话)。代号按原话认 —— 不改派遣器里每一处 ``raise``。新加一种常见拒绝,
在 :data:`CODES` 里加一行,测试会看着每一行至少认得一句真原话。
"""

from __future__ import annotations

import re

#: (代号, 认原话的正则, 英文说明)。按顺序认,先中先算。
CODES: tuple[tuple[str, re.Pattern[str], str], ...] = tuple(
    (code, re.compile(rx), en) for code, rx, en in (
        ("held", r"叫停了", "This robot was stopped by someone. Tap Resume before sending it out."),
        ("zones_unconfirmed", r"区域修订尚未做安全确认",
         "No-go zones on this map haven't been confirmed yet. Until an administrator confirms "
         "them, robots won't go out on their own (remote control still works)."),
        ("supervision", r"要人现场监护",
         "This robot needs someone on site watching it. Turn on \"I'm supervising\" first."),
        ("teleop", r"正在遥控", "Someone is driving this robot by remote control right now."),
        ("offline", r"不在线|状态不新鲜|未挂上派遣客户端",
         "This robot is offline or hasn't reported in recently."),
        # 易用性第 6 轮 A6-02:未就绪按哪一样分开说(原来一律「还在启动、充电或站起来」);急停最要紧
        ("estop", r"未就绪.*(estop|急停)", "The e-stop on this robot is pressed. Release it, "
         "then dispatch again."),
        ("not_localized", r"未就绪.*(loc|定位不可用)", "This robot doesn't know where it is. "
         "Set its position on the map first."),
        ("no_control", r"未就绪.*(control|控制权)", "Something else has control of this robot "
         "(for example the handheld remote). Hand control back to the site, then dispatch again."),
        ("not_standing", r"未就绪.*(motion|没站起来)", "This robot isn't standing (it may be "
         "sitting or lying down). Make it stand up, then dispatch again."),
        ("not_ready", r"未就绪", "This robot isn't ready yet (still starting up, charging or "
         "standing up)."),
        ("map_mismatch", r"加载的是|加载的地图|地图版本|重建过|未上报已加载的地图",
         "This route was drawn on a different map (or an older version) than the one the robot "
         "has loaded."),
        ("obstacles", r"避障不可用", "Obstacle avoidance on this robot isn't working right now."),
        ("clock", r"钟差", "This robot's clock doesn't match the site's yet. Wait a minute and "
         "try again."),
        ("zones_sync", r"区域尚未同步|不认区域|不守区域|无法规划|运行的配置与站点登记的不匹配",
         "This robot hasn't received the latest zones and maps yet."),
        ("deterring", r"正在驱离", "This robot is busy deterring someone."),
        ("manual_only", r"只许手动派", "This robot is set to manual dispatch only."),
        ("heading", r"头尾方向", "This robot's front/back direction isn't set correctly."),
        ("unreachable", r"无法到达|无法到达", "The robot can't reach one of these points."),
        # 日志设计 第 7 条:剩下常见的几种也给码
        ("busy", r"正在执行", "This robot is busy with another task."),
        ("unregistered", r"没有登记过|登记已吊销或过期",
         "This robot isn't registered on this site (or was removed)."),
        ("bad_mission", r"不成形|个航点|字节",
         "This route can't be sent as it is (too many points, "
         "too large or malformed)."),
    ))


#: 未就绪的哪一样 → 原话里的说法(按要紧的先说)。
_NOT_READY = (("estop_clear", "急停按着"), ("loc_ok", "定位不可用"),
              ("control", "控制权不在站点(手柄或别的程序在控制)"),
              ("motion", "没站起来(蹲着、趴着,或运动模式没就绪)"))


def not_ready_text(robot_id: str, keys: list[str] | tuple[str, ...]) -> str:
    """派遣器的「未就绪」原话:写人话,不写 ``motion`` 这种字段名(A6-02)。"""
    words = [w for k, w in _NOT_READY if k in keys] + [k for k in keys
                                                       if k not in dict(_NOT_READY)]
    return f"{robot_id} 未就绪:{'、'.join(words)}"


def reason_code(text: str) -> tuple[str, str] | None:
    """原话 → ``(代号, 英文说明)``;认不出 → ``None``。"""
    for code, rx, en in CODES:
        if rx.search(text or ""):
            return code, en
    return None


def extra_for(text: str) -> dict[str, str]:
    """给 409 回复补的字段:代号、英文说明、错误码(日志设计 第 7 条);认不出的只带
    ``0x0213 dispatch.refused``。"""
    from nexwar_contract import errcodes
    got = reason_code(text)
    if not got:
        return errcodes.wire("dispatch.refused")
    return {"reason_code": got[0], "reason_en": got[1]} | errcodes.wire(errcodes.REFUSAL[got[0]])
