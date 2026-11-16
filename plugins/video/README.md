# 视频播放

独立播放组件使用 mpv，在工作台内嵌播放本地文件及 HTTP、HTTPS、RTSP、UDP、RTP 地址。输入格式可选自动检测、H.264 裸流、MJPEG 裸流、MPEG-TS 或原始 YUV；原始 YUV 必须指定宽、高、像素格式和帧率，H.264 和 MJPEG 裸流也需要设置帧率。RTP 等流可能需要 SDP 描述文件；自定义 UDP 分包协议不属于通用解码，须按具体协议适配。没有实流验证前不声称兼容任何特定设备。

工作台播放页注册自身窗口；Agent 使用 `video.attach`、`video.play`、`video.pause`、`video.stop`、`video.seek`、`video.volume` 和 `video.status`，不自动播放。视频地址不要包含账号密码或敏感令牌，调用会进入共享日志。组件只终止自己启动的播放进程，禁用前须停止播放。

引擎来源：mpv 官网列出的 Windows 构建 [shinchiro/mpv-winbuild-cmake](https://github.com/shinchiro/mpv-winbuild-cmake/releases/tag/20261111)，文件 `mpv-x86_64-20261111-git-bcde6b93cc.7z`；归档 SHA-256 `f259b5fd4b5c395617c948a4fadcdf55bba1c5282fb7c13e88626b3f71072baf`。mpv 为 GPL 项目，构建及对应源码见该构建项目；外部引擎缺失时明确报告错误，不自动下载替换。源码分发不提交本地下载的 mpv.exe。

从源码构建时，在验证归档校验值后，将其中的 `mpv.exe` 和 `d3dcompiler_43.dll` 放在 `plugins/video/bin/`；`mpv.exe` 的 SHA-256 为 `3ea89fe7a4284b25dff3c72e1bde83e27324c90cfc4a074fe679293d19ee7c85`。引擎的 GPL 许可证见本目录 `LICENSE-mpv.txt`。工作台不会在后台下载播放器。
