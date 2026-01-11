"""
日志系统配置模块

提供统一的日志配置和获取日志记录器的功能
"""
import sys
import logging
from pathlib import Path
from typing import Optional

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "importer.log"

# 日志格式
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'


def setup_logging(
    level: str = "INFO",
    log_to_file: bool = True,
    log_to_console: bool = True
) -> None:
    """
    配置全局日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: 是否记录到文件
        log_to_console: 是否输出到控制台
    """
    # 确保日志目录存在
    if log_to_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 转换日志级别
    log_level = getattr(logging, level.upper(), logging.INFO)

    # 配置根日志器
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # 清除现有处理器
    root_logger.handlers.clear()

    # 创建格式化器
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    # 添加文件处理器
    if log_to_file:
        file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 添加控制台处理器
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    获取日志记录器

    Args:
        name: 日志记录器名称（通常使用 __name__）

    Returns:
        配置好的日志记录器实例
    """
    return logging.getLogger(name)


def log_function_call(func):
    """
    函数调用日志装饰器

    记录函数的进入和退出，用于调试

    Args:
        func: 要装饰的函数

    Returns:
        包装后的函数
    """
    logger = get_logger(func.__module__)

    def wrapper(*args, **kwargs):
        logger.debug(f"调用函数: {func.__name__}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"函数返回: {func.__name__}")
            return result
        except Exception as e:
            logger.error(f"函数异常: {func.__name__} - {e}")
            raise

    return wrapper
