import pytest

from instruments import registry
from instruments.tek_mso5 import TekMSO5

SCOPE_NAME = "示波器 - 泰克 5 系 (MSO54/56/58)"


def test_registry_lists_many_instrument_types():
    names = [item["名称"] for item in registry.INSTRUMENTS]
    assert len(names) >= 5
    assert any("示波器" in n for n in names)
    assert any("信号发生器" in n for n in names)
    assert any("源表" in n for n in names)


def test_exactly_one_available_and_it_is_tek_mso5():
    available = [i for i in registry.INSTRUMENTS if i["可用"]]
    assert len(available) == 1
    assert available[0]["名称"] == SCOPE_NAME
    assert available[0]["cls"] is TekMSO5


def test_get_by_name():
    item = registry.get_by_name(SCOPE_NAME)
    assert item["可用"] is True


def test_get_by_name_unknown_raises():
    with pytest.raises(KeyError):
        registry.get_by_name("不存在的仪器")
