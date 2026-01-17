# satUSD Liquidity Monitor

监控 [Segment Finance](https://app.segment.finance/#/) 上 satUSD-v1 资产的 Liquidity，当超过设定阈值时通过 Telegram 推送通知。

## 功能特性

- 🔍 **自动监控**: 定时检查 satUSD-v1 的 Liquidity 值
- 📱 **Telegram 推送**: 条件触发时自动发送通知
- ⚙️ **可配置**: 阈值、检查间隔等参数均可自定义
- 🔄 **7x24 运行**: 支持 systemd 服务，自动重启

## 项目结构

```
satUSD Monitor/
├── monitor.py          # 主监控程序
├── config.py           # 配置文件（包含敏感信息，不上传）
├── config.example.py   # 配置示例
├── requirements.txt    # Python 依赖
├── deploy_server.sh    # 服务器部署脚本
├── upload_to_tencent.sh # 上传到腾讯云脚本
└── .gitignore          # Git 忽略文件
```

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
python3 -m playwright install chromium
```

### 2. 配置

复制配置示例并填入真实值：

```bash
cp config.example.py config.py
```

编辑 `config.py`：

```python
# Telegram Bot 配置
TELEGRAM_BOT_TOKEN = "your_bot_token"
TELEGRAM_CHAT_ID = "your_chat_id"

# 监控配置
MONITOR_CONFIG = {
    "liquidity_threshold": 100,  # 触发阈值（美元）
    "check_interval": 1800,      # 检查间隔（秒，30分钟）
    # ...
}
```

### 3. 运行

```bash
# 测试连接
python3 monitor.py test

# 执行一次检查
python3 monitor.py once

# 持续运行监控
python3 monitor.py run
```

## 配置说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `url` | https://app.segment.finance/#/ | 监控的网站 URL |
| `asset_name` | satUSD-v1 | 监控的资产名称 |
| `liquidity_threshold` | 100 | 触发通知的阈值（美元） |
| `check_interval` | 1800 | 检查间隔（秒，默认30分钟） |
| `notify_on_change_only` | False | 是否只在状态变化时通知 |
| `page_timeout` | 60 | 页面加载超时时间（秒） |

## 服务器部署

### 部署到腾讯云

1. 修改 `upload_to_tencent.sh` 中的服务器配置
2. 执行部署脚本：

```bash
chmod +x upload_to_tencent.sh
./upload_to_tencent.sh
```

### 管理命令

```bash
# 查看服务状态
sudo systemctl status satusd-monitor

# 查看日志
tail -f /home/ubuntu/satusd-monitor/monitor.log

# 重启服务
sudo systemctl restart satusd-monitor

# 停止服务
sudo systemctl stop satusd-monitor
```

## 技术实现

- **Python 3.9+**
- **Playwright**: 用于获取动态渲染的网页数据
- **Requests**: 用于发送 Telegram 消息
- **systemd**: 用于服务管理和自动重启

## 注意事项

⚠️ `config.py` 包含敏感信息（Telegram Token 等），已添加到 `.gitignore`，请勿上传到公开仓库。

## License

MIT

