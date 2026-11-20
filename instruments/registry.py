from instruments.tek_mso5 import TekMSO5

INSTRUMENTS = [
    {"名称": "示波器 - 泰克 5 系 (MSO54/56/58)", "类别": "示波器", "可用": True, "cls": TekMSO5},
    {"名称": "信号发生器 - 泰克 AFG (开发中)", "类别": "信号发生器", "可用": False, "cls": None},
    {"名称": "源表 - 吉时利 2400/2450 (开发中)", "类别": "源表", "可用": False, "cls": None},
    {"名称": "万用表 - 吉时利 DMM6500 (开发中)", "类别": "万用表", "可用": False, "cls": None},
    {"名称": "频谱分析仪 - (开发中)", "类别": "频谱分析仪", "可用": False, "cls": None},
    {"名称": "逻辑分析仪 - (开发中)", "类别": "逻辑分析仪", "可用": False, "cls": None},
]


def get_by_name(name):
    for item in INSTRUMENTS:
        if item["名称"] == name:
            return item
    raise KeyError(f"未知仪器: {name}")
