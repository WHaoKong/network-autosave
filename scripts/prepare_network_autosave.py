# -*- coding: utf-8 -*-
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VERSION_TS = ROOT / "frontend" / "src" / "config" / "version.ts"
VERSION_TS.write_text(
    """// 版本管理配置
export const VERSION_CONFIG = {
  APP_VERSION: __APP_VERSION__,
  BUILD_TIME: __BUILD_TIME__,
  RELEASE_NOTES: 'network-autosave 1.0.0 初始发布',
  UPDATE_NOTES: {
    'v1.0.0': '多网盘自动转存工具 network-autosave 初始版本',
  }
} as const

export const APP_VERSION = VERSION_CONFIG.APP_VERSION
export const BUILD_TIME = VERSION_CONFIG.BUILD_TIME
export const RELEASE_NOTES = VERSION_CONFIG.RELEASE_NOTES
""",
    encoding="utf-8",
)

MAIN_TS = ROOT / "frontend" / "src" / "main.ts"
text = MAIN_TS.read_text(encoding="utf-8")
if "console.log(" in text:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith("console.log("):
            lines[i] = "console.log('网盘自动转存工具前端已启动')"
            break
    MAIN_TS.write_text("\n".join(lines) + "\n", encoding="utf-8")

README = ROOT / "README.md"
readme = README.read_text(encoding="utf-8", errors="replace")
if "baidu-autosave" in readme:
    readme = readme.encode("latin1", errors="ignore").decode("gb18030", errors="replace")
readme = readme.replace("baidu-autosave", "network-autosave")
readme = readme.replace("kokojacket/baidu-autosave", "WHaoKong/network-autosave")
readme = readme.replace("kokojacket/network-autosave", "WHaoKong/network-autosave")
readme = readme.replace("# 百度网盘自动转存", "# network-autosave 多网盘自动转存")
readme = readme.replace(
    "一个基于Flask的百度网盘自动转存系统",
    "一个基于 Flask 的多网盘自动转存系统，支持百度、夸克、UC、阿里云、迅雷等网盘",
)
README.write_text(readme, encoding="utf-8")

START_MD = ROOT / "\u7ec8\u7aef\u542f\u52a8\u547d\u4ee4.md"
if START_MD.exists():
    start_md = START_MD.read_text(encoding="gb18030", errors="replace")
    start_md = start_md.replace("baidu-autosave", "network-autosave")
    start_md = start_md.replace(r"D:\work\baidu-autosave", r"D:\Git\network-autosave")
    START_MD.write_text(start_md, encoding="utf-8")

print("metadata updated")
