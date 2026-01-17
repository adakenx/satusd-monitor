#!/bin/bash

# 服务器端部署脚本
# 在腾讯云服务器上执行，设置 satUSD 监控为 systemd 服务

set -e

WORK_DIR="/home/ubuntu/satusd-monitor"
SERVICE_NAME="satusd-monitor"

cd $WORK_DIR

echo "=========================================="
echo "    satUSD Liquidity 监控 - 服务器部署"
echo "=========================================="

# 1. 创建虚拟环境
echo ""
echo "[1/6] 创建 Python 虚拟环境..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 虚拟环境创建成功"
else
    echo "✅ 虚拟环境已存在"
fi

# 2. 激活虚拟环境并安装依赖
echo ""
echo "[2/6] 安装 Python 依赖..."
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ 依赖安装完成"

# 3. 安装 Playwright 浏览器
echo ""
echo "[3/6] 安装 Chromium 浏览器..."
python -m playwright install chromium
echo "✅ Chromium 安装完成"

# 4. 安装系统依赖（Playwright 需要）
echo ""
echo "[4/6] 安装系统依赖..."
python -m playwright install-deps chromium 2>/dev/null || {
    echo "⚠️ 自动安装依赖失败，尝试手动安装..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 2>/dev/null || true
}
echo "✅ 系统依赖安装完成"

# 5. 测试连接
echo ""
echo "[5/6] 测试 API 连接..."
python monitor.py test

# 6. 创建 systemd 服务
echo ""
echo "[6/6] 配置 systemd 服务..."

# 创建服务文件
sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null << EOF
[Unit]
Description=satUSD Liquidity Monitor
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${WORK_DIR}
ExecStart=${WORK_DIR}/venv/bin/python ${WORK_DIR}/monitor.py run
Restart=always
RestartSec=30
StandardOutput=append:${WORK_DIR}/monitor.log
StandardError=append:${WORK_DIR}/monitor.log

# 环境变量
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# 重新加载 systemd 并启动服务
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}

echo "✅ systemd 服务配置完成"

# 检查服务状态
echo ""
echo "=========================================="
echo "           部署完成！"
echo "=========================================="
echo ""
echo "📊 服务状态:"
sudo systemctl status ${SERVICE_NAME} --no-pager | head -10
echo ""
echo "📋 管理命令:"
echo "   查看状态: sudo systemctl status ${SERVICE_NAME}"
echo "   查看日志: tail -f ${WORK_DIR}/monitor.log"
echo "   重启服务: sudo systemctl restart ${SERVICE_NAME}"
echo "   停止服务: sudo systemctl stop ${SERVICE_NAME}"
echo "   启动服务: sudo systemctl start ${SERVICE_NAME}"
echo ""
echo "⏰ 监控配置: 每 30 分钟检查一次，当 Liquidity > \$100 时推送通知"
echo ""

