#!/usr/bin/env python3
"""Sono 动态板块：Claude Code 与 Codex 的订阅额度剩余。

刷新命令。stdout 输出 Sono 板块数据面 JSON（headline + rows）。

数据来源：
- Claude：钥匙串 "Claude Code-credentials"（claude CLI 登录后写入）或
  ~/.claude/.credentials.json 里的 OAuth token，调 api.anthropic.com 的
  /api/oauth/usage 查 5 小时与一周窗口。
- Codex：~/.codex/sessions/ 最近会话文件里的 rate_limits 快照（本地文件，
  无需网络；数据新鲜度 = Codex 上一次运行的时刻）。

查不到的窗口不画，降级为一行说明——不编造未观测到的状态。
"""

import datetime
import glob
import json
import os
import subprocess
import sys
import urllib.request

HOME = os.path.expanduser("~")


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def fmt_reset(dt):
    """把重置时刻格式化成本地时间的短说法。"""
    local = dt.astimezone()
    nl = now().astimezone()
    if local.date() == nl.date():
        return local.strftime("今天 %H:%M")
    if local.date() == (nl + datetime.timedelta(days=1)).date():
        return local.strftime("明天 %H:%M")
    return f"{local.month}/{local.day} {local.strftime('%H:%M')}"


def fmt_age(dt):
    s = (now() - dt).total_seconds()
    if s < 90:
        return "刚刚"
    if s < 3600:
        return f"{int(s // 60)} 分钟前"
    if s < 86400:
        return f"{int(s // 3600)} 小时前"
    return f"{int(s // 86400)} 天前"


def window_label(minutes):
    """返回 (ASCII slug, 显示名)。"""
    if minutes == 300:
        return "5h", "5 小时"
    if minutes == 10080:
        return "weekly", "一周"
    if minutes % 1440 == 0:
        return f"{minutes // 1440}d", f"{minutes // 1440} 天"
    if minutes % 60 == 0:
        return f"{minutes // 60}h", f"{minutes // 60} 小时"
    return f"{minutes}m", f"{minutes} 分钟"


def pct(v):
    """utilization 可能是 0-100 或 0-1，统一成 0-100 的整数。"""
    v = float(v)
    if 0 < v < 1:
        v *= 100
    return max(0, min(100, round(v)))


# ---------- Claude ----------

def claude_token():
    try:
        out = subprocess.run(
            ["/usr/bin/security", "find-generic-password",
             "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=4)
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout.strip()), None
    except subprocess.TimeoutExpired:
        return None, "钥匙串在等待授权：先在终端手动跑一次这个脚本，并选「始终允许」"
    except Exception:
        pass
    path = os.path.join(HOME, ".claude", ".credentials.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f), None
        except Exception:
            return None, "~/.claude/.credentials.json 存在但不是合法 JSON"
    return None, "claude CLI 未登录：终端运行 claude，输入 /login 后这里就能显示"


def claude_windows():
    """返回 (windows, note)。windows: [(标签, 已用%, 重置时刻 datetime|None)]"""
    creds, err = claude_token()
    if creds is None:
        return [], err
    token = (creds.get("claudeAiOauth") or {}).get("accessToken") or creds.get("accessToken")
    if not token:
        return [], "登录凭据里没有 accessToken，格式可能变了"
    req = urllib.request.Request(
        "https://api.anthropic.com/api/oauth/usage",
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "sono-board-ai-quota/1",
        })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return [], "Claude token 已失效：终端运行 claude，重新 /login"
        return [], f"Claude 用量接口返回 HTTP {e.code}"
    except Exception as e:
        return [], f"查询 Claude 用量失败：{type(e).__name__}"

    labels = [("five_hour", "5h", "5 小时"), ("seven_day", "weekly", "一周"),
              ("seven_day_opus", "weekly-opus", "一周 Opus"),
              ("seven_day_sonnet", "weekly-sonnet", "一周 Sonnet")]
    windows = []
    for key, slug, label in labels:
        w = data.get(key)
        if not isinstance(w, dict) or w.get("utilization") is None:
            continue
        reset = None
        raw = w.get("resets_at")
        if isinstance(raw, (int, float)):
            reset = datetime.datetime.fromtimestamp(raw, datetime.timezone.utc)
        elif isinstance(raw, str):
            try:
                reset = datetime.datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
        windows.append((slug, label, pct(w["utilization"]), reset))
    if not windows:
        return [], "Claude 用量接口通了，但没认出任何窗口字段"
    return windows, None


# ---------- Codex ----------

def codex_windows():
    """返回 (windows, 快照时刻, note)。windows 同上。"""
    files = sorted(glob.glob(os.path.join(HOME, ".codex", "sessions",
                                          "*", "*", "*", "rollout-*.jsonl")),
                   key=os.path.getmtime, reverse=True)
    for path in files[:20]:
        best = None
        try:
            with open(path, errors="replace") as f:
                for line in f:
                    if '"rate_limits"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except ValueError:
                        continue
                    rl = (ev.get("payload") or {}).get("rate_limits")
                    if rl:
                        best = (ev.get("timestamp"), rl)
        except OSError:
            continue
        if best is None:
            continue
        ts_raw, rl = best
        try:
            ts = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            ts = datetime.datetime.fromtimestamp(os.path.getmtime(path),
                                                 datetime.timezone.utc)
        windows = []
        for part in (rl.get("primary"), rl.get("secondary")):
            if not isinstance(part, dict) or part.get("used_percent") is None:
                continue
            reset = None
            if isinstance(part.get("resets_at"), (int, float)):
                reset = datetime.datetime.fromtimestamp(part["resets_at"],
                                                        datetime.timezone.utc)
            slug, label = window_label(part.get("window_minutes") or 0)
            windows.append((slug, label, pct(part["used_percent"]), reset))
        if windows:
            return windows, ts, None
    return [], None, "在 ~/.codex/sessions/ 里没找到额度快照：跑一次 Codex 后就有了"


# ---------- 组装 ----------

def main():
    rows = []
    tightest = None  # (used, 描述)

    claude, claude_note = claude_windows()
    for slug, label, used, reset in claude:
        detail = f"已用 {used}%"
        if reset:
            detail += f" · {fmt_reset(reset)} 重置"
        rows.append({"kind": "row", "id": f"claude-{slug}",
                     "title": f"Claude · {label}", "detail": detail,
                     "badge": f"剩 {100 - used}%"})
        if tightest is None or used > tightest[0]:
            tightest = (used, f"Claude {label}窗口已用 {used}%")
    if claude_note:
        rows.append({"kind": "note", "text": f"Claude：{claude_note}"})

    codex, codex_ts, codex_note = codex_windows()
    for slug, label, used, reset in codex:
        detail = f"已用 {used}%"
        if reset:
            detail += f" · {fmt_reset(reset)} 重置"
        if codex_ts:
            detail += f" · {fmt_age(codex_ts)}的快照"
        rows.append({"kind": "row", "id": f"codex-{slug}",
                     "title": f"Codex · {label}", "detail": detail,
                     "badge": f"剩 {100 - used}%"})
        if tightest is None or used > tightest[0]:
            tightest = (used, f"Codex {label}窗口已用 {used}%")
    if codex_note:
        rows.append({"kind": "note", "text": f"Codex：{codex_note}"})

    if tightest is None:
        headline = "还没有可显示的额度数据"
    elif tightest[0] >= 80:
        headline = f"注意：{tightest[1]}"
    else:
        headline = f"最紧的是 {tightest[1]}"

    json.dump({"headline": headline, "rows": rows},
              sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
