#!/usr/bin/env python3
"""
satUSD Liquidity 监控程序
监控 Segment Finance 上 satUSD-v1 的 liquidity，当超过阈值时通过 Telegram 推送通知

使用方法：
  python monitor.py test      # 测试连接
  python monitor.py once      # 执行一次检查
  python monitor.py run       # 持续运行监控
"""

import re
import time
import requests
from datetime import datetime
from playwright.sync_api import sync_playwright

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    MONITOR_CONFIG,
)


class SatUSDMonitor:
    """satUSD Liquidity 监控类"""
    
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.config = MONITOR_CONFIG
        self.last_state_above_threshold = None  # 用于追踪状态变化
        
    def log(self, msg):
        """打印带时间戳的日志"""
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")
    
    def parse_liquidity_value(self, text):
        """
        解析 liquidity 文本为数值
        例如: "20.40 satUSD-v1" -> 20.40
              "$20.39" -> 20.39
              "1.5K" -> 1500
              "2.3M" -> 2300000
        """
        if not text:
            return None
        
        # 移除货币符号和空格
        text = text.replace('$', '').replace(',', '').strip()
        
        # 处理 K/M/B 后缀
        multiplier = 1
        if text.endswith('K') or text.endswith('k'):
            multiplier = 1000
            text = text[:-1]
        elif text.endswith('M') or text.endswith('m'):
            multiplier = 1000000
            text = text[:-1]
        elif text.endswith('B') or text.endswith('b'):
            multiplier = 1000000000
            text = text[:-1]
        
        # 提取数字部分
        match = re.search(r'[\d.]+', text)
        if match:
            try:
                return float(match.group()) * multiplier
            except ValueError:
                return None
        return None
    
    def get_liquidity_from_page(self):
        """
        使用 Playwright 从网页获取 satUSD-v1 的 liquidity 值
        """
        self.log("启动浏览器获取页面数据...")
        
        with sync_playwright() as p:
            # 使用 headless 模式
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            )
            page = context.new_page()
            
            try:
                # 访问页面
                self.log(f"访问 {self.config['url']}...")
                page.goto(self.config['url'], timeout=self.config['page_timeout'] * 1000)
                
                # 等待页面加载完成 - 等待资产表格出现
                self.log("等待页面数据加载...")
                page.wait_for_selector('text=satUSD-v1', timeout=30000)
                
                # 额外等待确保数据完全加载
                time.sleep(3)
                
                # 查找 satUSD-v1 所在的行
                # 方法1: 尝试通过表格结构定位
                rows = page.query_selector_all('tr, [role="row"], .MuiTableRow-root')
                
                for row in rows:
                    row_text = row.inner_text()
                    if 'satUSD-v1' in row_text:
                        self.log(f"找到 satUSD-v1 行: {row_text[:100]}...")
                        
                        # 尝试从行文本中提取 liquidity
                        # 根据截图，liquidity 显示为 "20.40 satUSD-v1" 和 "$20.39"
                        # 查找 Liquidity 列的值
                        cells = row.query_selector_all('td, [role="cell"], .MuiTableCell-root')
                        
                        # 遍历单元格寻找 liquidity 相关的值
                        for i, cell in enumerate(cells):
                            cell_text = cell.inner_text()
                            self.log(f"  单元格 {i}: {cell_text}")
                        
                        # 从完整行文本中提取可能的 liquidity 值
                        # 根据截图格式，liquidity 显示在特定位置
                        # 尝试匹配 "X.XX satUSD-v1" 和下面的 "$X.XX"
                        liquidity_match = re.search(r'([\d.]+)\s*satUSD-v1\s*\$?([\d.]+)', row_text)
                        if liquidity_match:
                            # 使用美元值
                            usd_value = float(liquidity_match.group(2))
                            self.log(f"提取到 liquidity: ${usd_value}")
                            browser.close()
                            return usd_value
                        
                        # 备选方案：查找所有数字
                        numbers = re.findall(r'\$([\d.]+)', row_text)
                        if numbers:
                            # 最后一个美元值可能是 price，倒数第二个可能是 liquidity
                            self.log(f"找到的美元值: {numbers}")
                            if len(numbers) >= 2:
                                liquidity = float(numbers[-2])
                                self.log(f"推测 liquidity: ${liquidity}")
                                browser.close()
                                return liquidity
                
                # 方法2: 直接搜索页面内容
                self.log("尝试备选方法提取数据...")
                page_content = page.content()
                
                # 保存页面内容用于调试
                with open('debug_page.html', 'w', encoding='utf-8') as f:
                    f.write(page_content)
                self.log("页面内容已保存到 debug_page.html")
                
                browser.close()
                return None
                
            except Exception as e:
                self.log(f"[错误] 获取页面数据失败: {e}")
                browser.close()
                return None
    
    def send_telegram_message(self, message):
        """发送 Telegram 消息"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            self.log("[成功] Telegram 消息已发送")
            return True
        except requests.RequestException as e:
            self.log(f"[错误] Telegram 消息发送失败: {e}")
            return False
    
    def format_alert_message(self, liquidity):
        """格式化告警消息"""
        message = "🔔 <b>satUSD Liquidity 告警</b>\n\n"
        message += f"📊 资产: {self.config['asset_name']}\n"
        message += f"💰 当前 Liquidity: <b>${liquidity:.2f}</b>\n"
        message += f"📈 触发阈值: ${self.config['liquidity_threshold']}\n"
        message += f"🔗 <a href='{self.config['url']}'>查看详情</a>\n"
        message += f"\n⏰ 检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        return message
    
    def check_and_notify(self):
        """检查 liquidity 并在需要时发送通知"""
        self.log("=" * 50)
        self.log("开始检查 satUSD-v1 Liquidity")
        self.log("=" * 50)
        
        liquidity = self.get_liquidity_from_page()
        
        if liquidity is None:
            self.log("[错误] 无法获取 liquidity 值")
            return False
        
        self.log(f"当前 Liquidity: ${liquidity:.2f}")
        self.log(f"触发阈值: ${self.config['liquidity_threshold']}")
        
        is_above_threshold = liquidity > self.config['liquidity_threshold']
        
        should_notify = False
        if is_above_threshold:
            if self.config['notify_on_change_only']:
                # 只在状态从低于变为高于时通知
                if self.last_state_above_threshold is False or self.last_state_above_threshold is None:
                    should_notify = True
                    self.log("状态变化：从低于阈值变为高于阈值，发送通知")
                else:
                    self.log("已在阈值以上，跳过通知")
            else:
                # 每次超过阈值都通知
                should_notify = True
        
        self.last_state_above_threshold = is_above_threshold
        
        if should_notify:
            self.log(f"⚠️ Liquidity ${liquidity:.2f} > ${self.config['liquidity_threshold']}，发送通知...")
            message = self.format_alert_message(liquidity)
            self.send_telegram_message(message)
        else:
            self.log(f"✅ Liquidity ${liquidity:.2f} <= ${self.config['liquidity_threshold']}，无需通知")
        
        self.log("=" * 50)
        return True
    
    def run_once(self):
        """执行一次检查"""
        return self.check_and_notify()
    
    def run_continuous(self):
        """持续运行监控"""
        self.log("=" * 50)
        self.log("satUSD Liquidity 监控已启动")
        self.log(f"检查间隔: {self.config['check_interval']} 秒")
        self.log(f"触发阈值: ${self.config['liquidity_threshold']}")
        self.log("=" * 50)
        
        while True:
            try:
                self.check_and_notify()
            except Exception as e:
                self.log(f"[错误] 检查过程出错: {e}")
            
            self.log(f"下次检查在 {self.config['check_interval']} 秒后...")
            time.sleep(self.config['check_interval'])


def test_connection():
    """测试各项连接"""
    print("=" * 50)
    print("satUSD Liquidity 监控 - 连接测试")
    print("=" * 50)
    
    monitor = SatUSDMonitor()
    
    # 测试页面访问
    print("\n1. 测试页面访问...")
    liquidity = monitor.get_liquidity_from_page()
    if liquidity is not None:
        print(f"   ✅ 页面访问成功")
        print(f"   当前 satUSD-v1 Liquidity: ${liquidity:.2f}")
    else:
        print("   ❌ 页面访问失败或无法提取数据")
        print("   请检查 debug_page.html 文件分析原因")
    
    # 测试 Telegram
    print("\n2. 测试 Telegram...")
    test_msg = "🔔 satUSD Monitor 测试\n\n连接成功！"
    if monitor.send_telegram_message(test_msg):
        print("   ✅ Telegram 连接成功")
    else:
        print("   ❌ Telegram 连接失败")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test":
            test_connection()
        elif cmd == "once":
            monitor = SatUSDMonitor()
            monitor.run_once()
        elif cmd == "run":
            monitor = SatUSDMonitor()
            monitor.run_continuous()
        else:
            print("用法:")
            print("  python monitor.py test   # 测试连接")
            print("  python monitor.py once   # 执行一次检查")
            print("  python monitor.py run    # 持续运行监控")
    else:
        # 默认执行一次检查
        monitor = SatUSDMonitor()
        monitor.run_once()

