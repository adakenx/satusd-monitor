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
import traceback
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

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
        self.consecutive_failures = 0  # 连续失败次数
        self.last_heartbeat = None  # 上次心跳时间
        self.last_success_time = None  # 上次成功获取数据的时间
        self.max_failures_before_alert = 3  # 连续失败多少次后发送告警
        self.heartbeat_interval_hours = 72  # 心跳间隔（小时，3天）
        
    def log(self, msg):
        """打印带时间戳的日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {msg}", flush=True)
    
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
    
    def get_liquidity_from_page(self, retry_count=3):
        """
        使用 Playwright 从网页获取 satUSD-v1 的 liquidity 值
        支持重试机制
        """
        last_error = None
        
        for attempt in range(retry_count):
            if attempt > 0:
                self.log(f"第 {attempt + 1} 次重试...")
                time.sleep(5)  # 重试前等待
            
            browser = None
            try:
                self.log("启动浏览器获取页面数据...")
                
                with sync_playwright() as p:
                    # 使用 headless 模式
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        viewport={'width': 1920, 'height': 1080},
                        user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    )
                    page = context.new_page()
                    
                    # 设置默认超时
                    page.set_default_timeout(self.config['page_timeout'] * 1000)
                    
                    # 访问页面
                    self.log(f"访问 {self.config['url']}...")
                    page.goto(self.config['url'], wait_until='networkidle', timeout=self.config['page_timeout'] * 1000)
                    
                    # 等待页面加载完成 - 等待资产表格出现
                    self.log("等待页面数据加载...")
                    page.wait_for_selector('text=satUSD-v1', timeout=30000)
                    
                    # 额外等待确保数据完全加载
                    time.sleep(3)
                    
                    # 查找 satUSD-v1 所在的行
                    rows = page.query_selector_all('tr, [role="row"], .MuiTableRow-root')
                    
                    for row in rows:
                        row_text = row.inner_text()
                        if 'satUSD-v1' in row_text:
                            self.log(f"找到 satUSD-v1 行: {row_text[:100]}...")
                            
                            # 遍历单元格获取信息
                            cells = row.query_selector_all('td, [role="cell"], .MuiTableCell-root')
                            for i, cell in enumerate(cells):
                                cell_text = cell.inner_text()
                                self.log(f"  单元格 {i}: {cell_text}")
                            
                            # 从完整行文本中提取 liquidity 值
                            # 方法1: 匹配 "X.XX satUSD-v1" 和下面的 "$X.XX"
                            liquidity_match = re.search(r'([\d.]+)\s*satUSD-v1\s*\$?([\d.]+)', row_text)
                            if liquidity_match:
                                usd_value = float(liquidity_match.group(2))
                                self.log(f"提取到 liquidity: ${usd_value}")
                                browser.close()
                                return usd_value
                            
                            # 方法2: 查找所有美元值
                            numbers = re.findall(r'\$([\d.]+)', row_text)
                            if numbers:
                                self.log(f"找到的美元值: {numbers}")
                                if len(numbers) >= 2:
                                    liquidity = float(numbers[-2])
                                    self.log(f"推测 liquidity: ${liquidity}")
                                    browser.close()
                                    return liquidity
                    
                    # 未找到数据，保存页面用于调试
                    self.log("未能从页面提取数据，保存调试信息...")
                    try:
                        page_content = page.content()
                        with open('debug_page.html', 'w', encoding='utf-8') as f:
                            f.write(page_content)
                        self.log("页面内容已保存到 debug_page.html")
                    except Exception as save_err:
                        self.log(f"保存调试文件失败: {save_err}")
                    
                    browser.close()
                    last_error = "未能从页面提取 liquidity 数据"
                    
            except PlaywrightTimeout as e:
                last_error = f"页面加载超时: {e}"
                self.log(f"[错误] {last_error}")
            except Exception as e:
                last_error = f"获取页面数据失败: {e}"
                self.log(f"[错误] {last_error}")
                self.log(f"详细错误: {traceback.format_exc()}")
            finally:
                # 确保浏览器被关闭
                if browser:
                    try:
                        browser.close()
                    except:
                        pass
        
        self.log(f"[错误] 重试 {retry_count} 次后仍然失败: {last_error}")
        return None
    
    def send_telegram_message(self, message, retry_count=3):
        """发送 Telegram 消息，支持重试"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        
        for attempt in range(retry_count):
            try:
                response = requests.post(url, json=payload, timeout=15)
                response.raise_for_status()
                self.log("[成功] Telegram 消息已发送")
                return True
            except requests.RequestException as e:
                self.log(f"[错误] Telegram 消息发送失败 (尝试 {attempt + 1}/{retry_count}): {e}")
                if attempt < retry_count - 1:
                    time.sleep(2)
        
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
    
    def send_failure_alert(self):
        """发送连续失败告警"""
        message = "⚠️ <b>satUSD 监控异常</b>\n\n"
        message += f"❌ 连续 {self.consecutive_failures} 次获取数据失败\n"
        message += f"📍 监控目标: {self.config['asset_name']}\n"
        message += f"🔗 <a href='{self.config['url']}'>手动检查</a>\n"
        if self.last_success_time:
            message += f"\n✅ 上次成功: {self.last_success_time.strftime('%Y-%m-%d %H:%M:%S')}"
        message += f"\n⏰ 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.send_telegram_message(message)
    
    def send_heartbeat(self):
        """发送心跳消息，证明监控程序仍在运行"""
        now = datetime.now()
        
        # 检查是否需要发送心跳
        if self.last_heartbeat is None:
            # 首次启动不发送心跳，等待第一个周期
            self.last_heartbeat = now
            return
        
        hours_since_heartbeat = (now - self.last_heartbeat).total_seconds() / 3600
        if hours_since_heartbeat >= self.heartbeat_interval_hours:
            message = "💚 <b>satUSD 监控心跳</b>\n\n"
            message += "✅ 监控程序运行正常\n"
            message += f"📊 监控目标: {self.config['asset_name']}\n"
            message += f"⏱️ 检查间隔: {self.config['check_interval'] // 60} 分钟\n"
            message += f"📈 触发阈值: ${self.config['liquidity_threshold']}\n"
            if self.last_success_time:
                message += f"\n✅ 上次成功获取: {self.last_success_time.strftime('%H:%M:%S')}"
            message += f"\n⏰ 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}"
            
            if self.send_telegram_message(message):
                self.last_heartbeat = now
                self.log("心跳消息已发送")
    
    def check_and_notify(self):
        """检查 liquidity 并在需要时发送通知"""
        self.log("=" * 50)
        self.log("开始检查 satUSD-v1 Liquidity")
        self.log("=" * 50)
        
        liquidity = self.get_liquidity_from_page(retry_count=3)
        
        if liquidity is None:
            self.consecutive_failures += 1
            self.log(f"[错误] 无法获取 liquidity 值 (连续失败: {self.consecutive_failures})")
            
            # 连续失败达到阈值时发送告警
            if self.consecutive_failures >= self.max_failures_before_alert:
                if self.consecutive_failures == self.max_failures_before_alert:
                    self.log("连续失败次数达到阈值，发送告警...")
                    self.send_failure_alert()
                elif self.consecutive_failures % self.max_failures_before_alert == 0:
                    # 每隔一定次数再次告警
                    self.log("再次发送失败告警...")
                    self.send_failure_alert()
            
            self.log("=" * 50)
            return False
        
        # 成功获取数据，重置失败计数
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        
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
        self.log(f"检查间隔: {self.config['check_interval']} 秒 ({self.config['check_interval'] // 60} 分钟)")
        self.log(f"触发阈值: ${self.config['liquidity_threshold']}")
        self.log(f"心跳间隔: {self.heartbeat_interval_hours} 小时")
        self.log(f"失败告警阈值: 连续 {self.max_failures_before_alert} 次")
        self.log("=" * 50)
        
        # 发送启动通知
        startup_msg = "🚀 <b>satUSD 监控已启动</b>\n\n"
        startup_msg += f"📊 监控目标: {self.config['asset_name']}\n"
        startup_msg += f"⏱️ 检查间隔: {self.config['check_interval'] // 60} 分钟\n"
        startup_msg += f"📈 触发阈值: ${self.config['liquidity_threshold']}\n"
        startup_msg += f"\n⏰ 启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        self.send_telegram_message(startup_msg)
        
        while True:
            try:
                self.check_and_notify()
                self.send_heartbeat()
            except KeyboardInterrupt:
                self.log("收到中断信号，正在退出...")
                break
            except Exception as e:
                self.log(f"[严重错误] 检查过程出错: {e}")
                self.log(f"详细错误: {traceback.format_exc()}")
                self.consecutive_failures += 1
            
            self.log(f"下次检查在 {self.config['check_interval']} 秒后...")
            try:
                time.sleep(self.config['check_interval'])
            except KeyboardInterrupt:
                self.log("收到中断信号，正在退出...")
                break


def test_connection():
    """测试各项连接"""
    print("=" * 50)
    print("satUSD Liquidity 监控 - 连接测试")
    print("=" * 50)
    
    monitor = SatUSDMonitor()
    
    # 测试页面访问
    print("\n1. 测试页面访问...")
    liquidity = monitor.get_liquidity_from_page(retry_count=2)
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
