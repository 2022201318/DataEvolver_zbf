# DataEvolver 前端

本目录为 DataEvolver 开源项目的 **Web 前端应用**，面向学术界与工业界用户，提供可视化、可交互的数据准备全流程界面。

## 快速开始

```bash
# 安装依赖
npm install

# 开发
npm run dev
# 打开 http://localhost:5173

# 构建
npm run build

# 预览构建结果
npm run preview
```

## 文档

- **[前端开发规格说明](docs/FRONTEND_DEVELOPMENT_SPEC.md)**：完整的需求、功能清单、模块设计、实时同步接口预留、交互与动效、技术栈说明。

## 功能概览

- **Stage 1**：数据上传（Raw/Seed/Description）、数据预览、数据理解（数据画像、经验）
- **Stage 2**：算子库、DAG 可视化、Pipeline 计划、Check 与算子级自进化预留
- **Stage 3**：实例化代码按 Step 展示（折叠/展开、语法高亮、中间结果摘要）
- **Stage 4**：小规模采样、生成结果 vs Seed 对比、Judge 结果、经验与流水线级自进化
- **执行**：全量执行进度、结果摘要、预览与下载
- **全局**：自动/手动切换、配置入口预留；所有展示位预留与后端实时同步接口

## 技术栈

- React 18 + TypeScript + Vite 4
- Tailwind CSS、Zustand、React Router
- @xyflow/react（DAG）、Prism.js（代码高亮）、lucide-react（图标）

## 设计说明

- 整体风格参考 `example/dataevolver.html`：深色背景、青/橙主色、网格与光晕、**DAG 流光边 + 粒子流动**、双轨自进化 Hero 区。
- 后端接口统一使用 **FastAPI** 模块化实现（见规格文档 8.4 节）。

## 状态

- 当前为 **Mock 数据** 的完整交互实现；后端对接与实时同步（SSE/WebSocket/轮询）可按规格文档第四节接入，后端以 FastAPI 提供接口。
