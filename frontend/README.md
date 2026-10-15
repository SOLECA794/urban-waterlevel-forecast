# frontend —— 前端（Vue 3 + TypeScript + Vite + Element Plus + ECharts + Pinia）

依据《docs/前端规划书 V2.1》实现：五页面（总览 / 监测点详情 / 预警中心 / 系统设置 /
Agent 控制台）、mock 双通道、轮询刷新、降级不白屏。

## 页面

| 路由 | 页面 | 关键能力 |
|---|---|---|
| `/` | 系统总览 | 监测点卡片（等级排序）、今日预警统计、数据源/模型状态、最近预测记录 |
| `/station/:id` | 监测点详情 | **1h/3h/6h/12h 全切换**、**原始 vs 修正双曲线**、四级阈值线、置信区间（随预见期展宽）、**Agent-A 决策面板**、模型切换（S7）、预警提前量 |
| `/alerts` | 预警中心 | 等级/状态/参考级筛选；**6h/12h 参考级浅色显示** |
| `/settings` | 系统设置 | 点位增删改、四级阈值配置（立即生效）、模型激活、**参数校准入口（前后误差对比）**、重训占位提示、健康三态 |
| `/agent` | Agent 控制台 | 会话 / 消息流 / 工具调用轨迹三栏；EchoAgent 演示「提问→选工具→执行→回答」 |

## 视觉规范（06 §6）

主色防汛蓝 `#1E6FA8`；预警四色 蓝 `#2196F3` / 黄 `#FFC107` / 橙 `#FF9800` / 红 `#F44336`；
状态色 正常绿 / 断流灰 / 错误红 与预警四色区分；阈值线带等级文字标注；
双曲线以「线宽 + 线型 + 图例」区分（色弱可读）。

## 命令

```bash
npm install
npm run dev        # 开发（默认 VITE_USE_MOCK=true，后端未启动也能完整演示）
npm run gen:api    # 由 ../backend/openapi.json 生成 src/api/schema.d.ts（契约单一事实来源）
npm run build      # 产出 dist/（生产模式走真实接口，单端口由后端托管）
```

## mock 双通道（FR-5.7）

- `VITE_USE_MOCK=true`：全部请求走 `src/mock/`（形状与后端契约一致），后端未启动可完整演示；
- `VITE_USE_MOCK=false`：走真实接口；**网络失败自动降级**到 mock 并显示顶部横幅（不白屏）；
- 业务错误码（code≠0）一律抛 `BizError`，页面提示具体原因——**禁止仅凭 HTTP 200 判定成功**。

## 目录

```
src/
├─ app/{router,layouts}/    # 路由 + 主布局（侧边栏 + 顶部状态条）
├─ pages/                   # 五页面
├─ components/              # StationCard / TrendChart / AlertBadge / AlertList /
│                           # ForecastSummary / ForecastDecisionPanel / DegradedBanner / ToolCallTrace
├─ stores/                  # Pinia：station / alert / system / agent
├─ api/                     # client.ts（统一解包）+ endpoints.ts + schema.d.ts（生成勿改）
├─ composables/             # usePolling（30s 轮询）/ useEcharts / useSSE（预留）
├─ mock/                    # fixtures + 路由（VITE_USE_MOCK 切换）
└─ types/                   # 与后端契约一致的 TS 类型
```
