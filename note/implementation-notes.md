## 2026-06-22

### 16:43 - 现行站点协议与修复边界

- 实测结果：BongaCams 的 `tools/amf.php` 可返回当前 CDN；CAM4 的 `www` REST 端点返回 401，而 `hu.cam4.com` 配合 `webchat.cam4.com/requestAccess` 可返回直播 HLS；CamSoda 的 `chat/react` 与 LL-HLS 主播放列表可用；Stripchat 离线时 `cam` 为列表，直播主播放列表则使用 `EXT-X-MOUFLON`；MyFreeCams 的现行维护实现从 share 页面 `campreview` 属性构造预览 HLS。
- 取舍：分别迁移到上述已验证接口，并删除 MyFreeCams 旧 WebSocket/PHP 回退，减少请求次数和长期维护面。数字 model ID 无法由当前 share 页面解析，因此明确返回无流，不保留一套仅服务该旧入口的协议栈。
- Stripchat 限制：Mouflon 会混淆媒体 URI，且公开维护实现需要外部人工提供解密键。当前插件识别后明确报错，不伪装成可播放流，也不在仓库中加入密钥提取或缓存机制。
- 兼容边界：Zbiornik 当前页面已转为 WebRTC，Streamlink 不支持；ShowUp 受 Cloudflare 拦截且原实现仅支持已移除的 RTMP。两者继续保留显式“不支持”行为，不添加浏览器绕过或转码服务。

### 16:20 - 站点插件兼容性排查策略

- 问题：仓库内插件多年未统一验证，既可能受目标站 API 变化影响，也存在 Streamlink 8.x API 兼容问题；逐站反复探测容易触发限流。
- 约束：先用静态导入、离线样本和上游实现定位确定性故障；只有无法离线确认时才对每个目标站发少量请求。
- 已确认：`generic.py` 仍使用旧版 `num(min=..., max=...)`，在仓库声明的 Streamlink 8.4.0 环境中导入失败。现行接口使用 `ge`/`le`，直接替换可保持原有 0–25 边界且不增加兼容层。
- 决策：修复确定性兼容问题后再执行单次、串行的站点探测；不新增通用探测框架或重试层，避免把一次维护任务扩展成长期基础设施。
