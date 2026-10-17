# OpsAgent 架构与源码导读

本文从真实调用链解释项目如何实现对话、诊断、RAG 和 MCP 接入，路径均相对于仓库根目录。

## 1. 模块职责

| 层次 | 模块 | 职责 |
| --- | --- | --- |
| 入口 | `app/main.py` | 路由、静态资源、CORS、Milvus 生命周期 |
| 配置 | `app/config.py` | Pydantic Settings 读取环境变量与 `.env` |
| API | `app/api/` | 请求校验、服务调用、JSON / SSE 输出 |
| 对话 | `app/services/rag_agent_service.py` | 模型、工具、Checkpointer、文本流 |
| 运维 | `app/services/aiops_service.py` | 状态图、节点路由、任务模板、事件转换 |
| 决策 | `app/agent/aiops/` | Planner、Executor、Replanner、State |
| 工具 | `app/tools/` / `app/agent/mcp_client.py` | 本地工具、MCP 工具发现与重试 |
| 知识库 | `app/services/vector_*.py` | 向量化、入库、检索、VectorStore 封装 |
| 前端 | `static/` | fetch 流读取、会话展示、上传、Markdown 渲染 |

## 2. 对话调用链

```text
POST /api/chat 或 /api/chat_stream
  → RagAgentService.query() / query_stream()
  → 延迟初始化 MCP 工具
  → create_agent(model, local_tools + mcp_tools, checkpointer)
  → SystemMessage + HumanMessage
  → 以 session_id 作为 configurable.thread_id 执行
  → 返回最终文本 / 增量文本块
```

`create_agent` 提供模型与工具交替调用的运行机制。`MemorySaver` 保存进程内对话状态，不提供跨进程共享和重启恢复能力。

工具注册集中在 `app/tools/__init__.py` 的 `DEFAULT_LOCAL_AGENT_TOOLS`，包含知识检索、当前时间与 Prometheus 告警。对话服务在首次使用时加载 MCP 工具；发现失败时回退到本地工具并记录错误。

当前系统提示在每次请求中追加，消息裁剪函数尚未挂载。后续可以将系统提示固定到 Agent 配置，并使用 middleware 管理上下文预算。会话历史接口还需修正对 Checkpointer 字典返回值的读取。

## 3. 运维诊断状态与控制流

`app/agent/aiops/state.py` 定义四个核心状态字段：

| 字段 | 更新方式 | 用途 |
| --- | --- | --- |
| `input` | 覆盖 | 原始诊断任务 |
| `plan` | 覆盖 | 当前剩余步骤 |
| `past_steps` | `operator.add` 追加 | 已执行的 `(步骤, 结果)` |
| `response` | 覆盖 | 最终 Markdown 报告 |

图的入口为 Planner，随后进入 Executor 和 Replanner。Replanner 返回报告时结束；仍有计划时进入下一次 Executor。

### Planner：规划前检索经验

源码：`app/agent/aiops/planner.py`

1. 读取 `input`，调用 `retrieve_knowledge.ainvoke()` 获取运维经验。
2. 读取本地与 MCP 工具说明。
3. 使用 `planner_prompt | llm.with_structured_output(Plan)` 生成 `steps`。
4. 返回 `{"plan": steps}`。

经验检索失败会记录告警。规划失败时使用“收集信息、分析数据、生成报告”默认计划；后备计划不代表已经获得真实诊断证据。

### Executor：执行当前步骤

源码：`app/agent/aiops/executor.py`

1. 取出 `plan[0]`，通过 `bind_tools()` 为模型绑定工具。
2. 模型提出工具调用，`ToolNode` 执行该批调用。
3. 把工具返回传回模型，提取结果文本。
4. 移除当前步骤，追加 `(task, result)`。

当前实现只执行一轮工具调用，第二次模型响应中的新调用不会继续执行；提示中也未显式加入前序 `past_steps`。扩展时优先补充有限工具循环、前序证据和明确的成功 / 失败状态。

### Replanner：继续、改计划或报告

源码：`app/agent/aiops/replanner.py`

决策通过 `Act(action, new_steps)` 输出：`continue` 保留计划，`replan` 替换剩余步骤，`respond` 生成报告。代码限制新计划长度，并在执行步数达到限制时生成最终响应。

决策只使用每步结果前 300 个字符的摘要；报告生成读取完整执行结果。处理大日志时，适合引入独立证据存储，在状态中保留来源、摘要和引用 ID。

### 一次会话与一次诊断

`execute()` 初始化 `past_steps=[]`，但追加式 reducer 会将其与已有检查点相加，所以复用 `thread_id` 不会清除旧记录。当前独立诊断应使用新的 `session_id`；后续可将用户会话与单次执行分别建模为 `session_id` 和 `run_id`。

## 4. 知识库写入与读取

```text
文件上传
  → VectorIndexService.index_single_file()
  → 读取 UTF-8 文本 → 按 _source 删除旧向量
  → DocumentSplitterService.split_document()
  → VectorStoreManager.add_documents()
  → OpenAICompatibleEmbeddings.embed_documents()
  → Milvus biz collection
```

Markdown 先按一级、二级标题切分，再做递归字符切分和小片段合并。分片保存 `_source`、`_file_name`、`_extension` 与标题元数据。

Collection 包含 `id`、`vector`、`content`、`metadata`，使用 L2 距离和 IVF_FLAT 索引。当前向量维度固定为 1024，应与 Embedding 输出一致。已有集合维度不匹配时会删除重建，连接已有数据库前需要改为显式迁移。

检索主链路为 `retrieve_knowledge → VectorStoreManager → LangChain Milvus retriever`，按 `RAG_TOP_K` 返回文档。工具返回格式化文本及原始文档 artifact，文本中包含参考编号、文件名与标题。

`vector_search_service.py` 另有 PyMilvus 原生搜索封装，当前知识工具不经过该模块。

## 5. MCP 与 Prometheus

`app/agent/mcp_client.py` 延迟创建全局 `MultiServerMCPClient`，默认连接 CLS 与 Monitor 两个服务；可以通过配置修改 URL 与 transport。

调用拦截器在异常时最多尝试三次，间隔按指数退避增长；耗尽后返回 `CallToolResult(isError=True)`。对话与诊断链路的工具发现降级逻辑尚未统一，生产接入时应补充独立超时与部分可用策略。

`query_prometheus_alerts` 直接请求 `GET /api/v1/alerts`，执行完整 labels 去重、时间解析、持续时长计算和状态统计。它不执行 PromQL，也不代替 Alertmanager。

`mcp_servers/` 是模拟实现。替换为真实 API 时，需要统一服务名、实例身份与查询时间窗口，并保留清晰的工具参数契约。

## 6. SSE 事件与展示

| 链路 | LangGraph 流模式 | 对外事件 |
| --- | --- | --- |
| 对话 | `messages` | `content`、`done`、`error` |
| 诊断 | `updates` | `plan`、`step_complete`、`report`、`complete`、`error` |

对话增量发送模型文本；诊断在节点完成后发送进度，最终报告整体返回。API 包装为 `event: message`，真实类型位于 data JSON 的 `type` 字段。

## 7. 扩展入口

| 目标 | 建议入口 |
| --- | --- |
| 新增本地查询工具 | 使用 `@tool` 定义并加入 `DEFAULT_LOCAL_AGENT_TOOLS` |
| 接入新 MCP 服务 | 修改 `Settings.mcp_servers` 与环境配置 |
| 更换聊天模型 | 配置 Messages 兼容端点及匹配的模型 |
| 更换 Embedding | 修改配置，先规划维度和数据迁移 |
| 自定义诊断任务 | `AIOpsService.execute(user_input, session_id)` |
| 持久化与恢复 | 替换 MemorySaver，区分会话与运行 ID |
| 增加诊断评测 | 固定故障输入、工具回放、证据覆盖与结论检查 |

优先保证工具返回可信、步骤结果可判定、证据能跨步骤传递，再扩展并行执行与更复杂的规划策略。
