import json
from datetime import datetime


class ConfigError(Exception):
    """配置文件读写或格式错误。"""


REQUIRED_KEYS = ("仪器类型", "型号", "保存时间")


def save(path, config):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
    except OSError as exc:
        raise ConfigError(f"写配置文件失败: {exc}") from exc


def load(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"读配置文件失败: {exc}") from exc
    if not isinstance(config, dict):
        raise ConfigError("配置文件顶层必须是 JSON 对象")
    missing = [k for k in REQUIRED_KEYS if k not in config]
    if missing:
        raise ConfigError(f"配置文件缺少必需键: {', '.join(missing)}")
    return config


def default_filename(model):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{model}_{now}.json"
