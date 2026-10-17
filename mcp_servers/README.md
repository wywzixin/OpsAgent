# OpsAgent MCP 示例服务

两个本地 FastMCP 服务提供 Agent 工具接入示例，使用 `streamable-http` 协议。

> 当前均返回模拟数据，适合本地演示与工具契约联调。接入真实环境时，需要替换服务内查询实现，或在 `.env` 中配置自己的 MCP 端点。

## 服务与工具

| 服务 | 工具 | 用途 |
| --- | --- | --- |
| CLS · 8003 | `get_current_timestamp` | 当前毫秒时间戳 |
| CLS · 8003 | `get_region_code_by_name` | 地域名称转代码 |
| CLS · 8003 | `get_topic_info_by_name` | 按名称查询日志主题 |
| CLS · 8003 | `search_topic_by_service_name` | 按服务名查日志主题 |
| CLS · 8003 | `search_log` | 按主题、时间范围与条件查询日志 |
| Monitor · 8004 | `query_cpu_metrics` | 服务 CPU 指标序列 |
| Monitor · 8004 | `query_memory_metrics` | 服务内存指标序列 |

实际可用工具以服务发现结果和源码中的 `@mcp.tool()` 为准。

## 启动

在项目根目录的两个终端分别执行：

```bash
uv run --frozen python mcp_servers/cls_server.py
```

```bash
uv run --frozen python mcp_servers/monitor_server.py
```

默认配置：

```dotenv
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp
```

## 参数约定

- `search_log` 的 `start_time` / `end_time` 使用**毫秒整数时间戳**。
- 指标工具的 `start_time` / `end_time` 使用 `YYYY-MM-DD HH:MM:SS` 字符串。
- 指标聚合间隔支持 `1m`、`5m`、`1h` 等形式。
- 时间工具和查询工具的时区应在真实接入时统一。

典型查询顺序为：确认服务与日志主题 → 确定时间范围 → 查询指标与日志 → 汇总证据。

## 接入真实系统

可以在现有工具中调用云日志 SDK、Prometheus 或自建监控 API，保留参数与返回结构；也可以新增 MCP 服务，并修改 `app/config.py` 的 `mcp_servers` 配置。

Key 只放在环境变量或本地 `.env`。工具应返回明确的失败信息、来源标识和查询时间范围，便于 Agent 判断证据是否有效。

客户端发现、调用重试与异常处理位于 [app/agent/mcp_client.py](../app/agent/mcp_client.py)，整体流程见 [架构导读](../docs/ARCHITECTURE.md)。
