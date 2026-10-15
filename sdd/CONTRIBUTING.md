# 贡献规范

## 分支
- main：稳定，可直接部署
- feature/xxx：新功能
- fix/xxx：缺陷修复

## commit message
格式：`type: 简述`
type 取：feat / fix / refactor / docs / test / chore

## 推送前自检
1. backend：`cd backend && python -m pytest tests/ -x`
2. frontend：`cd frontend && npm run build`
3. 全局搜一遍：`grep -r "114.55\|i-bp14x7\|ghp_" backend/ frontend/src/` 必须零命中