"""
エラーリカバリー＆ヘルスチェック — 自動リトライ・障害通知・システム監視
"""

import functools
import time
import os
import json
import traceback
from datetime import datetime
from dataclasses import dataclass, asdict


HEALTH_LOG_FILE = os.path.join(os.path.dirname(__file__), "health_log.json")


@dataclass
class HealthStatus:
    component: str
    status: str  # "ok" | "degraded" | "down"
    last_success: str
    last_error: str
    error_count: int
    message: str


def load_health_log():
    if os.path.exists(HEALTH_LOG_FILE):
        with open(HEALTH_LOG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_health_log(log):
    with open(HEALTH_LOG_FILE, "w") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def update_health(component: str, success: bool, message: str = ""):
    """コンポーネントのヘルス状態を更新"""
    log = load_health_log()
    now = datetime.now().isoformat()

    entry = log.get(component, {
        "component": component,
        "status": "ok",
        "last_success": "",
        "last_error": "",
        "error_count": 0,
        "message": "",
    })

    if success:
        entry["status"] = "ok"
        entry["last_success"] = now
        entry["error_count"] = 0
        entry["message"] = message or "正常"
    else:
        entry["error_count"] = entry.get("error_count", 0) + 1
        entry["last_error"] = now
        entry["message"] = message

        if entry["error_count"] >= 5:
            entry["status"] = "down"
        elif entry["error_count"] >= 2:
            entry["status"] = "degraded"

    log[component] = entry
    save_health_log(log)
    return entry


def with_retry(max_retries=3, base_delay=2, component="unknown"):
    """指数バックオフ付きリトライデコレータ"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    update_health(component, success=True)
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"[{component}] リトライ {attempt + 1}/{max_retries} "
                              f"({delay}秒後): {e}")
                        time.sleep(delay)
                    else:
                        update_health(
                            component,
                            success=False,
                            message=f"{e.__class__.__name__}: {str(e)[:200]}",
                        )
            raise last_error
        return wrapper

    return decorator


def with_retry_async(max_retries=3, base_delay=2, component="unknown"):
    """非同期版リトライデコレータ"""
    import asyncio

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    update_health(component, success=True)
                    return result
                except Exception as e:
                    last_error = e
                    if attempt < max_retries:
                        delay = base_delay * (2 ** attempt)
                        print(f"[{component}] リトライ {attempt + 1}/{max_retries} "
                              f"({delay}秒後): {e}")
                        await asyncio.sleep(delay)
                    else:
                        update_health(
                            component,
                            success=False,
                            message=f"{e.__class__.__name__}: {str(e)[:200]}",
                        )
            raise last_error
        return wrapper

    return decorator


def get_health_report() -> list[dict]:
    """全コンポーネントのヘルス状態を取得"""
    log = load_health_log()
    return list(log.values())


def format_health_for_slack() -> list[dict]:
    """Slack表示用のヘルスレポートブロックを生成"""
    report = get_health_report()

    if not report:
        return [{"type": "section", "text": {"type": "mrkdwn", "text": "ヘルスデータなし"}}]

    status_icons = {"ok": "🟢", "degraded": "🟡", "down": "🔴"}
    lines = ["*🏥 システムヘルスチェック*\n"]

    for entry in report:
        icon = status_icons.get(entry.get("status", "ok"), "⚪")
        name = entry.get("component", "unknown")
        msg = entry.get("message", "")
        err_count = entry.get("error_count", 0)

        line = f"{icon} *{name}*: {msg}"
        if err_count > 0:
            line += f" (連続エラー: {err_count}回)"
        lines.append(line)

    has_issues = any(e.get("status") != "ok" for e in report)
    if has_issues:
        lines.append("\n⚠️ *障害が検出されています*")
    else:
        lines.append("\n✅ *全システム正常*")

    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)},
        }
    ]


def send_health_alert(slack_client=None, channel=None):
    """障害があればSlackにアラートを送信"""
    report = get_health_report()
    issues = [e for e in report if e.get("status") != "ok"]

    if not issues or not slack_client or not channel:
        return False

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "🚨 システム障害アラート"},
        },
    ] + format_health_for_slack()

    slack_client.chat_postMessage(
        channel=channel,
        blocks=blocks,
        text="🚨 システム障害が検出されました",
    )
    return True


if __name__ == "__main__":
    # テスト
    update_health("crowdworks_login", True, "正常ログイン")
    update_health("message_fetch", False, "タイムアウト")
    update_health("message_fetch", False, "タイムアウト")

    for entry in get_health_report():
        print(f"{entry['component']}: {entry['status']} - {entry['message']}")
