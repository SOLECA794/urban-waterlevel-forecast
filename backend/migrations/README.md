# migrations/ —— 数据库迁移（说明）

**本期口径（已在交付报告记录偏离理由）**：

文档规划使用 Alembic 管理迁移。为保证「一条命令启动」的部署体验与
Python 3.11–3.13 兼容性，本期改为：

1. 建表：SQLAlchemy metadata（`app/infrastructure/persistence/database.py`
   的 `init_db`，幂等 `create_all`）；
2. 种子：`scripts/generate_demo_data.py`（数据源/监测点/模型版本/事件库）；
3. 重置：`generate_demo_data.py --reset`。

**将来填充（EXT-POINT(INTEGRATION)）**：引入 Alembic 时，
`alembic init migrations` 后将 env.py 指向 `app.domain.models.Base.metadata`，
首个迁移即为当前全表结构；此后加 Agent 相关表走增量迁移，不影响既有数据。

全表清单（12 张）：source / station / model / forecast / forecast_point /
forecast_decision / alert / flood_event / task / agent_session /
agent_message / agent_tool_call。
