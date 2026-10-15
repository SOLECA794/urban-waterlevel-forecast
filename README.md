# Urban Waterlevel Forecast

面向城市内涝的水位预测预警系统，以 Agent 主动值班为核心。

## 功能
- 多源数据融合：历史水位、实时监测、气象预报（Open-Meteo）统一特征工程
- 非线性汇流预测模型：tanh 饱和产流 + 指数退水 + 参数自学习，支持 1/3/6/12h 预见期
- 三因子预警研判：预测水位 + 持续时间 + 变化趋势，阈值按站点可配
- 多源协同修正：实时监测新息 + 最新气象预报新息 + 已发生事件修正
- Agent 主动巡检：每轮滚动预测后自动生成汛情摘要
- 可视化：一张图、趋势曲线、深色数据大屏、全局预警弹窗

## 技术栈
- 后端：Python 3.11 + FastAPI + numpy + pandas
- 前端：Vue 3 + TypeScript + Element Plus + ECharts
- 部署：Linux + systemd/setsid 进程守护

## 启动
后端：
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
WL_PORT=8095 python -m app.main
```
前端：
```bash
cd frontend
npm install
npm run dev
```