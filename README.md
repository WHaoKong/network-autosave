# network-autosave 多网盘自动转存

一个基于 Flask 的多网盘自动转存系统，支持将分享链接自动保存到指定目录，并提供 Web 管理界面、定时调度与消息通知。

## 支持的网盘

| 网盘 | 标识 | 说明 |
|------|------|------|
| 百度网盘 | `baidu` | 基于 baidupcs-py，功能最完整 |
| 夸克网盘 | `quark` | 支持分享转存 |
| UC 网盘 | `uc` | 与夸克共用适配层 |
| 阿里云盘 | `aliyun` | 支持 Cookie 登录与转存 |
| 迅雷云盘 | `xunlei` | 支持分享转存 |

## 主要特性

- **自动转存**：将各网盘分享链接自动保存到指定目录
- **多网盘支持**：统一管理百度、夸克、UC、阿里云、迅雷等账号
- **多用户管理**：每个网盘可添加多个账号并切换
- **定时任务**：支持全局定时与单任务独立 Cron 规则
- **消息推送**：支持 25+ 种通知方式及自定义 Webhook
- **任务分类**：按分类组织与管理转存任务
- **状态监控**：通过 SSE 实时显示任务执行状态与日志
- **智能去重**：自动跳过已转存的文件
- **容量监控**：监控网盘容量，超阈值时发送通知
- **链接复制**：一键复制分享链接到剪贴板
- **智能填充**：自动获取分享文件夹名称并填充任务名
- **正则处理**：支持文件过滤与重命名的正则表达式
- **现代界面**：Vue 3 + Element Plus，响应式设计，支持移动端

## 系统要求

- Python 3.10（baidupcs-py 0.7.6 仅支持 3.10）
- Node.js 18+（仅开发或自行构建前端时需要）
- Windows / Linux / macOS

## 快速开始

### 方式一：本地开发（前后端分离）

**1. 克隆仓库**

```bash
git clone https://github.com/WHaoKong/network-autosave.git
cd network-autosave
```

**2. 安装后端依赖并启动**

```bash
pip install -r requirements.txt
python web_app.py
```

看到 `Server started at http://0.0.0.0:5000` 表示后端启动成功。

**3. 启动前端开发服务器**

```bash
cd frontend
npm install   # 首次运行需要
npm run dev
```

前端默认运行在 **http://localhost:3001**，API 请求会自动代理到后端 5000 端口。

**4. 访问应用**

在浏览器打开 [http://localhost:3001](http://localhost:3001)

> 默认登录账号：`admin`  
> 默认登录密码：`admin123`

### 方式二：仅启动后端（生产模式）

若已构建前端（`frontend/dist`），或只需 API 服务：

```bash
pip install -r requirements.txt
python web_app.py
```

访问 [http://localhost:5000](http://localhost:5000)

### 方式三：Docker 部署（推荐）

**使用 docker-compose：**

```bash
mkdir -p config log
docker-compose up -d
```

**使用 Docker CLI：**

```bash
mkdir -p config log

docker run -d \
  --name network-autosave \
  --restart unless-stopped \
  -p 5000:5000 \
  -v $(pwd)/config:/app/config \
  -v $(pwd)/log:/app/log \
  -e TZ=Asia/Shanghai \
  WHaoKong/network-autosave:latest
```

查看日志：

```bash
docker-compose logs -f
# 或
docker logs -f network-autosave
```

访问 [http://localhost:5000](http://localhost:5000)

> 默认登录账号：`admin`  
> 默认登录密码：`admin123`

## 通信模式

项目支持两种前后端通信方式：

1. **SSE 模式（推荐）**：通过 Server-Sent Events 实时推送任务状态与日志，体验更流畅。
2. **轮询模式**：前端定期请求后端获取最新状态，兼容性更好，无需额外配置。

开发环境下前端通过 Vite 代理 `/api` 到后端；生产环境下由 Flask 直接托管构建后的静态资源。

## 目录结构

```
network-autosave/
├── config/                  # 配置文件目录
│   ├── config.json          # 运行时配置（自动生成）
│   └── config.template.json # 配置模板
├── frontend/                # Vue 3 前端（Vite + Element Plus）
│   ├── src/
│   └── dist/                # 构建产物（Docker / 生产部署）
├── log/                     # 日志目录
├── scripts/                 # 辅助脚本
├── static/                  # 旧版静态资源（兼容保留）
├── aliyun_storage.py        # 阿里云盘适配
├── quark_storage.py         # 夸克 / UC 网盘适配
├── xunlei_storage.py        # 迅雷云盘适配
├── storage.py               # 存储管理核心
├── scheduler.py             # 任务调度
├── notify.py                # 通知模块
├── web_app.py               # Web 应用入口
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

### 主要模块

| 模块 | 说明 |
|------|------|
| `web_app.py` | Web 应用核心，HTTP API 与 SSE 推送 |
| `storage.py` | 多网盘存储调度与百度网盘 API |
| `quark_storage.py` | 夸克 / UC 网盘转存适配 |
| `aliyun_storage.py` | 阿里云盘转存适配 |
| `xunlei_storage.py` | 迅雷云盘转存适配 |
| `scheduler.py` | 定时任务调度与执行 |
| `notify.py` | 多种通知渠道推送 |
| `utils.py` | 通用工具函数 |

## 使用说明

### 1. 添加网盘账号

1. 在浏览器中登录对应网盘网页版
2. 按 F12 打开开发者工具，获取 Cookie
3. 在系统「用户管理」中选择网盘类型，填写用户名与 Cookie 并保存

各网盘 Cookie 获取方式类似，具体字段因平台而异。添加后可在用户列表中切换当前使用的账号。

### 2. 添加转存任务

1. 点击「添加任务」
2. 填写任务信息：
   - **网盘类型**：选择转存目标网盘
   - **任务名称**（可选）：输入分享链接后会自动获取文件夹名称
   - **分享链接**（必填）
   - **提取码**（如需要）
   - **保存目录**（必填）：会随任务名称智能同步
   - **定时规则**（可选）：Cron 表达式
   - **分类**（可选）
   - **过滤表达式**（可选）：正则过滤需转存的文件
   - **重命名表达式**（可选）：正则重命名转存的文件

**智能功能：**

- **自动填充任务名称**：输入分享链接后自动获取文件夹名称
- **保存目录同步**：任务名称变化时自动更新保存目录末级文件夹名
- **编辑检测**：手动编辑保存目录后，当前任务停止自动同步
- **分享链接复制**：任务列表中可一键复制分享链接
- **正则文件过滤**：如 `^(\d+)\.mp4$` 只转存以数字开头的 mp4 文件
- **正则文件重命名**：如 `第(\d+)集\.mp4` 将匹配数字替换为指定格式

> **注意**：百度网盘 API 对重命名操作有严格的频率限制，频繁重命名可能导致失败或触发风控。建议优先调整分享源文件名，谨慎使用重命名功能。

### 3. 定时设置

- **全局定时规则**：适用于未设置自定义定时的任务
- **单任务定时**：可为每个任务设置独立 Cron 规则

Cron 示例：

| 表达式 | 说明 |
|--------|------|
| `*/5 * * * *` | 每 5 分钟执行一次 |
| `0 */1 * * *` | 每小时执行一次 |
| `0 8,12,18 * * *` | 每天 8、12、18 点执行 |

### 4. 通知设置

系统支持 25+ 种通知方式，包括但不限于：

- **PushPlus**、**Bark**、**钉钉机器人**、**飞书机器人**
- **企业微信**、**Telegram**、**SMTP 邮件**
- **自定义 Webhook** 及 Gotify、iGot、ServerJ、PushDeer 等

配置步骤：

1. 在系统设置中启用通知功能
2. 填写对应服务的 Token / 密钥等字段
3. 点击「测试通知」验证配置
4. 支持同时配置多种通知方式

**通知延迟合并**：多个任务在短时间（默认 30 秒）内完成时，通知会合并为一条发送，减少打扰。

### 5. 网盘容量监控

1. 在系统设置中启用「网盘容量提醒」
2. 设置容量提醒阈值（默认 90%）
3. 设置检查时间（默认每天 00:00）
4. 使用量超过阈值时，通过已配置的通知渠道发送警告

## 配置文件说明

`config/config.json` 主要结构示例：

```json
{
    "baidu": {
        "users": {},
        "current_user": null,
        "tasks": []
    },
    "quark": {
        "users": {},
        "current_user": null
    },
    "aliyun": {
        "users": {},
        "current_user": null
    },
    "xunlei": {
        "users": {},
        "current_user": null
    },
    "uc": {
        "users": {},
        "current_user": null
    },
    "retry": {
        "max_attempts": 3,
        "delay_seconds": 5
    },
    "cron": {
        "default_schedule": ["0 10 * * *"],
        "auto_install": true
    },
    "notify": {
        "enabled": false,
        "notification_delay": 30,
        "direct_fields": {
            "PUSH_PLUS_TOKEN": "",
            "WEBHOOK_URL": ""
        }
    },
    "quota_alert": {
        "enabled": true,
        "threshold_percent": 90,
        "check_schedule": "0 0 * * *"
    },
    "scheduler": {
        "max_workers": 1,
        "misfire_grace_time": 3600,
        "coalesce": true,
        "max_instances": 1
    },
    "auth": {
        "users": "admin",
        "password": "admin123",
        "session_timeout": 3600
    }
}
```

首次运行时会从 `config.template.json` 自动生成。建议修改默认登录密码后再部署到公网环境。

## 常见问题

1. **任务执行失败**
   - 检查分享链接是否有效、提取码是否正确
   - 确认对应网盘账号 Cookie 未过期
   - 查看 `log/` 目录下的日志了解详细原因

2. **定时任务不执行**
   - 确认 Cron 表达式格式正确
   - 检查系统时间是否准确
   - 查看调度器日志

3. **前端页面空白或 API 报错**
   - 确认后端已在 5000 端口正常运行
   - 开发模式下确认前端代理配置正确（默认代理到 `127.0.0.1:5000`）

4. **通知推送失败**
   - 验证 Token / 配置是否正确
   - 使用「测试通知」功能排查
   - 检查网络与防火墙设置

5. **多网盘账号切换无效**
   - 确认已在用户管理中设为当前用户
   - 添加任务时选择正确的网盘类型与账号

6. **正则表达式问题**
   - 确认语法正确，可用在线工具验证
   - 过滤表达式用于筛选文件，重命名表达式用于改名
   - 重命名可能因频率限制失败，建议谨慎使用

## 开发说明

| 服务 | 地址 | 说明 |
|------|------|------|
| 后端 API | http://localhost:5000 | Flask 应用 |
| 前端开发服务器 | http://localhost:3001 | Vite 开发服务器 |
| API 代理 | `/api` → `:5000/api` | 前端自动代理到后端 |

构建前端生产包：

```bash
cd frontend
npm install
npm run build:prod
```

更多启动方式见 [终端启动命令.md](./终端启动命令.md) 与 [前端开发启动指南.md](./前端开发启动指南.md)。

版本更新记录请见 [Releases](https://github.com/WHaoKong/network-autosave/releases)。

## 许可证

本项目采用 [AGPL-3.0](./LICENSE) 许可证，与上游项目保持一致。

## 致谢

本项目基于 **[kokojacket/baidu-autosave](https://github.com/kokojacket/baidu-autosave)** 二次开发。感谢原作者 **kokojacket** 及所有贡献者开源了这套完善的百度网盘自动转存方案，为本项目提供了坚实的架构基础与丰富的功能实现。

同时感谢以下开源项目：

- [Flask](https://flask.palletsprojects.com/)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [baidupcs-py](https://github.com/PeterDing/BaiduPCS-Py)
- [quark-auto-save](https://github.com/Cp0204/quark-auto-save) — 夸克网盘自动转存，提供了很好的参考
- [Vue.js](https://vuejs.org/) / [Element Plus](https://element-plus.org/) / [Vite](https://vitejs.dev/)
