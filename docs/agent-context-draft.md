# Agent Context Draft

> 说明：这是一份给未来 agent / Codex 协作使用的长期上下文草稿，不直接修改 `AGENTS.md`。后续如需同步，请人工挑选其中稳定、长期有效的部分。

## product context

- 项目名当前在代码、仓库、镜像、页面标题中统一使用 `Noctra`。
- 产品定位不是“自动媒体库黑盒”，而是“可扫描、可预览、可确认、可追踪”的整理工作台。
- 当前核心闭环是：
  - 扫描 source
  - 识别番号
  - 预览 output
  - 勾选确认
  - 批量整理
  - 查看历史
- 当前主要用户场景是个人机器 + NAS，不是公网多用户系统。
- 后续明确会继续做“刮削”能力，因此当前很多 UI 和数据结构要为 scrape status 预留空间。

## ui / design preferences

- 统一风格方向：dark + console + devtool + terminal
- 喜欢：
  - 冷色分层
  - 微发光
  - 精密感
  - 信息密度清晰但不拥挤
- 不喜欢：
  - 传统 SaaS admin 风
  - 白底后台
  - 过度按钮化
  - 独立大浮窗
  - 很重的操作条

### 已明确收敛的交互偏好

- 状态操作区使用 integrated expanding badge
- 只允许 hover 展开，不允许 click pin
- 复制反馈使用局部 toast，不用顶部全局 success
- stats cards 是状态模块，不是按钮
- 批处理反馈使用 batch rail，不使用全屏 loading
- 历史页应明显区别于扫描页，更像 archive / log list

### 页面定位

- 扫描页：确认工作台
- 历史页：整理记录页

## engineering constraints

- 一套代码适配本地 / NAS / Docker，环境差异只通过 env / profile 控制。
- 不要再把绝对路径硬编码回脚本或代码。
- 当前本地默认端口：`4020`
- 本地默认 profile：
  - `test_data/source`
  - `test_data/dist`
  - `data/noctra.db`
- 当前镜像部署链是：
  - GitHub Actions 推 Docker Hub
  - NAS 拉 `acyua/noctra:latest`
  - Watchtower 轮询更新
- Watchtower 当前是每日轮询，不是 5 分钟高频轮询。
- 当前前端是单文件 `static/index.html`，不要轻易引入新的构建链。
- 当前批量整理已经使用 batch job 模型，后续相关功能优先在这套模型上扩展。

### 文件规则

- 目录使用纯番号
- 文件名保留语义后缀，但要规范化：
  - `字幕 / CH / ch` -> `-C`
  - `uncensored` -> `-UC`
- 要去掉中文、日文、演员名、编码标记等冗余尾巴

## collaboration preferences

- 用户更喜欢“小步快跑 + 先看效果 + 再细调”的协作方式。
- 做 UI 时，不要一上来推翻式改结构；优先在已有方向上微调。
- 如果用户只想调 table，不要顺手重做整页布局。
- 如果发现已有信息冲突，要明确写“待确认”，不要默默选一个。
- 解释 bug 时，优先说明根因，而不是只给结果。
- 本地测试如果会污染 `test_data`，调试后要主动恢复。
- 不要直接改 `AGENTS.md`，应先把长期上下文整理进独立草稿文档。

## do

- 先检查 `README`、`docs/`、`app/main.py`、`app/scanner.py`、`app/organizer.py`、`static/index.html`
- 在改 UI 前先理解页面定位：扫描页 != 历史页
- 保持中文主语义，英文只做弱辅助
- 保持状态 badge、hover glow、control rail、batch rail 的同一套视觉语言
- 优先用 env/profile 解决环境问题
- 继续补足“失败重试”“刮削预留”“历史页收口”

## don’t

- 不要回退到传统 SaaS admin 风格
- 不要把状态操作做回独立大浮窗 / 抽屉
- 不要把 stats cards 做成业务 tab 或按钮
- 不要让历史页继续套扫描页的大表格宽度与节奏
- 不要重新引入顶部全局复制成功提示
- 不要把环境差异重新硬编码进脚本
- 不要未经说明直接改 `AGENTS.md`

## 待确认 / 易冲突信息

- 命名层面：用户口头偶尔会说 `Nocta`，但仓库和代码当前使用 `Noctra`
- 旧文档中仍有部分早期端口、旧 UI、旧部署说明残留
- 当前开发现场可能存在 `dev` 分支上的未提交 UI 收口改动，提交前先看 `git status`
