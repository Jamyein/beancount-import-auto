"""
AI 分类异常定义模块

提供 AI 分类过程中可能遇到的异常类型
"""
import sys

sys.dont_write_bytecode = True


class AIClassificationError(Exception):
    """AI 分类错误基类"""
    pass


class RateLimitError(AIClassificationError):
    """API 速率限制错误"""
    pass
