"""Product types and counting units are independent.

Legacy categories remain accepted during the transition so saved structures,
old clients and creation snapshots remain readable without rewriting history.
New interfaces only offer JewelryType; they label legacy values as pending.
"""
from typing import Literal, get_args

JewelryType = Literal["耳饰", "项链", "手链", "戒指", "胸针", "发饰", "组合套装", "其他"]
LegacyJewelryCategory = Literal["套装", "单件", "单对"]
JewelryCategory = JewelryType | LegacyJewelryCategory
JewelryUnit = Literal["个", "对", "条", "枚", "件", "套", "卡"]

JEWELRY_TYPES = get_args(JewelryType)
LEGACY_JEWELRY_PREFIXES = {"套装": "SP-SET", "单件": "SP-PCS", "单对": "SP-PAIR"}
