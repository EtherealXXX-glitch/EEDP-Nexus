# SLogic Combo8 插件

独立、可拆卸的 Agent 组件，不接管串口或烧录插件。USB 设备须处于蓝灯逻辑分析仪模式。

引擎来自 Sipeed 官方发布：
https://github.com/sipeed/SLogic/releases/tag/release-2.3.3

文件 `bin/sigrok-cli.exe` 对应 `sigrok-cli-SLogic-2.3.3-windows-x86_64.exe`，SHA-256：
`7ca7f046ea67ce3a4cd1dce02795f7ea36f0ca956cc595743e1ac076ca221307`。
引擎报告 sigrok-cli 0.8.0，包含 SLogic 驱动、libsigrokdecode 及 Python 解码环境。

操作顺序：devices → capabilities → inspect → 用户确认采样接线及范围后 start → status。
只测量 Combo8 支持范围内的逻辑信号（官方输入范围 0–3.6V），先共地。不得将其他 SLogic 型号的阈值/电压范围套用到 Combo8。

采样有明确时长及整个任务超时，等待触发也计入超时。取消只停止本插件拥有的进程树。
V1 每次只允许一个采集或离线处理任务，任务输出使用唯一目录，不覆盖已有文件。
设备能力现场读取；Windows 带宽保守限制为 160Mb/s，单次最多一亿采样点。

decode 要求明确解码器与引脚映射，支持 UART、I2C、SPI 等引擎已有解码器。
可先调用 decoder 查询其选项；解码无注释时 `annotations=false`，不会宣称识别成功。
export 支持 VCD/CSV。decode/export 只读现有 .sr，不访问 USB。

设置由工作台记忆；通信调用、错误和结果写入共享事件库，原始文件及 manifest 在 `.state/logs/slogic/<任务>/`。
任务目录默认保留，不自动删除。完整 stdout/stderr 与命令保留，status 返回结果路径及 SHA-256。

已迁移 schema 1.1：所有动作声明读写性质；`start` 要求当次确认 signal_voltage 和 common_ground，未知电压拒绝采样。
附带 samples/synthetic-uart-100000.sr 为人工生成的 UART 100000 波特离线示例（不是设备实采），界面“示例波形”可直接查看，无需连接被测电路。
主界面右侧逻辑分析入口提供内嵌波形工作区，启用状态变化时同步显示/移除。波形精确视图与活动包络明确区分，缩放/平移不重新采集。
查看器将总览及最近 8 个精细视窗保留在本地；缩放和平移即时绘制缓存，后台补精度，避免停下滚动后画面才追上。小波形全缓存后不再请求后台。
任务目录纳入日志分类、ZIP 导出及归档，历史保护同共享策略；运行中和最近任务保留原位置。
