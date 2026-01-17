# 配置文件示例 - 请复制为 config.py 并填入真实值
# 注意：config.py 包含敏感信息，请勿上传到 Git！

# Telegram Bot 配置
TELEGRAM_BOT_TOKEN = "your_bot_token_here"
TELEGRAM_CHAT_ID = "your_chat_id_here"

# 监控配置
MONITOR_CONFIG = {
    # 监控的网站 URL
    "url": "https://app.segment.finance/#/",
    
    # 要监控的资产名称
    "asset_name": "satUSD-v1",
    
    # liquidity 阈值（美元），超过此值触发通知
    "liquidity_threshold": 100,
    
    # 检查间隔（秒），默认 30 分钟
    "check_interval": 1800,
    
    # 是否只在状态变化时通知（从低于阈值变为高于阈值）
    # False = 每次超过阈值都通知
    # True = 只在首次超过阈值时通知
    "notify_on_change_only": False,
    
    # 页面加载超时时间（秒）
    "page_timeout": 60,
}

