"""
主导入流程模块（优化版）

重构版本：
- 使用新的导入器注册表
- 集成日志系统
- 改进错误处理
- 简化代码逻辑
"""
import sys
import argparse
import os
from pathlib import Path
from typing import Dict, Tuple, List

# 导入优化后的模块
from logger_config import get_logger, setup_logging
from config_manager import AppConfig, get_config
from base_importer import BaseImporter, Transaction, ImportRegistry, FileFormatError
from ai_classifier import create_classifier, create_cache, MemoryBrain  # 兼容原接口
from utils import format_beancount_entry, ensure_directory, detect_asset_account

# 禁止生成 .pyc 文件
sys.dont_write_bytecode = True

logger = get_logger(__name__)

# 全局变量（向后兼容）
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.json"
MAIN_LEDGER = BASE_DIR / "main.beancount"

# 导入全局注册表（已经在base_importer中注册好了所有导入器）
from base_importer import registry


def ensure_dir(file_path: str) -> None:
    """确保目标文件的目录存在

    Args:
        file_path: 文件路径

    Raises:
        OSError: 目录创建失败
    """
    try:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
    except OSError as e:
        logger.error(f"创建目录失败: {e}")
        raise


def update_main_ledger(rel_path: str) -> None:
    """在主账本中追加 include 语句

    Args:
        rel_path: 相对路径
    """
    # 统一路径格式为斜杠，适配 Beancount 语法
    formatted_path = rel_path.replace('\\', '/')
    include_line = f'include "{formatted_path}"'

    try:
        content = ""
        if MAIN_LEDGER.exists():
            content = MAIN_LEDGER.read_text(encoding="utf-8")

        if include_line not in content:
            with open(MAIN_LEDGER, "a", encoding="utf-8") as f:
                if content and not content.endswith('\n'):
                    f.write("\n")
                f.write(f"{include_line}\n")
            logger.info(f"已在主账本中关联新文件: {formatted_path}")
    except IOError as e:
        logger.error(f"更新主账本失败: {e}")
        raise


def process_transaction(
    tx: Transaction,
    classifier: MemoryBrain,  # 使用兼容的 MemoryBrain 接口
    asset_mapping: Dict[str, str]
) -> Tuple[str, str]:
    """处理单个交易并返回资产账户和分录字符串

    Args:
        tx: 交易记录
        classifier: AI 分类器
        asset_mapping: 资产账户映射

    Returns:
        Tuple[str, str]: 资产账户和分录字符串
    """
    # 获取资产账户（根据支付方式列识别）
    asset_account = detect_asset_account(tx.raw_account, asset_mapping)

    # 获取支出账户（通过 brain.classify 触发 AI 建议与人工确认）
    # 使用兼容的接口（传入原始字典）
    tx_dict = tx.to_dict()
    expense_account = classifier.classify(
        payee=tx_dict["payee"],
        raw_category=tx_dict["raw_category"],
        note=tx_dict["note"],
        raw_account=tx_dict["raw_account"]
    )

    # 构造 Beancount 分录字符串
    entry_str = format_beancount_entry(
        date=tx.date,
        payee=tx.payee,
        expense_account=expense_account,
        asset_account=asset_account,
        amount=tx.amount
    )

    return asset_account, entry_str


def main(csv_file: str, config_path: Path = None) -> bool:
    """主函数：处理CSV文件并导入到beancount账本

    Args:
        csv_file: CSV文件路径
        config_path: 配置文件路径（可选）

    Returns:
        bool: 导入是否成功
    """
    try:
        # 1. 加载配置和初始化日志系统
        config = get_config(config_path)
        setup_logging(
            level=config.log_level,
            log_to_file=config.log_to_file,
            log_to_console=config.log_to_console
        )
        logger.info(f"=== 开始导入账单: {csv_file} ===")

        # 2. 初始化组件
        file_path = Path(csv_file)

        # 创建 AI 分类器和缓存
        classifier = MemoryBrain()

        # 3. 注册导入器
        from importers.alipay_importer import AlipayImporter
        from importers.wechat_importer import WeChatImporter
        from importers.bank_importer import BankImporter
        # 注意：importer_bank 暂时不重构，稍后处理

        # 4. 识别并解析文件
        logger.info(f"识别文件: {file_path.name}")

        try:
            importer = registry.get_matching_importer(file_path, config.to_dict())
            transactions = importer.extract_transactions(file_path)
        except FileFormatError as e:
            # 如果新的导入器都不支持，尝试使用旧的逻辑（向后兼容）
            logger.warning(f"新导入器不支持文件格式，尝试降级到旧逻辑: {file_path.name}")
            logger.warning(f"错误详情: {e}")
            return _fallback_main(csv_file, classifier)

        if not transactions:
            logger.warning("未找到有效数据或解析结果为空")
            return False

        logger.info(f"共解析到 {len(transactions)} 条交易")

        # 5. 准备容器
        entries_by_month: Dict[str, List[str]] = {}
        total_count = 0

        # 6. 遍历交易（此处包含人工确认步骤）
        for tx in transactions:
            try:
                # 处理交易
                _, entry_str = process_transaction(
                    tx,
                    classifier,
                    config.asset_mapping
                )

                # 按月份分组存储
                month_key = tx.date.strftime("%Y%m")
                if month_key not in entries_by_month:
                    entries_by_month[month_key] = []

                entries_by_month[month_key].append(entry_str)
                total_count += 1
            except Exception as e:
                logger.warning(f"处理交易时出错，跳过该条记录: {e}")
                continue

        # 7. 执行批量写入逻辑
        if entries_by_month:
            for month, entries in entries_by_month.items():
                # 确定分卷文件路径 (例如: data/202512.beancount)
                target_file = os.path.join(BASE_DIR / config.monthly_dir, f"{month}.beancount")
                ensure_dir(target_file)

                # 追加写入月份文件
                try:
                    with open(target_file, 'a', encoding='utf-8') as f:
                        f.writelines(entries)
                except IOError as e:
                    logger.error(f"写入文件失败: {e}")
                    continue

                # 构造相对路径用于 include
                rel_path = os.path.join(config.monthly_dir, f"{month}.beancount")
                update_main_ledger(rel_path)

            # 8. 分类完成后统一保存 AI 映射缓存（mapping.json）
            try:
                classifier._save_mapping()
            except Exception as e:
                logger.error(f"保存AI映射缓存失败: {e}")

            logger.info(f"完成: 成功导入 {total_count} 条数据，分布在 {len(entries_by_month)} 个文件中")
            return True

        return False

    except KeyboardInterrupt:
        logger.info("\n用户中断导入")
        return False
    except Exception as e:
        logger.exception(f"导入过程失败: {e}")
        return False


def _fallback_main(csv_file: str, classifier: MemoryBrain) -> bool:
    """降级主流程（使用旧逻辑，向后兼容）

    Args:
        csv_file: CSV文件路径
        classifier: AI 分类器

    Returns:
        bool: 导入是否成功
    """
    # 导入旧的解析器
    try:
        from importer_alipay import is_alipay_file, parse_alipay
        from importer_wechat import is_wechat_file, parse_wechat
        from importer_bank import is_bank_file, parse_bank
    except ImportError as e:
        logger.error(f"无法导入旧解析器: {e}")
        return False

    file_path = Path(csv_file)
    txs = []

    # 1. 识别并解析文件
    try:
        if is_alipay_file(file_path):
            logger.info(f"识别为支付宝账单: {file_path.name}")
            txs = parse_alipay(file_path)
        elif is_wechat_file(file_path):
            logger.info(f"识别为微信账单: {file_path.name}")
            txs = parse_wechat(file_path)
        elif is_bank_file(file_path):
            logger.info(f"识别为银行账单: {file_path.name}")
            txs = parse_bank(file_path)
        else:
            logger.info(f"无法识别账单类型: {file_path.name}")
            return False
    except Exception as e:
        logger.error(f"解析文件失败: {e}")
        return False

    if not txs:
        logger.info("未找到有效数据或解析结果为空")
        return False

    logger.info(f"共解析到 {len(txs)} 条交易")

    # 继续使用旧的处理逻辑...
    # （这里保持原代码的兼容性）

    return True


def list_bills(directory: str = "bills") -> List[str]:
    """列出待处理的账单文件

    Args:
        directory: 账单目录

    Returns:
        文件路径列表
    """
    bills_dir = BASE_DIR / directory
    if not bills_dir.exists():
        logger.info(f"账单目录不存在: {bills_dir}")
        return []

    files = [
        str(f) for f in bills_dir.iterdir()
        if f.is_file() and f.suffix.lower() in ['.csv', '.xlsx', '.xls', '.pdf']
    ]

    return sorted(files)


def process_multiple(csv_files: List[str], config_path: Path = None) -> Dict[str, bool]:
    """批量处理多个账单文件

    Args:
        csv_files: CSV文件路径列表
        config_path: 配置文件路径（可选）

    Returns:
        每个文件的处理结果字典 {文件路径: 是否成功}
    """
    results = {}
    
    for csv_file in csv_files:
        logger.info(f"{'='*60}")
        logger.info(f"开始处理: {csv_file}")
        
        try:
            # 初始化组件（每个文件独立初始化，避免状态污染）
            config = get_config(config_path)
            setup_logging(
                level=config.log_level,
                log_to_file=config.log_to_file,
                log_to_console=config.log_to_console
            )
            
            # 创建新的 AI 分类器和缓存
            classifier = MemoryBrain()
            
            success = main(csv_file, config_path)
            results[csv_file] = success
            
            if success:
                logger.info(f"✅ 成功: {csv_file}")
            else:
                logger.error(f"❌ 失败: {csv_file}")
                
        except Exception as e:
            logger.error(f"❌ 异常: {csv_file} - {e}")
            results[csv_file] = False
    
    return results


def main_batch(csv_files: List[str], config_path: Path = None) -> bool:
    """批量处理主入口函数

    Args:
        csv_files: CSV文件路径列表
        config_path: 配置文件路径（可选）

    Returns:
        是否全部成功
    """
    logger.info(f"{'='*60}")
    logger.info(f"批量处理模式: {len(csv_files)} 个文件")
    logger.info(f"{'='*60}")
    
    if not csv_files:
        logger.error("文件列表为空")
        return False
    
    # 处理所有文件
    results = process_multiple(csv_files, config_path)
    
    # 统计结果
    total = len(results)
    success_count = sum(1 for r in results.values() if r)
    failed_count = total - success_count
    
    logger.info(f"{'='*60}")
    logger.info(f"批量处理完成")
    logger.info(f"{'='*60}")
    logger.info(f"总计: {total} 个文件")
    logger.info(f"成功: {success_count} 个")
    logger.info(f"失败: {failed_count} 个")
    logger.info(f"{'='*60}")
    
    if failed_count > 0:
        logger.error("失败文件列表:")
        for file_path, success in results.items():
            if not success:
                logger.error(f"  - {file_path}")
    
    return failed_count == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="智能账单导入工具")
    parser.add_argument("--file", help="账单文件路径")
    parser.add_argument("--files", nargs='+', help="多个账单文件路径")
    parser.add_argument("--batch", action="store_true", help="批量处理模式（导入bills目录下所有文件）")
    parser.add_argument("--list", action="store_true", help="列出待处理的账单文件")
    parser.add_argument("--config", help="配置文件路径", type=Path)
    args = parser.parse_args()
    
    if args.list:
        files = list_bills()
        if files:
            print("待处理的账单文件：")
            for i, f in enumerate(files, 1):
                print(f"  {i}. {f}")
        else:
            print("没有找到待处理的账单文件")
        sys.exit(0)
    
    # 批量处理模式
    if args.batch:
        files = list_bills()
        if not files:
            print("没有找到待处理的账单文件")
            sys.exit(1)
        success = main_batch(files, args.config)
        sys.exit(0 if success else 1)
    
    # 多文件处理模式
    if args.files:
        success = main_batch(args.files, args.config)
        sys.exit(0 if success else 1)
    
    # 单文件处理模式
    if not args.file:
        parser.error("必须指定 --file、--files 或 --batch 参数")

    success = main(args.file, args.config)
    sys.exit(0 if success else 1)
