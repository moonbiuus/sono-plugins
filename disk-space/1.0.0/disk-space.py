#!/usr/bin/env python3
"""Sono 动态板块：磁盘余量。

刷新命令。stdout 输出 Sono 板块数据面 JSON（headline + rows）。

数据来源：statfs（shutil.disk_usage），纯本地即时读取，无网络、无缓存、
不读任何文件内容。监看的卷：

- ``/``（系统卷，APFS 密封快照）
- ``/System/Volumes/Data``（数据卷，用户文件实际所在）

两条路径指向同一设备时（非 APFS 分卷布局）只画一行。查不到的卷不画，
全部查不到时降级为一行说明——不编造未观测到的状态。
"""

import json
import os
import shutil
import sys

# (挂载点, 卷名, row id)
VOLUMES = [
    ("/", "系统卷", "root"),
    ("/System/Volumes/Data", "数据卷", "data"),
]


def fmt_gb(n_bytes):
    """字节 → 十进制 GB 字符串（与 Finder 同一口径）。"""
    gb = n_bytes / 1_000_000_000
    if gb >= 10:
        return f"{gb:.0f}"
    return f"{gb:.1f}"


def collect():
    """返回 [(卷名, row id, total, used, free)]，查不到的卷跳过。"""
    volumes = []
    seen_devices = set()
    for path, name, row_id in VOLUMES:
        try:
            device = os.stat(path).st_dev
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        if device in seen_devices:
            continue
        seen_devices.add(device)
        if usage.total <= 0:
            continue
        volumes.append((name, row_id, usage.total, usage.used, usage.free))
    return volumes


def main():
    if sys.argv[1:] != ["refresh"]:
        print("usage: disk-space.py refresh", file=sys.stderr)
        sys.exit(2)

    volumes = collect()
    rows = []
    tightest = None  # (used_pct, 卷名, free)
    for name, row_id, total, used, free in volumes:
        used_pct = max(0, min(100, round(used / total * 100)))
        rows.append({
            "kind": "row",
            "id": row_id,
            "title": name,
            "detail": f"已用 {used_pct}% · 共 {fmt_gb(total)} GB",
            "badge": f"剩 {fmt_gb(free)} GB",
        })
        if tightest is None or used_pct > tightest[0]:
            tightest = (used_pct, name, free)

    if tightest is None:
        headline = "查不到任何卷的容量"
        rows.append({
            "kind": "note",
            "text": "statfs 对 / 与 /System/Volumes/Data 都失败了，这在正常的 macOS 上不该发生",
        })
    else:
        used_pct, name, free = tightest
        summary = f"{name}剩 {fmt_gb(free)} GB（{100 - used_pct}%）"
        headline = f"注意：{summary}" if used_pct >= 80 else summary

    json.dump({"headline": headline, "rows": rows}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
