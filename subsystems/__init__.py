"""
多模态数据准备 子系统（对齐旧版「大块能力」划分，减少顶层目录数量）。

| 包 | 职责 |
|----|------|
| `structured_understanding` | 结构化理解（LLM / stub） |
| `pipeline_orchestration` | 编排三阶段 + DAG 校验与图论 |
| `pipeline_runtime` | 实例化桩、试运行采样、全量执行（原 execution + instantiation + trial） |
| `pipeline_session` | manifest 与上传文件预览 |
| `operator_management` | 算子注册表合并与写入 |
| `observability` | Token 用量等可观测 |
| `workflow` | 分步推进状态机 + 质检/经验快照（原 workflow_runner + workflow_closure） |
"""
