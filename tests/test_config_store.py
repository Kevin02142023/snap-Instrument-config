import json

import pytest

from core import config_store


def test_save_load_roundtrip(tmp_path):
    config = {
        "仪器类型": "示波器",
        "型号": "泰克5系",
        "保存时间": "2026-10-12 15:30:00",
        "示波器": {"1通道参数": {"电压每格": "1.0E+00"}},
    }
    path = tmp_path / "cfg.json"
    config_store.save(path, config)
    assert config_store.load(path) == config


def test_save_writes_utf8_chinese(tmp_path):
    path = tmp_path / "cfg.json"
    config_store.save(path, {"仪器类型": "示波器"})
    text = path.read_text(encoding="utf-8")
    assert '"仪器类型": "示波器"' in text


def test_load_invalid_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(config_store.ConfigError):
        config_store.load(path)


def test_load_missing_keys_raises(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps({"仪器类型": "示波器"}), encoding="utf-8")
    with pytest.raises(config_store.ConfigError, match="型号"):
        config_store.load(path)


def test_load_non_object_raises(tmp_path):
    path = tmp_path / "cfg.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(config_store.ConfigError):
        config_store.load(path)


def test_load_non_utf8_file_raises(tmp_path):
    path = tmp_path / "gbk.json"
    path.write_bytes('{"仪器类型": "示波器"}'.encode("gbk"))
    with pytest.raises(config_store.ConfigError):
        config_store.load(path)


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(config_store.ConfigError):
        config_store.load(tmp_path / "不存在.json")


def test_default_filename_format():
    name = config_store.default_filename("MSO54")
    assert name.startswith("MSO54_")
    assert name.endswith(".json")
    assert "_" in name[len("MSO54_"):-len(".json")]
