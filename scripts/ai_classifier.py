"""
AI 分类核心模块（优化版）

重构版本：
- 添加重试机制（使用 tenacity）
- 改进异常处理
- 支持配置化
- 添加缓存机制优化
"""
import sys
import json
from pathlib import Path
from typing import Dict, Set, List, Optional, Any

# 导入 OpenAI SDK 和 httpx（条件化导入）
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

# httpx 总是尝试导入，因为两种模式都可能需要
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False
    # 如果 OpenAI 和 httpx 都不可用，才报错
    if not HAS_OPENAI:
        raise ImportError("OpenAI SDK 和 httpx 都不可用，至少需要安装其中一个")

from logger_config import get_logger
from config_manager import AppConfig

logger = get_logger(__name__)

# 禁止生成 .pyc 文件
sys.dont_write_bytecode = True


class AIClassificationError(Exception):
    """AI 分类错误"""
    pass


class RateLimitError(AIClassificationError):
    """API 速率限制错误"""
    pass


class ClassificationCache:
    """分类缓存管理

    提供线程安全的缓存读写，支持原子性写入
    """

    def __init__(self, cache_path: Path):
        self.cache_path = cache_path
        self.mapping: Dict[str, str] = self._load()

    def _load(self) -> Dict[str, str]:
        """加载缓存"""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"加载缓存: {len(data)} 条记录")
                    return data
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"⚠️  加载缓存失败，使用空缓存: {e}")
        return {}

    def save(self) -> None:
        """安全保存缓存（原子性写入）"""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.cache_path.with_suffix('.tmp')

            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(self.mapping, f, ensure_ascii=False, indent=2)

            # 原子性替换（Windows 和 Unix 兼容）
            temp_path.replace(self.cache_path)

            logger.info(f"保存缓存: {len(self.mapping)} 条记录")

        except Exception as e:
            logger.error(f"❌ 保存缓存失败: {e}")
            # 不抛出异常，避免影响主流程

    def get(self, key: str) -> Optional[str]:
        """获取缓存的分类

        Args:
            key: 缓存键（格式："payee|raw_category"）

        Returns:
            缓存的账户名，未找到返回 None
        """
        return self.mapping.get(key)

    def set(self, key: str, value: str) -> None:
        """设置缓存

        Args:
            key: 缓存键
            value: 账户名
        """
        self.mapping[key] = value

    def contains(self, key: str) -> bool:
        """检查缓存中是否存在该键

        Args:
            key: 缓存键

        Returns:
            是否存在
        """
        return key in self.mapping

    def clear(self) -> None:
        """清空缓存"""
        self.mapping.clear()
        logger.info("缓存已清空")


class AIClassifier:
    """AI 分类器（带重试和降级）"""

    def __init__(self, config: AppConfig):
        """初始化 AI 分类器

        Args:
            config: 应用配置对象
        """
        self.config = config
        self.openai_cfg = config.openai

        if HAS_OPENAI:
            # 使用 OpenAI SDK
            self.client = OpenAI(
                api_key=self.openai_cfg.api_key,
                base_url=self.openai_cfg.api_base
            )
            self.use_httpx = False
            logger.info("使用 OpenAI SDK")
        elif HAS_HTTPX:
            # 使用 httpx（OpenAI SDK 不可用）
            self.client = httpx.Client(
                base_url=self.openai_cfg.api_base,
                headers={"Authorization": f"Bearer {self.openai_cfg.api_key}"},
                timeout=30.0
            )
            self.use_httpx = True
            logger.info("使用 httpx（OpenAI SDK 不可用）")
        else:
            raise RuntimeError("OpenAI SDK 和 httpx 都不可用")

        self.cache: Optional[ClassificationCache] = None

    def set_cache(self, cache: ClassificationCache) -> None:
        """设置缓存管理器

        Args:
            cache: 缓存对象
        """
        self.cache = cache

    def classify(
        self,
        payee: str,
        raw_category: str,
        note: str,
        raw_account: str,
        allowed_accounts: Optional[Set[str]] = None
    ) -> str:
        """分类主逻辑（带缓存和重试）

        Args:
            payee: 商户名称
            raw_category: 原始分类
            note: 交易备注
            raw_account: 原始账户
            allowed_accounts: 允许的账户列表

        Returns:
            分类结果（账户名）

        Raises:
            AIClassificationError: 分类失败
        """
        # 1. 检查缓存
        if self.cache:
            key = f"{payee.strip()}|{raw_category.strip()}"
            cached_account = self.cache.get(key)
            if cached_account:
                logger.debug(f"命中缓存: {key} -> {cached_account}")
                return cached_account

        # 2. 调用 AI 分类
        suggested = self._ai_classify_with_retry(
            payee=payee,
            raw_category=raw_category,
            note=note,
            allowed_accounts=allowed_accounts or set(self.config.my_accounts)
        )

        # 3. 人工确认
        final_account = self._confirm_account(
            suggested=suggested,
            payee=payee,
            allowed_accounts=allowed_accounts or set(self.config.my_accounts)
        )

        # 4. 保存到缓存
        if self.cache:
            key = f"{payee.strip()}|{raw_category.strip()}"
            self.cache.set(key, final_account)

        return final_account

    def _ai_classify_with_retry(
        self,
        payee: str,
        raw_category: str,
        note: str,
        allowed_accounts: Set[str]
    ) -> str:
        """AI 分类（带重试机制）

        Args:
            payee: 商户名称
            raw_category: 原始分类
            note: 交易备注
            allowed_accounts: 允许的账户列表

        Returns:
            AI 建议的账户名

        Raises:
            AIClassificationError: 分类失败（所有重试后）
        """
        from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

        def _get_retry_exceptions():
            """获取需要重试的异常类型"""
            exceptions = []
            if HAS_HTTPX:
                exceptions.extend([httpx.TimeoutException, httpx.NetworkError])
            # OpenAI SDK 的异常类型
            if HAS_OPENAI:
                try:
                    from openai import APITimeoutError, APIConnectionError
                    exceptions.extend([APITimeoutError, APIConnectionError])
                except ImportError:
                    pass
            return tuple(exceptions) if exceptions else (Exception,)

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=60),
            retry=retry_if_exception_type(_get_retry_exceptions()),
            reraise=True
        )
        def _classify() -> str:
            return self._ai_classify(
                payee=payee,
                raw_category=raw_category,
                note=note,
                allowed_accounts=allowed_accounts
            )

        try:
            return _classify()
        except Exception as e:
            logger.error(f"❌ AI 分类失败（已重试3次）: {e}")
            raise AIClassificationError(f"AI 分类失败: {e}") from e

    def _ai_classify(
        self,
        payee: str,
        raw_category: str,
        note: str,
        allowed_accounts: Set[str]
    ) -> str:
        """调用 AI API 进行分类

        Args:
            payee: 商户名称
            raw_category: 原始分类
            note: 交易备注
            allowed_accounts: 允许的账户列表

        Returns:
            AI 建议的账户名
        """
        accounts_text = "\n".join(sorted(list(allowed_accounts)))

        prompt = self._build_prompt(
            payee=payee,
            raw_category=raw_category,
            note=note,
            accounts=accounts_text
        )

        try:
            if self.use_httpx:
                # 使用 httpx
                response = self.client.post(
                    "/chat/completions",
                    json={
                        "model": self.openai_cfg.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 100
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                result = response.json()
                suggested = result["choices"][0]["message"]["content"].strip()
            else:
                # 使用 OpenAI SDK
                resp = self.client.chat.completions.create(
                    model=self.openai_cfg.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=100
                )
                suggested = resp.choices[0].message.content.strip()

            logger.debug(f"AI 建议账户: {suggested}")
            return self._validate_and_clean(suggested, allowed_accounts)

        except Exception as e:
            # 条件化异常处理
            if HAS_HTTPX and isinstance(e, httpx.HTTPStatusError):
                if e.response.status_code == 429:
                    raise RateLimitError(f"API 速率限制: {e}")
                logger.error(f"HTTP 错误: {e}")
                raise AIClassificationError(f"API 调用失败: {e}") from e
            elif HAS_HTTPX and isinstance(e, httpx.TimeoutException):
                logger.error(f"API 超时: {e}")
                raise AIClassificationError(f"API 调用超时: {e}") from e
            else:
                # OpenAI SDK 或其他异常处理
                logger.error(f"AI 接口异常: {e}")
                raise AIClassificationError(f"AI 分类失败: {e}") from e

    def _build_prompt(
        self,
        payee: str,
        raw_category: str,
        note: str,
        accounts: str
    ) -> str:
        """构建 AI 提示词

        Args:
            payee: 商户名称
            raw_category: 原始分类
            note: 交易备注
            accounts: 可选账户列表

        Returns:
            提示词字符串
        """
        return f"""
你是一个专业的 Beancount 记账分类助手。

【已知信息】
1. 账单原始分类（最重要参考）：{raw_category}
2. 商户名称：{payee}
3. 商品信息：{note}

【待选账户列表】
{accounts}

【任务】
请从上述"待选账户列表"中选择一个最合适的账户。

【规则 - 必须遵守】
1. 必须优先参考"账单原始分类"进行逻辑推断。
2. 必须【只能】从提供的"待选账户列表"中选择。
3. 如果无法确定，请选择列表中的支出类账户（Expenses: 开头）。
4. 只能返回账户名本身，不要包含任何解释、标点或多余文字。
"""

    def _validate_and_clean(self, suggested: str, allowed_accounts: Set[str]) -> str:
        """验证并清理 AI 返回的账户名

        Args:
            suggested: AI 建议的账户名
            allowed_accounts: 允许的账户列表

        Returns:
            验证后的账户名

        Raises:
            AIClassificationError: 验证失败
        """
        # 清理建议（去除引号、句号等）
        cleaned = suggested.strip().replace('"', '').replace('。', '').replace('，', '')

        # 验证是否在允许列表中
        if cleaned in allowed_accounts:
            return cleaned

        # 如果不在允许列表中，返回第一个允许的账户
        logger.warning(f"AI 返回的账户不在允许列表中: {cleaned}")
        if allowed_accounts:
            # 优先返回支出类账户
            for account in sorted(allowed_accounts):
                if account.startswith("Expenses:"):
                    logger.warning(f"降级使用默认支出账户: {account}")
                    return account
            # 如果没有支出类，返回第一个
            default_account = sorted(allowed_accounts)[0]
            logger.warning(f"降级使用默认账户: {default_account}")
            return default_account

        raise AIClassificationError("没有可用的账户")

    def _confirm_account(
        self,
        suggested: str,
        payee: str,
        allowed_accounts: Set[str]
    ) -> str:
        """人工确认账户

        Args:
            suggested: AI 建议的账户
            payee: 商户名称
            allowed_accounts: 允许的账户列表

        Returns:
            用户确认的账户
        """
        logger.info(f"🆕 发现新商户：{payee}")
        logger.info(f"🤖 AI 建议账户：{suggested}")

        # 显示前 10 个允许的账户作为提示
        logger.info("合法账户选项（前10个）：")
        for acc in sorted(list(allowed_accounts))[:10]:
            logger.info(f"  - {acc}")

        # 交互式确认
        while True:
            try:
                user_input = input("请输入账户（回车确认建议 / 手动修改）：\n> ").strip()

                final = user_input if user_input else suggested

                if final in allowed_accounts:
                    logger.info(f"✅ 确认账户：{final}")
                    return final
                else:
                    logger.error(f"❌ 非法账户：'{final}'，该账户不在允许列表中")

            except KeyboardInterrupt:
                logger.info("\n⚠️  用户取消，使用 AI 建议")
                return suggested
            except EOFError:
                logger.info("\n⚠️  输入结束，使用 AI 建议")
                return suggested


def create_classifier(config: AppConfig) -> AIClassifier:
    """创建 AI 分类器的工厂函数

    Args:
        config: 应用配置

    Returns:
        AI 分类器实例
    """
    return AIClassifier(config)


def create_cache(cache_path: Path) -> ClassificationCache:
    """创建缓存管理器的工厂函数

    Args:
        cache_path: 缓存文件路径

    Returns:
        缓存管理器实例
    """
    return ClassificationCache(cache_path)


# 兼容性：保持与原代码相同的接口（向后兼容）
class MemoryBrain:
    """向后兼容的内存大脑类

    保持与原 importer_main.py 代码的兼容性
    """

    def __init__(self):
        """初始化（使用默认配置）"""
        from config_manager import get_config
        self.config = get_config()
        self.classifier = create_classifier(self.config)
        self.cache = create_cache(Path("config/mapping.json"))
        self.classifier.set_cache(self.cache)

        # 兼容性：暴露 mapping 属性
        self.mapping = self.cache.mapping

    def classify(self, payee: str, raw_category: str, note: str, raw_account: str) -> str:
        """分类（兼容原接口）

        Args:
            payee: 商户名称
            raw_category: 原始分类
            note: 交易备注
            raw_account: 原始账户（未使用）

        Returns:
            分类结果
        """
        return self.classifier.classify(
            payee=payee,
            raw_category=raw_category,
            note=note,
            raw_account=raw_account,
            allowed_accounts=set(self.config.my_accounts)
        )

    def _save_mapping(self) -> None:
        """保存映射（兼容原接口）"""
        self.cache.save()
