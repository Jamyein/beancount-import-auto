"""
配置管理器模块

提供统一的配置加载、验证和管理功能
"""
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from logger_config import get_logger

logger = get_logger(__name__)


@dataclass
class OpenAIConfig:
    """OpenAI/DeepSeek API 配置"""
    api_key: str = ""
    api_base: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"


@dataclass
class PlatformConfig:
    """平台特定配置"""
    keywords: List[str] = field(default_factory=list)
    extensions: List[str] = field(default_factory=list)
    field_mappings: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class AppConfig:
    """主应用配置"""
    # OpenAI 配置
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)

    # 文件路径
    main_bean_file: str = "main.beancount"
    monthly_dir: str = "data"
    config_dir: str = "config"

    # 账户映射
    asset_mapping: Dict[str, str] = field(default_factory=dict)
    my_accounts: List[str] = field(default_factory=list)

    # 平台配置
    platforms: Dict[str, PlatformConfig] = field(default_factory=dict)

    # 性能限制
    max_file_size: int = 10 * 1024 * 1024  # 10MB

    # 日志配置
    log_level: str = "INFO"
    log_to_file: bool = True
    log_to_console: bool = True

    @classmethod
    def load(cls, config_path: Path) -> "AppConfig":
        """加载配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            配置对象

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        logger.info(f"加载配置文件: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 验证配置
        cls._validate_config(data)

        # 构建配置对象
        openai_cfg = OpenAIConfig(**data.get("openai", {}))

        # 平台配置
        platforms_data = data.get("platforms", {})
        platforms = {
            name: PlatformConfig(
                keywords=cfg.get("keywords", []),
                extensions=cfg.get("extensions", []),
                field_mappings=cfg.get("field_mappings", {})
            )
            for name, cfg in platforms_data.items()
        }

        return cls(
            openai=openai_cfg,
            main_bean_file=data.get("main_bean_file", "main.beancount"),
            monthly_dir=data.get("monthly_dir", "data"),
            config_dir=data.get("config_dir", "config"),
            asset_mapping=data.get("asset_mapping", {}),
            my_accounts=data.get("my_accounts", []),
            platforms=platforms,
            max_file_size=data.get("max_file_size", 10 * 1024 * 1024),
            log_level=data.get("log_level", "INFO"),
            log_to_file=data.get("log_to_file", True),
            log_to_console=data.get("log_to_console", True)
        )

    @staticmethod
    def _validate_config(data: Dict[str, Any]) -> None:
        """验证配置数据

        Args:
            data: 配置字典

        Raises:
            ValueError: 配置验证失败
        """
        # 验证 OpenAI 配置
        if "openai" not in data:
            raise ValueError("配置缺少 'openai' 节点")

        openai_cfg = data["openai"]
        required_openai_fields = ["api_key", "api_base", "model"]
        for field in required_openai_fields:
            if field not in openai_cfg:
                raise ValueError(f"OpenAI 配置缺少必需字段: {field}")

        # 验证 api_base 为有效的 URI
        api_base = openai_cfg.get("api_base", "")
        if not (api_base.startswith("http://") or api_base.startswith("https://")):
            raise ValueError(f"api_base 必须是有效的 URL: {api_base}")

        # 验证账户映射
        if "asset_mapping" in data:
            asset_mapping = data["asset_mapping"]
            if not isinstance(asset_mapping, dict):
                raise ValueError("'asset_mapping' 必须是字典类型")

        # 验证账户列表
        if "my_accounts" in data:
            my_accounts = data["my_accounts"]
            if not isinstance(my_accounts, list):
                raise ValueError("'my_accounts' 必须是列表类型")

    def save(self, config_path: Path) -> None:
        """保存配置到文件

        Args:
            config_path: 配置文件路径
        """
        data = {
            "openai": {
                "api_key": self.openai.api_key,
                "api_base": self.openai.api_base,
                "model": self.openai.model
            },
            "main_bean_file": self.main_bean_file,
            "monthly_dir": self.monthly_dir,
            "config_dir": self.config_dir,
            "asset_mapping": self.asset_mapping,
            "my_accounts": self.my_accounts,
            "platforms": {
                name: {
                    "keywords": cfg.keywords,
                    "extensions": cfg.extensions,
                    "field_mappings": cfg.field_mappings
                }
                for name, cfg in self.platforms.items()
            },
            "max_file_size": self.max_file_size,
            "log_level": self.log_level,
            "log_to_file": self.log_to_file,
            "log_to_console": self.log_to_console
        }

        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 原子性写入
        temp_path = config_path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        temp_path.replace(config_path)

        logger.info(f"配置已保存: {config_path}")

    def get_platform_config(self, platform_name: str) -> Optional[PlatformConfig]:
        """获取平台配置

        Args:
            platform_name: 平台名称

        Returns:
            平台配置对象，不存在返回 None
        """
        return self.platforms.get(platform_name)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式

        Returns:
            配置字典
        """
        return {
            "openai": {
                "api_key": self.openai.api_key,
                "api_base": self.openai.api_base,
                "model": self.openai.model
            },
            "main_bean_file": self.main_bean_file,
            "monthly_dir": self.monthly_dir,
            "config_dir": self.config_dir,
            "asset_mapping": self.asset_mapping,
            "my_accounts": self.my_accounts,
            "platforms": {
                name: {
                    "keywords": cfg.keywords,
                    "extensions": cfg.extensions,
                    "field_mappings": cfg.field_mappings
                }
                for name, cfg in self.platforms.items()
            },
            "max_file_size": self.max_file_size,
            "log_level": self.log_level,
            "log_to_file": self.log_to_file,
            "log_to_console": self.log_to_console
        }


class ConfigManager:
    """配置管理器

    单例模式，提供全局配置访问
    """

    _instance: Optional["ConfigManager"] = None
    _config: Optional[AppConfig] = None

    def __new__(cls) -> "ConfigManager":
        """实现单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: Path) -> AppConfig:
        """加载配置

        Args:
            config_path: 配置文件路径

        Returns:
            配置对象
        """
        self._config = AppConfig.load(config_path)
        return self._config

    def get_config(self) -> AppConfig:
        """获取当前配置

        Returns:
            配置对象

        Raises:
            RuntimeError: 配置未加载
        """
        if self._config is None:
            raise RuntimeError("配置未加载，请先调用 load() 方法")
        return self._config

    def is_loaded(self) -> bool:
        """检查配置是否已加载

        Returns:
            配置是否已加载
        """
        return self._config is not None


def get_config(config_path: Optional[Path] = None) -> AppConfig:
    """获取配置的便捷函数

    Args:
        config_path: 配置文件路径（可选），默认为 config/config.json

    Returns:
        配置对象
    """
    manager = ConfigManager()

    if config_path is None:
        # 默认配置文件路径
        base_dir = Path(__file__).parent.parent
        config_path = base_dir / "config" / "config.json"

    if not manager.is_loaded():
        manager.load(config_path)

    return manager.get_config()
