"""DRILL_REFACTOR_CODE_SMELL_DICT_BUILDER: long_function — последовательное построение dict.

Нет if/for/while блоков 3+ строк. Нет вложенных def. Вариант для LLM: extract helper
_build_config или группировка полей по смыслу.
"""

from typing import Any, Dict


def polygon_refactor_code_smell_dict_builder(env: str) -> Dict[str, Any]:
    """55+ строк: построение большого dict без extractable блоков."""
    config: Dict[str, Any] = {}
    config["env"] = env
    config["host"] = "localhost"
    config["port"] = 8080
    config["timeout"] = 30
    config["retries"] = 3
    config["cache_size"] = 1024
    config["log_level"] = "info"
    config["debug"] = False
    config["workers"] = 4
    config["threads"] = 8
    config["memory_limit"] = 512
    config["disk_limit"] = 1024
    config["max_connections"] = 100
    config["keepalive"] = 60
    config["compression"] = True
    config["ssl_enabled"] = False
    config["auth_required"] = True
    config["rate_limit"] = 1000
    config["batch_size"] = 64
    config["queue_size"] = 128
    config["shutdown_timeout"] = 10
    config["grace_period"] = 5
    config["health_check_interval"] = 15
    config["metrics_interval"] = 60
    config["backup_interval"] = 3600
    config["sync_interval"] = 300
    config["cleanup_interval"] = 86400
    config["expiry_days"] = 7
    config["max_file_size"] = 10485760
    config["buffer_size"] = 8192
    config["chunk_size"] = 4096
    config["block_size"] = 512
    config["page_size"] = 16
    config["pool_size"] = 32
    config["connection_timeout"] = 5
    config["read_timeout"] = 30
    config["write_timeout"] = 30
    config["idle_timeout"] = 120
    config["session_timeout"] = 3600
    config["cookie_max_age"] = 86400
    config["cors_origins"] = "*"
    config["allowed_hosts"] = ["*"]
    config["static_path"] = "/static"
    config["template_path"] = "/templates"
    # Padding to exceed MAX_FUNCTION_LINES (50)
    config["_1"] = 1
    config["_2"] = 2
    config["_3"] = 3
    config["_4"] = 4
    config["_5"] = 5
    config["_6"] = 6
    config["_7"] = 7
    config["_8"] = 8
    config["_9"] = 9
    config["_10"] = 10
    return config
