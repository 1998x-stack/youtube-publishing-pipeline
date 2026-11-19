# YouTube Publishing Pipeline｜YouTube 自动上传与排期

**P0 已实现代码，但尚未配置无人值守云端部署。**

流程：Colab 生产视频 → Google Drive 存放 MP4/封面/字幕/manifest → 校验和人工审核 → YouTube 私享上传 → 等待处理 → 预约公开 → 记录状态。

## 核心模块

| 模块 | 位置 | 能力 |
| --- | --- | --- |
| 合同 | contracts | Manifest JSON Schema |
| 业务层 | src/youtube_pipeline/domain | 校验、状态转换 |
| 工作流 | src/youtube_pipeline/application | 扫描、上传、核验 |
| Drive | adapters/assets/drive.py | 分页列举、分块下载 |
| YouTube | adapters/youtube/client.py | 上传、封面、字幕、排期 |
| 数据库 | adapters/persistence/sqlite.py | 去重、任务领取、审计 |
| 测试 | tests | 离线单元与集成测试 |

## 本地启动

1. 安装 Python 3.11 及以上；执行 python -m pip install -e '.[dev]'。
2. 运行 pytest -q 与 ruff check src tests。
3. 按 [示例 manifest](examples/manifest.example.json) 创建视频目录。大文件先上传，manifest.json 最后上传。
4. 配置 Google Cloud 的 YouTube Data API v3、Drive API、OAuth 桌面客户端；把凭据放在 secrets/client_secret.json，执行 ytp auth。
5. 设置 YTP_DRIVE_ROOT_ID 和 YTP_YOUTUBE_CHANNEL_ID。
6. 执行 ytp scan、ytp status、ytp upload --execute、ytp reconcile --execute。

上传始终从 private 开始。没有 --execute 不进行 YouTube 写入操作。

**安全：** 必须显式审核、确认版权/授权及儿童内容与合成媒体标记。上传结果不明时不自动重传，标记 UNKNOWN_UPLOAD_RESULT。任务 ID 与 manifest 内容固定对应。

**限制：** P0 使用 SQLite（单节点持久化），不提供 Firestore 分布式锁、Secret Manager、Cloud Scheduler 的生产部署，详见 [后续路线](docs/roadmap.md)。

Colab 文件交接说明：[Colab 导出脚本](docs/colab-export.md)。
