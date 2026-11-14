# 健康检查与本地探测日志

## 存活检查

- `GET /health` 或 `GET /api/health` 返回 HTTP 200 和 `{"status":"ok","app":"Allenop"}`。
- 同时支持 `HEAD`，响应无正文。接口无需登录，不读写数据库，不返回连接信息或凭据。
- 这是 **liveness（HTTP 服务存活）** 检查，不代表数据库、登录或所有业务模块已就绪；不应用来替代业务 readiness 检查。
- `/api/health` 适用于只代理 `/api` 的前端 / 反向代理。现有 `GET /` 返回值保持不变。

本机默认后端可验证：

```sh
curl -i http://127.0.0.1:8000/health
curl -I http://127.0.0.1:8000/api/health
```

非自动重载的后端需要重启进程后才会加载新路由；前端页面刷新不能更新后端。

## 不应伪装成成功的外部请求

### OpenCode 的 vLLM 自动发现与 8000 端口冲突

连续出现同一连接上的 `GET /health → 200`、`GET /v1/models → 404`，与 OpenCode V2 内置 vLLM 发现流程一致：默认访问 `http://127.0.0.1:8000/v1`，先检查 `/health`，再读取 `/v1/models`。本机此前也观察到 OpenCode 进程连接业务后端的 8000 端口。补充健康接口并不能停止探测，反而会让探测继续进入读取模型列表这一步。

如果没有使用 vLLM，在 **OpenCode 配置** 中关闭该发现插件，而不是在业务后端实现假的模型接口。保留配置中其他字段和已有插件规则，仅向 `plugins` 追加：

```json
"-opencode.provider.vllm"
```

本机 2026-11-14 已在 `~/.config/opencode/opencode.json` 应用此设置，原配置备份为同目录下的 `opencode.json.before-disable-vllm-20261114`（含原配置内容，应按敏感文件保护）。只增加了这一条插件规则，没有修改当前模型或 provider 配置。配置自动重载，无需重启 OpenCode 或业务后端；以后需要使用 vLLM 时移除这条禁用规则。

验证记录：

- `opencode plugin list --builtin` 确认本机插件 ID 为 `opencode.provider.vllm`。
- `opencode api get /api/plugin` 的运行时列表已不包含该插件，OpenAI、dynamic 和 OpenCode provider 插件仍处于 active 状态。
- 修改后 65 秒内进行 546 次本地连接采样，未观察到连接 8000 的已建立连接。采样可能漏掉极短连接，不能替代后端访问日志；本轮没有直接读取用户终端日志，因此仍应确认实际刷屏是否停止。
- 主动检查 `/health`、`/api/health` 均为 200，未登录访问 `/api/parts/` 仍为 401；主动访问 `/v1/models` 仍正确返回 404（该验证会产生一次对应日志）。

参考：[OpenCode V2 providers / Runtimes](https://opencode.ai/v2/docs/providers#runtimes)、[插件开关与自动重载](https://opencode.ai/v2/docs/plugins)。

### 打印与 WebSocket 探测

- `GET /CLodopfuncs.js` 是 C-Lodop 打印控件常见脚本路径。本项目未集成该控件；请求本应用时返回 404 是正常路由行为，不应该返回空脚本冒充打印服务。若打印确实不可用，需要在发起请求的页面中定位该 URL，并确认打印服务的实际地址 / 端口。
- Uvicorn 的 `connection rejected (403 Forbidden)` 常见于未匹配 / 未接受的 WebSocket 握手，不等于业务 HTTP 接口权限失败。本项目没有 WebSocket 路由，不能通过放宽 CORS、移除鉴权或添加无用的 WebSocket 接口处理。
- 要追查以上请求，保留相邻日志中的完整请求路径，并查看浏览器 Network 的 Request URL / Initiator / Origin，或用 `lsof -nP -iTCP:8000 -sTCP:ESTABLISHED` 检查正在连接的本地进程。仅凭 `127.0.0.1` 不能确定是哪个页面、插件或工具发起的请求。
- 不全局过滤 403 / 404 访问日志，以免隐藏真实接口拼写错误与权限问题。
