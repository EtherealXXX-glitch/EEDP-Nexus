# Beken 烧录组件 v1.1

契约遵循工作台 `COMPONENT-STANDARD.md`。使用原生 beken 视图，Agent 使用 `beken.*` / `beken__*`。

inspect/status 只读；start 写入 Flash，cancel 可能打断烧录，均标为破坏性操作。
必须先预检精确固件、地址、长度与 SHA-256，再启动；组件不会抢占其他组件的串口。

start 返回异步任务，状态 idle/running/succeeded/failed/cancelled/interrupted；进度为当前擦除/写入阶段，未知值为 null。
按 CR/LF/CRLF 实时解析厂商输出。成功须本次日志同时包含三个完成标志，不可仅看退出码。

厂商引擎位于 bin/bk_loader.exe。每任务保存固件快照与日志，位于共享日志根目录 flash-<任务>/。
克隆源码后需放入合法获取的原厂引擎，或用 EEDP_BEKEN_ENGINE 指定本机位置；不再依赖开发者个人目录。缺少引擎不影响串口组件，烧录预检会明确报告缺失。
正在烧录的组件不能禁用；完成后自动释放端口。设置不会自动触发写入。
