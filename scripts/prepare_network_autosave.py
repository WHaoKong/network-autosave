from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

VERSION_TS = ROOT / "frontend" / "src" / "config" / "version.ts"
VERSION_TS.write_text(
    """// \u7248\u672c\u7ba1\u7406\u914d\u7f6e
export const VERSION_CONFIG = {
  APP_VERSION: __APP_VERSION__,
  BUILD_TIME: __BUILD_TIME__,
  RELEASE_NOTES: 'network-autosave 1.1.0\uff1a\u5938\u514b\u6bcf\u65e5\u7b7e\u5230\u3001\u901a\u77e5\u6807\u9898\u663e\u793a\u4efb\u52a1\u7ed3\u679c',
  UPDATE_NOTES: {
    'v1.1.0': '\u65b0\u589e\u5938\u514b\u6bcf\u65e5\u7b7e\u5230\u9886\u7a7a\u95f4\uff1b\u901a\u77e5\u5185\u5bb9\u6539\u4e3a\u4efb\u52a1\u540d\u79f0+\u6210\u529f/\u5931\u8d25\uff1b\u4fee\u590d\u53f3\u4e0a\u89d2\u663e\u793a\u767b\u5f55\u7528\u6237\u540d\u4e0e\u4e2d\u6587\u4e71\u7801',
    'v1.0.0': '\u591a\u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58\u5de5\u5177 network-autosave \u521d\u59cb\u7248\u672c',
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
    for index, line in enumerate(lines):
        if line.strip().startswith("console.log("):
            lines[index] = "console.log('\\u7f51\\u76d8\\u81ea\\u52a8\\u8f6c\\u5b58\\u5de5\\u5177\\u524d\\u7aef\\u5df2\\u542f\\u52a8')"
            break
    MAIN_TS.write_text("\n".join(lines) + "\n", encoding="utf-8")

README = ROOT / "README.md"
readme = README.read_text(encoding="utf-8", errors="replace")
if "baidu-autosave" in readme:
    readme = readme.encode("latin1", errors="ignore").decode("gb18030", errors="replace")
readme = readme.replace("baidu-autosave", "network-autosave")
readme = readme.replace("kokojacket/baidu-autosave", "WHaoKong/network-autosave")
readme = readme.replace("kokojacket/network-autosave", "WHaoKong/network-autosave")
readme = readme.replace(
    "# \u767e\u5ea6\u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58",
    "# network-autosave \u591a\u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58",
)
readme = readme.replace(
    "\u4e00\u4e2a\u57fa\u4e8eFlask\u7684\u767e\u5ea6\u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58\u7cfb\u7edf",
    "\u4e00\u4e2a\u57fa\u4e8e Flask \u7684\u591a\u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58\u7cfb\u7edf\uff0c"
    "\u652f\u6301\u767e\u5ea6\u3001\u5938\u514b\u3001UC\u3001\u963f\u91cc\u4e91\u3001\u8fc5\u96f7\u7b49\u7f51\u76d8",
)
README.write_text(readme, encoding="utf-8")

START_MD = ROOT / "\u7ec8\u7aef\u542f\u52a8\u547d\u4ee4.md"
if START_MD.exists():
    start_md = START_MD.read_text(encoding="gb18030", errors="replace")
    start_md = start_md.replace("baidu-autosave", "network-autosave")
    start_md = start_md.replace(r"D:\work\baidu-autosave", r"D:\Git\network-autosave")
    START_MD.write_text(start_md, encoding="utf-8")

print("metadata updated")
