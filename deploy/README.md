# 部署手册 —— 城市内涝（积水）水位预测预警系统

**最终部署形态：单端口**。后端 FastAPI（Uvicorn）同时托管前端构建产物
（`frontend/dist`）与 `/api/v1` 接口，一个端口提供全部服务。
（文档 04 §7.2 原为 Nginx(80) + backend(8000) 双容器；按交付决策合并为单端口，
Docker（M5）本期跳过。）

## 1. 环境要求

| 项 | 要求 |
|---|---|
| 操作系统 | Linux（Ubuntu 20.04+ / CentOS 8+ 等主流发行版） |
| Python | **>= 3.11**（3.11 / 3.12 / 3.13 均验证兼容，全 wheel 依赖、零编译） |
| 内存 / 磁盘 | 2 核 4GB / 10GB（纯 CPU，无 GPU） |
| 浏览器 | Chrome / Edge 现代版本 |

依赖硬约束：**不包含** prophet / torch / celery / redis / 时序数据库 / 向量数据库。

## 2. 交付包结构

```
waterLevelForcasting/
├─ backend/            # FastAPI 服务（含 config/、scripts/）
├─ frontend/dist/      # 前端构建产物（开发机 npm run build 后一并上传）
└─ deploy/
   ├─ start.sh         # 一键启动（建 venv → 装依赖 → 数据初始化 → 起服务）
   ├─ stop.sh          # 停止服务
   ├─ requirements.txt # 运行时依赖清单
   └─ README.md        # 本手册
```

## 3. 启动（3 步）

```bash
# ① 上传交付包后，赋予脚本执行权限
chmod +x deploy/start.sh deploy/stop.sh

# ② 一键启动（默认 0.0.0.0:8000；可用环境变量覆盖）
WL_PORT=8000 ./deploy/start.sh

# ③ 浏览器验证
#    入口页： http://<服务器IP>:8000/
#    健康检查： http://<服务器IP>:8000/api/v1/health   （数据源/模型/数据库三态应为 STREAMING / loaded / ok）
#    接口文档： http://<服务器IP>:8000/docs
```

首次启动会自动：创建 `backend/.venv` → 安装依赖 → 无数据时执行
`backend/scripts/generate_demo_data.py` 生成模拟数据（SQLite + Parquet）→
启动后立即执行一轮滚动预测（总览页/预警中心即有演示数据）。

## 4. 常用操作

```bash
./deploy/stop.sh                       # 停止（PID 文件 + 端口兜底）
WL_PORT=9000 ./deploy/start.sh         # 指定端口启动
./deploy/start.sh > app.out 2>&1 &     # 后台运行（或用 systemd 托管，见 §7）
```

## 5. 配置外置（改场景不改代码）

| 文件 | 内容 |
|---|---|
| `backend/config/default.yaml` | 数据源类型、模型类型、**预见期 `[1,3,6,12]`（可撤回为 `[1,3]`）**、滚动周期、协同修正参数、预警默认阈值、存储路径 |
| `backend/config/stations.yaml` | 监测点清单与四级阈值 / 基流水位 / 退水系数 |
| 环境变量 | `WL_PORT` / `WL_HOST` / `WL_SQLITE_PATH` / `WL_PARQUET_DIR` / `WL_DATASOURCE_TYPE` / `WL_AUTO_FORECAST` |

修改配置后重启服务生效；设置页修改的点位阈值保存后下一次研判立即生效（无需重启）。

## 6. 数据与持久化

```
backend/data/
├─ app.db        # SQLite 业务库（监测点/预测明细/决策/预警/Agent 三表，WAL 模式）
├─ parquet/      # 原始时序（station_*.parquet）+ 未来 12h 降雨真值（*_future.parquet）
└─ logs/         # 按天滚动 JSON 日志（保留 14 天）
```

- 升级/回滚：数据目录不随进程销毁；备份即拷贝 `backend/data/`。
- 重置演示数据：`cd backend && python scripts/generate_demo_data.py --reset`。

## 7. systemd 托管（推荐生产使用）

```ini
# /etc/systemd/system/water-level.service
[Unit]
Description=Water Level Forecast System
After=network.target

[Service]
WorkingDirectory=/opt/waterLevelForcasting/backend
ExecStart=/opt/waterLevelForcasting/backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

```bash
# 首次仍建议先手动跑一次 deploy/start.sh 完成依赖安装与数据初始化
systemctl daemon-reload && systemctl enable --now water-level
```

## 8. 验证清单（部署后 2 分钟）

| 检查 | 方法 | 预期 |
|---|---|---|
| 入口页 | 浏览器打开 `http://IP:8000/` | 总览页 6 张监测点卡片 + 顶部状态条 |
| 健康三态 | `curl http://IP:8000/api/v1/health` | `code:0`，datasource=STREAMING、model.loaded=true、database=ok |
| 预测链路 | 详情页选 12h 点「发起预测」 | 出现双预测曲线 + 置信区间，12h 区间明显更宽 |
| 预警链路 | 预警中心 | 有记录；6h/12h 预警带「参考」标记浅色显示 |
| 决策追溯 | 详情页 Agent-A 面板 | 模型选择/融合权重/修正强度/理由 |
| 离线演示 | 停掉后端刷新页面 | 顶部降级横幅 + mock 数据，页面不白屏（前端产物内置 mock 通道） |

## 9. 常见问题

| 现象 | 处理 |
|---|---|
| 启动报「Python 版本过低」 | 安装 Python 3.11+ 并以 `PYTHON_BIN=/usr/bin/python3.11 ./deploy/start.sh` 指定 |
| 页面空白且无 API | `frontend/dist` 未上传——上传后重启；或临时以 API 模式运行并用 5173 端口前端开发服务 |
| 8000 端口被占用 | `WL_PORT=9000 ./deploy/start.sh` |
| 预测报 DATA_NOT_ENOUGH | 该点位无模拟数据：`python scripts/generate_demo_data.py`（或 --reset） |
| 接入真实数据源 | 实现 `RealSourceAdapter`（EXT-POINT(DATASOURCE) 有对接说明），配置 `datasource.type: real` |
