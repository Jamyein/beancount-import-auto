"""
导入器抽象基类模块

定义所有账单导入器必须实现的基础接口
"""
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Dict, Any, Type, Optional
from pathlib import Path
from decimal import Decimal, InvalidOperation
from datetime import date, datetime

# 导入日志系统
from logger_config import get_logger

logger = get_logger(__name__)

# 常量定义
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB文件大小限制
MIN_DATE = date(2000, 1, 1)
MAX_AMOUNT = Decimal('100000000')  # 1亿元


@dataclass
class Transaction:
    """标准化交易记录

    所有导入器都必须返回此格式的交易记录
    """
    date: date
    payee: str
    amount: Decimal
    raw_category: str
    raw_account: str
    note: str = ""
    source: str = ""
    status: str = "success"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（向后兼容）"""
        return {
            "date": self.date,
            "payee": self.payee,
            "amount": self.amount,
            "note": self.note,
            "raw_category": self.raw_category,
            "raw_account": self.raw_account,
            "source": self.source,
            "status": self.status
        }


class ImportError(Exception):
    """导入过程错误基类"""
    pass


class TransactionValidationError(ImportError):
    """交易记录验证失败"""
    pass


class FileFormatError(ImportError):
    """文件格式识别失败"""
    pass


class FileSizeError(ImportError):
    """文件大小超限"""
    pass


class BaseImporter(ABC):
    """所有导入器的抽象基类

    子类必须实现以下方法：
        - supports_file(): 判断是否支持该文件
        - extract_transactions(): 提取交易记录

    子类可以重写以下方法：
        - validate_transaction(): 自定义验证逻辑
    """

    PLATFORM_NAME: str = ""
    SUPPORTED_EXTENSIONS: List[str] = []
    ENCODING: str = "utf-8"
    ENCODINGS: List[str] = ["utf-8", "utf-8-sig", "gbk", "gb18030"]

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化导入器

        Args:
            config: 配置字典（可选）
        """
        self.config = config or {}
        self.logger = get_logger(self.__class__.__name__)

    @abstractmethod
    def supports_file(self, path: Path) -> bool:
        """判断该导入器是否支持给定文件

        Args:
            path: 文件路径

        Returns:
            是否支持该文件
        """
        pass

    @abstractmethod
    def extract_transactions(self, path: Path) -> List[Transaction]:
        """从文件中提取交易记录

        Args:
            path: 文件路径

        Returns:
            交易记录列表

        Raises:
            FileFormatError: 文件格式不正确
            ImportError: 导入过程失败
        """
        pass

    def validate_transaction(self, tx: Transaction) -> bool:
        """验证单条交易记录

        执行以下验证：
        - 必要字段检查
        - 金额范围检查
        - 日期范围检查

        Args:
            tx: 交易记录

        Returns:
            是否通过验证

        Raises:
            TransactionValidationError: 验证失败
        """
        # 必要字段验证
        required_fields = ['date', 'payee', 'amount']
        for field in required_fields:
            if not getattr(tx, field):
                self.logger.warning(f"交易记录缺少必要字段: {field}")
                raise TransactionValidationError(f"缺少字段: {field}")

        # 金额验证（必须为正数，小于1亿）
        if tx.amount <= 0:
            self.logger.warning(f"无效的交易金额: {tx.amount}")
            raise TransactionValidationError(f"金额必须大于0: {tx.amount}")
        if tx.amount > MAX_AMOUNT:
            self.logger.warning(f"金额异常（超过1亿）: {tx.amount}")
            raise TransactionValidationError(f"金额超过上限: {tx.amount}")

        # 日期验证（2000年-今天）
        if tx.date < MIN_DATE:
            self.logger.warning(f"日期过早: {tx.date}")
            raise TransactionValidationError(f"日期过早: {tx.date}")
        if tx.date > date.today():
            self.logger.warning(f"日期为未来: {tx.date}")
            raise TransactionValidationError(f"日期为未来: {tx.date}")

        return True

    def validate_file_size(self, path: Path) -> None:
        """验证文件大小

        Args:
            path: 文件路径

        Raises:
            FileSizeError: 文件过大
        """
        try:
            file_size = path.stat().st_size
            if file_size > MAX_FILE_SIZE:
                self.logger.error(
                    f"文件过大: {file_size / 1024 / 1024:.2f}MB "
                    f"(限制: {MAX_FILE_SIZE / 1024 / 1024}MB)"
                )
                raise FileSizeError(f"文件大小超限: {path}")
        except OSError as e:
            self.logger.error(f"无法获取文件大小: {path} - {e}")
            raise ImportError(f"文件访问失败: {e}")

    def parse_amount(self, amount_str: str, line_num: int = 0) -> Decimal:
        """统一金额解析

        Args:
            amount_str: 金额字符串
            line_num: 行号（用于日志）

        Returns:
            解析后的金额

        Raises:
            TransactionValidationError: 金额格式无效
        """
        try:
            cleaned = (amount_str
                      .replace("¥", "")
                      .replace("￥", "")
                      .replace("$", "")
                      .replace(" ", "")
                      .replace(",", ""))
            return abs(Decimal(cleaned))
        except (ValueError, InvalidOperation, AttributeError) as e:
            self.logger.error(f"第{line_num}行金额解析失败: '{amount_str}' - {e}")
            raise TransactionValidationError(f"无效金额格式: {amount_str}")

    def parse_date(self, date_str: str, line_num: int = 0) -> date:
        """统一日期解析

        尝试多种常见日期格式

        Args:
            date_str: 日期字符串
            line_num: 行号（用于日志）

        Returns:
            解析后的日期

        Raises:
            TransactionValidationError: 日期格式无效
        """
        import pandas as pd

        date_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y%m%d',
            '%Y年%m月%d日',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
        ]

        # 首先尝试 pandas 的智能解析
        try:
            date_obj = pd.to_datetime(date_str, errors='coerce')
            if not pd.isna(date_obj):
                parsed_date = date_obj.date()
                self.validate_date_range(parsed_date)
                return parsed_date
        except Exception:
            pass

        # 回退到手动解析
        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(date_str, fmt).date()
                self.validate_date_range(parsed_date)
                return parsed_date
            except ValueError:
                continue

        self.logger.error(f"第{line_num}行日期解析失败: '{date_str}'")
        raise TransactionValidationError(f"无效日期格式: {date_str}")

    def validate_date_range(self, date_val: date) -> None:
        """验证日期范围

        Args:
            date_val: 要验证的日期

        Raises:
            TransactionValidationError: 日期超出范围
        """
        if date_val < MIN_DATE:
            raise TransactionValidationError(f"日期过早: {date_val}")
        if date_val > date.today():
            raise TransactionValidationError(f"日期为未来: {date_val}")

    def safe_get(self, value: Any, default: str = "") -> str:
        """安全获取字符串并清理

        Args:
            value: 输入值
            default: 默认值

        Returns:
            清理后的字符串
        """
        import pandas as pd

        if value is None:
            return default

        # 处理 pandas NA
        try:
            if pd.isna(value):
                return default
        except TypeError:
            pass

        return str(value).strip()

    def escape_beancount_string(self, s: str) -> str:
        """转义 Beancount 特殊字符

        Args:
            s: 原始字符串

        Returns:
            转义后的字符串
        """
        return s.replace('"', '""').replace('\n', ' ').replace('\r', '')


class ImportRegistry:
    """导入器注册表

    用于动态注册和管理导入器实现
    """

    def __init__(self):
        self._importers: List[Type[BaseImporter]] = []
        self.logger = get_logger(self.__class__.__name__)

    def register(self, importer_class: Type[BaseImporter]):
        """注册一个导入器实现

        Args:
            importer_class: 导入器类（必须是 BaseImporter 的子类）

        Returns:
            导入器类（支持装饰器用法）

        Raises:
            ValueError: 不是 BaseImporter 的子类
        """
        if not issubclass(importer_class, BaseImporter):
            raise ValueError("必须为 BaseImporter 的子类")
        self._importers.append(importer_class)
        self.logger.info(f"注册导入器: {importer_class.PLATFORM_NAME}")
        return importer_class

    def get_matching_importer(
        self,
        path: Path,
        config: Optional[Dict[str, Any]] = None
    ) -> BaseImporter:
        """查找支持该文件的导入器

        Args:
            path: 文件路径
            config: 配置字典（可选）

        Returns:
            匹配的导入器实例

        Raises:
            FileFormatError: 未找到支持该文件的导入器
        """
        for importer_cls in self._importers:
            importer = importer_cls(config)
            if importer.supports_file(path):
                self.logger.info(f"匹配到导入器: {importer.PLATFORM_NAME}")
                return importer

        self.logger.error(f"未找到支持该文件的导入器: {path.name}")
        raise FileFormatError(f"未找到支持该文件的导入器: {path}")

    def list_supported_formats(self) -> List[str]:
        """列出支持的文件格式

        Returns:
            支持的文件扩展名列表
        """
        formats = []
        for importer_cls in self._importers:
            formats.extend(importer_cls.SUPPORTED_EXTENSIONS)
        return list(set(formats))

    def list_platforms(self) -> List[str]:
        """列出的所有支持的平台

        Returns:
            平台名称列表
        """
        return [imp.PLATFORM_NAME for imp in self._importers]


# 全局导入器注册表
registry = ImportRegistry()

# 禁止生成 .pyc 文件
sys.dont_write_bytecode = True
