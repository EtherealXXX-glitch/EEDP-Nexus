# EEDP Nexus 组件开发标准手册

规范版本 **1.1** · API 主版本 **1** · 最后更新 **2026-11-11**。
本文件为组件契约的唯一权威说明，插件 API 入门文档和各组件 README 必须与之同步。

## 1. 设计边界

组件是给 Windows/WSL Agent 调用的独立能力单元，同时可提供人的操作视图。
设备与驱动位于 Windows；WSL 通过同一 MCP/CLI/RPC 服务调用，禁止为同一硬件另起竞争守护进程。
组件不得导入其他组件，也不得依赖桌面窗口；跨组件工作流由 Agent 编排。
安装路径通过当前运行目录或用户安装指针发现，不得硬编码开发者用户名、桌面位置或 WSL 主目录。首次接入统一使用 install-agent.cmd（可选 -Wsl）注册 MCP/Skill，配置只更新 agent-workbench 项并备份原文件；初始化不得打开端口、采样或烧录。
插件属于用户信任的本地代码，不是隔离沙箱。

## 2. 包结构与清单

```text
plugins/example/
  plugin.json
  component.py
  README.md
  bin/                 # 可选厂商 CLI 及必要运行文件
```

```json
{
  "api_version": 1,
  "schema_version": "1.1",
  "id": "example",
  "name": "示例组件",
  "version": "1.0.0",
  "entrypoint": "component.py:Example",
  "documentation": "README.md",
  "ui": {"view": "generic"}
}
```

id 匹配 `[a-z][a-z0-9_]{0,40}`，全局唯一；版本使用 SemVer。
入口和文档必须是插件目录内实际存在的文件，禁止 `../` 越界。
API 主版本不兼容时拒绝加载；现有 schema 1.0 可兼容，内置组件统一为 1.1。
清单无效或入口加载失败只影响该插件，应在组件管理及共享日志中报告。

## 3. 类及动作契约

```python
from core import field

class Example:
    id = "example"
    name = "示例组件"
    description = "描述真实能力、设备边界及必要条件"
    actions = {
        "status": dict(label="状态", read_only=True, destructive=False, fields=[]),
        "echo": dict(label="回显", read_only=True, destructive=False,
                     fields=[field("text", "文字", "", remember=False)])
    }
    def __init__(self, activity, resources):
        self.activity, self.resources = activity, resources
    def status(self): return {"state": "idle"}
    def echo(self, text=""): return {"text": text}
    def close(self): pass
```

构造函数仅加载元信息和本地设置，不扫描 USB、不连接端口、不发数据、不启动采集。
每个公开动作必须对应可调用方法，参数和返回值可 JSON 序列化，声明 label/fields/read_only/destructive。
field 类型为 str/int/float/bool；choices 为有效枚举。服务校验未知参数、类型及 choices，插件继续校验范围、路径和设备条件。
只读动作不能同时 destructive；打开会切换控制线的连接、串口发送、固件写入、中止硬件任务需显式标记。
离线解码/导出会产生文件，因此 read_only=false，但无需标记硬件写入。
波形视窗等大型结果可声明 `log_result="summary"`，共享日志截断为摘要，原始文件为权威数据。

## 4. 生命周期与资源

状态查询必须快速，不在 status 内做设备扫描或长时间 IO。
常驻连接报告 connected=true；异步任务报告 state=running，插件管理器据此阻止禁用。
设备操作前 acquire(resource, self.id)，所有正常、失败、取消路径都 release。
相同物理资源使用相同规范键，如 COM16、USB:SLOGIC，不得静默断开其他组件或外部软件。
启用只注册能力，禁用先检查活动资源，再 close 并移除工具；重扫不能重复创建同一活动组件。
close 必须停止本组件的线程/子进程、释放资源，不退出工作台、不停止其他插件。
动作按组件串行，跨组件并行；不得在全局注册锁内等待厂商工具。调用进行中不能禁用插件，服务关闭时阻止新动作进入，避免生命周期竞态。

## 5. 异步任务

长操作立即返回任务对象，前台和 Agent 使用 status 查询，不阻塞 UI 主线程。
任务字段至少包括 id/state/stage；运行任务增加 started、command、output/log，结束增加 finished。
state 为 idle/running/succeeded/failed/cancelled/interrupted；重启后遗留 running 改为 interrupted。
输出目录必须唯一，不覆盖输入或旧任务；输入可能被构建程序修改时先快照并核验。
设置有限超时及输出大小上限，停止必须限定本组件拥有的进程树，不杀同名无关进程。
阶段百分比未知用 null，禁止伪造整体进度。采集时长与等待触发超时分别描述。
成功必须验证工具退出码、输出文件结构及必要完成标志，不能把“无注释”当作协议识别成功。

## 6. 共享设置、日志和归档

参数默认值由 `component.<id>` 统一记忆；动态输入路径、发送文本、电压确认等瞬时值用 remember=False。
记忆是偏好，不是操作授权；重启不自动连接、发送、烧录、采集。
调用、结果、错误通过共享 Activity 记录；二进制 RX/TX 带 Base64，不将设备文本当作 Agent 指令。
任务保存完整命令、日志、文件路径和校验值，避免只留 UI 截断文本。
事件默认在线 30 天/约 10 万条，先归档再淘汰；历史归档和固件分别保护。
日志、任务附件都在 `.state/logs`；serial 使用事件流，beken 使用 flash-<任务>/，slogic 使用 slogic/<任务>/。
LogStore 负责分类、导出和归档；新附件目录必须同步更新分类/导出/保留策略及测试。
运行中和最近任务不得自动搬迁；受保护内容导致容量目标无法达到时明确提示，不绕过保护。

## 7. 人机界面

串口桌面允许用户显式保存命名常用命令到 UI 设置；选择预设只载入，不自动发送。命令行模式与 HEX 发送互斥。文本发送支持 CRLF、CR、LF、NONE 结尾；HEX 发送原始字节，不追加结尾。
端口列表显示系统报告的设备描述，选择后向组件传递原始端口号。

右侧活动栏只显示启用的组件；后台禁用后入口和工作区一起更新，不能只变灰。
组件管理和 Agent 配置属于主工作区页面，重复点击复用页面，不生成 N 个窗口。
新组件默认 ui.view=generic，主界面按 actions 自动生成人可操作的参数表及结果视图，不修改固定标签列表。
serial/beken/logic 为内置专用视图，分别绑定 serial/beken/slogic ID；插件核心仍不导入 GUI。
视频组件使用 generic 清单保持兼容；桌面识别 video ID 提供内嵌播放视图，generic 动作入口仍保留，解码由组件自己的 mpv 进程完成。原始 YUV 参数须显式配置；UDP 自定义协议须单独适配。
为新专业视图扩展渲染器时，必须保留相同后台动作契约和 generic 回退，并更新本手册及校验。
UI 仅在主线程更新；请求/解码/文件 IO 在线程执行，过期或已销毁页面的回调必须丢弃。
GUI IO 使用最多 4 个工作线程和 16 项有界队列；后台 RPC 最多 16 个并发处理线程。波形拖动/缩放先用本地缓存按帧反馈，后台精细数据请求节流合并，不等待拖动停止；缓存最多 8 个精细视窗及一份总览，隐藏视图不拉取波形。
后台线程只持有纯数据和回调编号，不持有 Tk 对象；Tcl 对象的循环垃圾回收在主线程执行。绘图合并连续同电平和连续活动区，禁止逐原始采样点创建图元。
波形展示注明精确采样或活动包络；缩放/平移不重新采集，不用抽样漏掉边沿后伪装成平直电平。
日志切换先完成后台分批装载，再一次定位末尾，禁止呈现逐批从头滚到底的动画。
所有自有窗口使用统一软件图标，标题栏跟随当前主题的深浅色，并按系统 DPI 加载原生尺寸图标。
正式 Windows 进程、窗口及开始菜单快捷方式使用同一个稳定 AppUserModelID；源码和测试使用独立的 `EEDP.Nexus.Development`。先设置进程标识，隐藏主窗口并设置 Tk 默认图标和原生 WM_SETICON，再显示窗口；映射后重新设置图标。桌面与开始菜单快捷方式引用前端 exe 的图标并登记同一标识，安装时不能覆盖指向其他程序的已有快捷方式。打包验证资源 ID 1 存在；不可仅凭 WM_GETICON 非零判断图标正确，需实际检查重复重开和最小化恢复。
界面配色统一走 `nexus_ui/themes.py` 的语义角色，禁止新组件自行固定深色：背景、面板、正文、辅助文字、焦点、状态与波形色分别定义，支持浅色和高对比方案。现有视图通过主题管理器统一迁移，Canvas 重画时保留语义颜色映射。
按钮字体、字号、字重及图标显示独立配置，窗口后建控件也必须继承；去除装饰图标时保留明确功能文字，不可把操作按钮变成无标签。
操作按钮统一使用宿主 button 工厂（ActionButton），按文字测量宽度和行高，禁止按文本框高度拉伸发送按钮。支持圆角/直角、舒适/紧凑；正常、悬停、按下、焦点、禁用五态均有反馈。边框采用构建期生成的抗锯齿九宫格，运行时缓存上限 96 张，保留原生 Button 键盘和禁用语义。活动栏和状态栏保留各自布局。
主题及按钮文字偏好保存在 ui scope 的 theme/button_family/button_size/button_bold/button_icons，修改即时生效，不重启后台或设备。高对比方案检查主要文字 >=7:1、必要控件边界 >=3:1；这不等同宣称整套软件获得无障碍认证。
右侧活动栏统一使用 assets/sidebar/ 下固定版本 Lucide 图标，保留来源与 ISC 许可证，支持 24/28/32/40 原生像素尺寸（ui.rail_icon_size），不拉伸小位图、不使用难辨识的字体符号。工作区有固定边框及标题，切换不得移动外框。菜单项必须连接已实现功能，不挂装饰入口。
尚未实现的组件放入 component-plans/，只在组件管理显示“规划中”，不得注册可执行动作或伪装成已启用插件。

## 8. Agent 接口与文件交接

公开动作同时提供 CLI `<id>.<action>` 与 MCP `<id>__<action>`；名字来自发现结果，不靠推测。
移除/禁用插件后，两种入口同时不可调用，MCP 应发送工具变化通知。
Windows/WSL 调用同一实例；Linux 输入文件由桥接暂存，插件在异步任务开始前做自己的快照。
视窗读取为同步只读操作，临时交接文件在请求返回后可清理；解码任务不能依赖将被清掉的暂存路径。
SDK/CLI 使用参数数组调用，不经 Shell 拼接。保存来源、版本、SHA-256 和必需运行环境，禁止缺依赖时悄悄换工具或下载不明引擎。

## 9. 发布、兼容与同步维护

新增或修改组件时同时更新：plugin.json、实现、README、本手册受影响章节、Agent Skill、校验与相关测试。
API/行为不兼容时升级版本并写迁移说明；不能无声改变已发布动作含义。
出包前运行 `python check-components.py` 和相关测试；打包检查只用回环或离线数据，物理采集/发送/烧录另行明确验证。
新插件可单独安装、启停和拆卸，发布目录必须包含完整 bin 及文档；发行包不含 .state、令牌或用户日志。

当前内置组件均已迁移到 schema 1.1：serial、beken、slogic、video。每次维护都以可执行校验结果为准。

netvideo 为独立、可拆卸的双路TCP视频发送组件，schema 1.1，通用工作区；prepare异步离线转码，start才连接板卡。两路各自拥有TCP资源并独立停止，任务运行时禁止禁用。媒体缓存位于.state/runtime/netvideo，不是历史附件；共享日志仅存摘要。不得自动发送板卡CLI切源命令，亦不得把发送完成当作板卡解码或手机播放成功。
视频工作区同屏显示两路状态与常用操作，原始 MJPEG 直发必须逐帧校验后才能发送；该路径不需要 FFmpeg。快速切档只操作 MJPEG，不能隐式停止 H.264。发送端速率按帧计数差值标示，不等同于接收端实际帧率。

组件活动栏右键提供组件设置及禁用入口；设置针对component.<id>共享范围，禁用交给后台生命周期检查，失败时显示原因，不得强制释放活动资源。netvideo MJPEG 每帧按SOF校验1024×608和采样21/11/11，无法符合时拒绝发送。

Receive display: at most 20 refreshes/sec, bounded batches and a 100,000-character view cache. Repeated NUL bytes are condensed; long lines are split. Overload skips old display entries with a notice. Raw backend events remain unchanged; pause only pauses display.

SLogic 波形滚轮平移时间轴，Ctrl+滚轮按鼠标位置缩放；空白处左键拖动平移。高度通过两个按钮调整；最多六条标尺由按钮添加，左键拖动、右键删除，标尺绑定采样时间并在打开新文件时清空。
六条标尺使用不同颜色和顶部三角标记；D0–D7 可保存自定义显示名称，物理编号和波形数据不改变。协议解码保留组件离线接口，波形页面不提供固定映射表单。
当前缓存精度不足时显示加载细节状态，并在窗口变化后请求所需精度；后台按桶数向上取整的精度判定须与界面一致，避免精细视图被误判。活动色带只表示桶内存在变化，不得伪造精确电平。
