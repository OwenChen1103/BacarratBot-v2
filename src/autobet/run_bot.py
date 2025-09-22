#!/usr/bin/env python3
"""
自動投注機器人主入口 - 讀取配置、啟動引擎
"""

import os
import sys
import time
import logging
import argparse
import yaml
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# 添加專案根目錄到 Python 路徑
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.autobet.autobet_engine import AutoBetEngine
from src.autobet.io_events import NDJSONPlayer, DemoFeeder


def setup_logging(log_level: str = "INFO"):
    """設置日誌"""
    os.makedirs('data/logs', exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('data/logs/autobet.log', encoding='utf-8')
        ]
    )


def load_environment_config():
    """載入環境配置"""
    load_dotenv()

    config = {
        'dry_run': os.getenv('DRY_RUN', '1') == '1',
        'screen_dpi_scale': float(os.getenv('SCREEN_DPI_SCALE', '1.0')),
        'log_level': os.getenv('LOG_LEVEL', 'INFO'),
        'event_source_mode': os.getenv('EVENT_SOURCE_MODE', 'demo'),
        'reader_sse_url': os.getenv('READER_SSE_URL', 'http://127.0.0.1:8888/events'),
        'ndjson_replay_file': os.getenv('NDJSON_REPLAY_FILE', 'data/sessions/events.sample.ndjson'),
        'demo_round_interval': int(os.getenv('DEMO_ROUND_INTERVAL_SEC', '10')),
        'demo_random_seed': os.getenv('DEMO_RANDOM_SEED')
    }

    if config['demo_random_seed']:
        config['demo_random_seed'] = int(config['demo_random_seed'])

    return config


def main():
    """主函數"""
    parser = argparse.ArgumentParser(description="百家樂自動投注機器人")
    parser.add_argument('--strategy', default='configs/strategy.default.json', help='策略配置檔案路徑')
    parser.add_argument('--positions', default='configs/positions.sample.json', help='位置配置檔案路徑')
    parser.add_argument('--event-source', choices=['ndjson', 'sse', 'demo'], default=None, help='事件來源模式')
    parser.add_argument('--ndjson-file', default='data/sessions/events.sample.ndjson', help='NDJSON事件檔案路徑')
    parser.add_argument('--dry-run', type=int, choices=[0, 1], default=None, help='乾跑模式 (0=實戰, 1=乾跑)')

    args = parser.parse_args()

    # 載入環境配置
    env_config = load_environment_config()

    # CLI 參數覆蓋環境變數
    if args.event_source:
        env_config['event_source_mode'] = args.event_source
    if args.ndjson_file:
        env_config['ndjson_replay_file'] = args.ndjson_file
    if args.dry_run is not None:
        env_config['dry_run'] = bool(args.dry_run)

    # 設置日誌
    setup_logging(env_config['log_level'])
    logger = logging.getLogger(__name__)

    # 確保資料目錄存在
    os.makedirs('data/logs', exist_ok=True)
    os.makedirs('data/sessions', exist_ok=True)

    logger.info("百家樂自動投注機器人啟動")
    logger.info(f"乾跑模式: {env_config['dry_run']}")
    logger.info(f"事件來源: {env_config['event_source_mode']}")

    try:
        return run_console_mode(args, env_config)
    except KeyboardInterrupt:
        logger.info("用戶中斷，程式結束")
        return 0
    except Exception as e:
        logger.error(f"程式錯誤: {e}", exc_info=True)
        return 1


def run_console_mode(args, env_config):
    """命令行模式"""
    logger = logging.getLogger(__name__)

    # 載入UI配置
    ui_config = {}
    ui_config_file = 'configs/ui.yaml'
    if os.path.exists(ui_config_file):
        with open(ui_config_file, 'r', encoding='utf-8') as f:
            ui_config = yaml.safe_load(f)

    # 創建引擎
    engine = AutoBetEngine(dry_run=env_config['dry_run'])

    # 載入配置
    if not engine.load_positions(args.positions, env_config['screen_dpi_scale']):
        logger.error("載入位置配置失敗")
        return 1

    if not engine.load_strategy(args.strategy):
        logger.error("載入策略配置失敗")
        return 1

    engine.load_ui_config(ui_config)

    # 初始化組件
    if not engine.initialize_components():
        logger.error("初始化組件失敗")
        return 1

    # 設置事件處理
    event_feeder = None
    mode = env_config['event_source_mode']

    if mode == 'ndjson':
        ndjson_file = env_config['ndjson_replay_file']
        if not os.path.exists(ndjson_file):
            logger.error(f"NDJSON檔案不存在: {ndjson_file}")
            return 1
        event_feeder = NDJSONPlayer(ndjson_file, engine.on_event)
        logger.info(f"使用NDJSON回放: {ndjson_file}")
    elif mode == 'demo':
        interval = env_config['demo_round_interval']
        seed = env_config['demo_random_seed']
        event_feeder = DemoFeeder(interval, engine.on_event, seed)
        logger.info(f"使用Demo模式，間隔: {interval}秒")
    else:
        logger.error(f"不支援的事件來源: {mode}")
        return 1

    # 啟動引擎
    engine.set_enabled(True)

    # 啟動事件來源
    if event_feeder:
        event_feeder.start()

    logger.info("引擎已啟動，按 Ctrl+C 停止")

    try:
        # 主循環
        while True:
            time.sleep(0.1)

            # 檢查狀態
            status = engine.get_status()
            if status['current_state'] == 'error':
                logger.error("引擎進入錯誤狀態")
                break

            # 檢查NDJSON是否完成
            if mode == 'ndjson' and event_feeder and not event_feeder.is_running():
                logger.info("NDJSON回放完成")
                break

    except KeyboardInterrupt:
        logger.info("停止引擎...")
    finally:
        # 清理
        if event_feeder:
            event_feeder.stop()
        engine.set_enabled(False)
        time.sleep(0.5)  # 給線程時間清理

    logger.info("程式正常結束")
    return 0


if __name__ == "__main__":
    sys.exit(main())