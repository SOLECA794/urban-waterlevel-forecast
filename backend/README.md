# backend —— 后端服务（FastAPI 模块化单体）

严格依据《docs/后端规划书 V2.1》实现。分层：接入层（api）→ 应用层（application）→
领域层（domain：实体 + 四 Port）→ 基础设施层（infrastructure：各 Port 的 Adapter）。
**铁律：应用层与领域层不 import 任何具体 Adapter，只依赖 Port**（`app/core/deps.py`
是唯一的 Port→Adapter 绑定点）。

## 目录速览

```
backend/
├─ app/
│  ├─ main.py                  # FastAPI 入口 + lifespan + 单端口静态托管
│  ├─ core/                    # config / logging / errors / response / deps
│  ├─ domain/
│  │  ├─ models/               # 12 张表 ORM（含 forecast_point 三值、forecast_decision）
│  │  └─ ports/                # DataSource / ForecastModel / Tool / Agent / Orchestrator
│  ├─ application/             # forecast / revision / alert / station / calibration / agent
│  ├─ infrastructure/
│  │  ├─ datasource/           # SimulatedSource ✅ / RealSourceAdapter 🔶
│  │  ├─ forecast/             # Naive ✅ / LinearResponse ✅ / Lgbm 🔶 + registry
│  │  ├─ persistence/          # sqlite_repo / parquet_store / duckdb_analytics
│  │  ├─ agent/                # ToolRegistry ✅ / tools ✅ / EchoAgent 🔶
│  │  └─ scheduler/            # APScheduler 滚动预测 + 实况回填
│  ├─ api/v1/                  # stations / forecasts / alerts / models / calibrations / agent
│  └─ schemas/                 # Pydantic 契约
├─ config/                     # default.yaml + stations.yaml（配置驱动一切）
├─ scripts/generate_demo_data.py
├─ tests/                      # pytest + TestClient 冒烟
└─ requirements.txt
```

## 本地启动

```bash
cd backend
pip install -r requirements.txt
python scripts/generate_demo_data.py --reset     # 生成模拟数据（SQLite + Parquet）
uvicorn app.main:app --host 0.0.0.0 --port 8000  # http://localhost:8000/api/v1/health
```

接口文档：`http://localhost:8000/docs`（OpenAPI 自动生成）。

## 关键约定

- 统一 `/api/v1` 前缀；响应 `{code, message, data}`；错误码见 `app/core/errors.py`（05 §6.1）。
- 留白统一标注 `# EXT-POINT(类型): 说明`，`grep -rn "EXT-POINT" backend/` 可穷举。
- Agent 能力分级 L0/L1/L2（L2 需人工确认令牌），**L3 自动执行永不做**。
- 存储：业务 SQLite（`data/app.db`）+ 原始序列 Parquet（`data/parquet/`）+ 分析 DuckDB 直读。

## 测试

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```
