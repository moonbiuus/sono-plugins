#!/usr/bin/env python3
"""构建 Sono 插件注册表索引。

读 plugins/<id>.json 上架条目 → 解析插件内容位置 → 校验结构 → 算每个文件的
sha256 → 生成 index.json 与 mirror/<id>/<version>/ 目录。

哈希不是手写的：作者的条目只提供 repo + tag（+ 可选 path），本脚本按 tag 取
确切字节算哈希。「改了内容忘了改索引」在结构上不可能。

内容解析顺序（每个条目）：
1. repo 是注册表自己（moonbiuus/sono-plugins）→ 直接读本仓库的 path 目录；
2. `--local-source <id>=<本地路径>` 指过来的本地目录（CI 首次构建 / 本地开发用，
   避免依赖远端 tag 已存在）；
3. 从 raw.githubusercontent.com 按 repo + tag 下载（正式 CI 路径）。

index.json 的字段名与日期格式以 Sono 客户端 `SonoKit/PluginCommunity.swift` 的
`PluginRegistryEntry` 为准：日期必须是不带小数秒的完整 ISO8601（客户端用
JSONDecoder 的 .iso8601 策略，`"2026-07-28"` 这种裸日期解不出来）。

用法：
    python3 scripts/build_index.py                # 构建 index.json 与 mirror/
    python3 scripts/build_index.py --check        # 只校验（PR CI），不写任何文件
    python3 scripts/build_index.py --local-source disk-space=../sono-plugin-disk-space
"""

import argparse
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_SLUG = "moonbiuus/sono-plugins"

MAX_FILE_BYTES = 256 * 1024
CATEGORIES = {"system", "monitor", "info", "dev"}
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
ID_BAD_CHARS = set('/\\:')


class Problem(Exception):
    pass


def check_id(pid: str):
    if not pid or len(pid) > 100:
        raise Problem(f"id 为空或超过 100 字符: {pid!r}")
    if not pid.isascii():
        raise Problem(f"id 必须是 ASCII: {pid!r}")
    if any(c.isspace() or c in ID_BAD_CHARS or not c.isprintable() for c in pid):
        raise Problem(f"id 不得含空白、/ \\ : 或控制字符: {pid!r}")


def github_slug(repo: str):
    m = re.match(r"^https://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", repo)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def load_json(name: str, data: bytes):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Problem(f"{name} 不是合法的 UTF-8 JSON: {e}")


class Source:
    """一个插件的内容来源：给文件名，回字节。"""

    def __init__(self, describe, reader):
        self.describe = describe
        self._reader = reader
        self._cache = {}

    def read(self, name: str) -> bytes:
        if name not in self._cache:
            data = self._reader(name)
            if len(data) > MAX_FILE_BYTES:
                raise Problem(f"{name} 超过 {MAX_FILE_BYTES // 1024}KB（{len(data)} 字节）")
            self._cache[name] = data
        return self._cache[name]


def local_source(directory: Path) -> Source:
    def reader(name: str) -> bytes:
        path = directory / name
        if not path.is_file():
            raise Problem(f"{directory} 下缺少 {name}")
        return path.read_bytes()
    return Source(str(directory), reader)


def remote_source(slug: str, tag: str, sub_path: str) -> Source:
    prefix = f"https://raw.githubusercontent.com/{slug}/{tag}/"
    if sub_path:
        prefix += sub_path.rstrip("/") + "/"

    def reader(name: str) -> bytes:
        url = prefix + name
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        except OSError as e:
            raise Problem(f"下载失败 {url}: {e}")
    return Source(prefix, reader)


def resolve_source(entry: dict, local_sources: dict) -> Source:
    pid, repo = entry["id"], entry["repo"]
    slug = github_slug(repo)
    if slug is None:
        raise Problem(f"repo 不是可解析的 github.com 地址: {repo}")
    sub_path = entry.get("path") or ""
    if slug == REGISTRY_SLUG:
        if not sub_path:
            raise Problem("repo 指向注册表自身时必须给 path")
        return local_source(REPO_ROOT / sub_path)
    if pid in local_sources:
        base = Path(local_sources[pid]).resolve()
        return local_source(base / sub_path if sub_path else base)
    return remote_source(slug, entry["tag"], sub_path)


def validate_board(pid: str, board: dict, scripts: list):
    if not isinstance(board, dict):
        raise Problem("板块声明的顶层不是对象")
    if board.get("board") != pid:
        raise Problem(f"板块声明 board={board.get('board')!r} 与插件 id {pid!r} 不一致")
    exec_block = board.get("exec")
    if not isinstance(exec_block, dict):
        raise Problem("板块声明缺少 exec 段")
    exec_file = exec_block.get("file")
    allowed = {f"~/.sono/boards/bin/{pid}/{s}" for s in scripts}
    if exec_file not in allowed:
        raise Problem(
            f"exec.file 必须是 ~/.sono/boards/bin/{pid}/<脚本名>（脚本名取自 "
            f"manifest.files.scripts），实际是 {exec_file!r}")
    refresh = exec_block.get("refresh")
    if not isinstance(refresh, dict) or not isinstance(refresh.get("argv"), list) \
            or not refresh["argv"] or not all(isinstance(a, str) for a in refresh["argv"]):
        raise Problem("exec.refresh.argv 缺失或不是非空字符串数组")
    argv_texts = [json.dumps(refresh["argv"])]
    for action in exec_block.get("actions") or []:
        if not isinstance(action, dict) or not isinstance(action.get("argv"), list):
            raise Problem("actions 里存在没有 argv 数组的动作")
        argv_texts.append(json.dumps(action["argv"]))
    for text in argv_texts:
        if '"sh", "-c"' in text or '"bash", "-c"' in text or "sh -c" in text:
            raise Problem("argv 不得经 shell（发现 sh -c / bash -c）")


def validate_script(name: str, data: bytes):
    if b"\x00" in data:
        raise Problem(f"脚本 {name} 含 NUL 字节，像二进制（拒收线）")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Problem(f"脚本 {name} 不是 UTF-8 文本（拒收线）")
    if re.search(r"\bsh\s+-c\b", text):
        raise Problem(f"脚本 {name} 含 `sh -c`（argv 不经 shell，拒收线）")


def build_entry(entry_path: Path, local_sources: dict):
    entry = load_json(entry_path.name, entry_path.read_bytes())
    pid = entry.get("id")
    if not isinstance(pid, str):
        raise Problem(f"{entry_path.name} 缺少字符串 id")
    check_id(pid)
    if entry_path.stem != pid:
        raise Problem(f"条目文件名 {entry_path.name} 必须等于 <id>.json")
    for key in ("repo", "tag"):
        if not isinstance(entry.get(key), str) or not entry[key]:
            raise Problem(f"{entry_path.name} 缺少字符串 {key}")

    source = resolve_source(entry, local_sources)
    manifest = load_json("manifest.json", source.read("manifest.json"))

    if manifest.get("id") != pid:
        raise Problem(f"manifest.id={manifest.get('id')!r} 与条目 id {pid!r} 不一致")
    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        raise Problem(f"manifest.version 不是 semver: {version!r}")
    for key in ("name", "description"):
        if not isinstance(manifest.get(key), str) or not manifest[key]:
            raise Problem(f"manifest.{key} 缺失或为空")
    author = manifest.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str):
        raise Problem("manifest.author.name 缺失")
    category = manifest.get("category")
    if category not in CATEGORIES:
        raise Problem(f"manifest.category 必须是 {sorted(CATEGORIES)} 之一: {category!r}")

    files_decl = manifest.get("files")
    if not isinstance(files_decl, dict) or not isinstance(files_decl.get("board"), str):
        raise Problem("manifest.files.board 缺失")
    board_file = files_decl["board"]
    scripts = files_decl.get("scripts")
    if not isinstance(scripts, list) or not scripts \
            or not all(isinstance(s, str) and s for s in scripts):
        raise Problem("manifest.files.scripts 缺失或为空")
    preview_file = files_decl.get("preview")
    if preview_file is not None and not isinstance(preview_file, str):
        raise Problem("manifest.files.preview 若存在必须是字符串")

    board = load_json(board_file, source.read(board_file))
    validate_board(pid, board, scripts)
    for script in scripts:
        validate_script(script, source.read(script))
    if preview_file:
        load_json(preview_file, source.read(preview_file))
    source.read("README.md")  # 必须存在（商店详情页正文）

    file_names = [
        "manifest.json", board_file, *scripts, "README.md",
        *([preview_file] if preview_file else []),
    ]
    # 去重但保序（board_file 理论上不会与其他重名，防御一下）
    file_names = list(dict.fromkeys(file_names))
    hashes = {
        name: "sha256:" + hashlib.sha256(source.read(name)).hexdigest()
        for name in file_names
    }

    disclosures = manifest.get("disclosures")
    if not isinstance(disclosures, dict):
        raise Problem("manifest.disclosures 缺失（空的键写 []，不要省略）")
    for key in ("network", "reads", "writes", "spawns"):
        if not isinstance(disclosures.get(key), list):
            raise Problem(f"manifest.disclosures.{key} 缺失或不是数组")

    reviewed_at = entry.get("reviewedAt")
    if reviewed_at is not None and not re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", reviewed_at):
        raise Problem(
            f"reviewedAt 必须是不带小数秒的完整 ISO8601（如 2026-07-28T00:00:00Z），"
            f"客户端的 .iso8601 解码器解不出裸日期: {reviewed_at!r}")

    index_entry = {
        "id": pid,
        "name": manifest["name"],
        "description": manifest["description"],
        "icon": board.get("icon"),
        "category": category,
        "official": bool(entry.get("official", False)),
        "version": version,
        "author": {"name": author["name"], "github": author.get("github")},
        "repo": entry["repo"],
        "path": entry.get("path"),
        "tag": entry["tag"],
        "board": board_file,
        "files": hashes,
        "scripts": scripts,
        "disclosures": {k: disclosures[k] for k in ("network", "reads", "writes", "spawns")},
        "preview": preview_file,
        "reviewedAt": reviewed_at,
    }
    # 可选键缺席就整个不写：客户端按「键可能缺席」解码，null 只添噪
    index_entry = {k: v for k, v in index_entry.items() if v is not None}
    if index_entry["author"].get("github") is None:
        index_entry["author"].pop("github", None)
    mirror_files = {name: source.read(name) for name in file_names}
    return index_entry, mirror_files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="只校验与 dry run，不写 index.json 与 mirror/")
    parser.add_argument("--local-source", action="append", default=[],
                        metavar="ID=PATH",
                        help="外部仓库条目改从本地目录读内容（可多次）")
    args = parser.parse_args()

    local_sources = {}
    for item in args.local_source:
        pid, sep, path = item.partition("=")
        if not sep or not pid or not path:
            parser.error(f"--local-source 需要 ID=PATH 形式: {item!r}")
        local_sources[pid] = path

    entry_paths = sorted((REPO_ROOT / "plugins").glob("*.json"))
    if not entry_paths:
        print("plugins/ 下没有任何条目", file=sys.stderr)
        return 1

    plugins, mirrors, errors = [], {}, []
    seen = set()
    for entry_path in entry_paths:
        try:
            index_entry, mirror_files = build_entry(entry_path, local_sources)
            pid = index_entry["id"]
            if pid in seen:
                raise Problem(f"id 重复: {pid}")
            seen.add(pid)
            plugins.append(index_entry)
            mirrors[(pid, index_entry["version"])] = mirror_files
            print(f"ok: {pid} {index_entry['version']}（{len(mirror_files)} 个文件）")
        except Problem as e:
            errors.append(f"{entry_path.name}: {e}")

    if errors:
        for line in errors:
            print(f"error: {line}", file=sys.stderr)
        return 1

    index = {
        "version": 1,
        "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "plugins": sorted(plugins, key=lambda p: p["id"]),
    }
    if args.check:
        print(f"check 通过：{len(plugins)} 个条目，未写任何文件")
        return 0

    index_path = REPO_ROOT / "index.json"
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(f"写入 {index_path.relative_to(REPO_ROOT)}")

    for (pid, version), files in mirrors.items():
        target = REPO_ROOT / "mirror" / pid / version
        target.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (target / name).write_bytes(data)
        print(f"写入 mirror/{pid}/{version}/（{len(files)} 个文件）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
