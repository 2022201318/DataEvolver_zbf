"""
Pipeline Orchestration Prompt Definitions
Standardize all LLM call prompts

编排三阶段 prompt 主干对齐旧版 多模态数据准备 `subsystems/pipeline_orchestration/prompts.py`；
并补充开源 CLI 全链路说明，供编排评估 / 任务判断等模块复用。
"""

# 供 `dag_semantic_llm` 等引用：与下方 DATACRAFT 附录一致，避免重复维护长文
CLI_WORKFLOW_FOR_LLM = """
---
## Open-source CLI end-to-end context (legacy-tuned workflow reference)

Typical command order: **understand** → **orchestrate** (this multi-stage LLM + automatic DAG assessment) → **evolve-operators** *only when* assessment recommends **new registry operators** → **instantiate** (Python stubs, JSONL stdin/stdout per step) → **trial** (sample run) → **run-pipeline** → **quality-check** (artifact snapshot) → **experience** (closure).

When the DAG passes assessment and **does not** recommend new operators, the workflow **skips** operator evolution and proceeds to **instantiate** — design pipelines assuming that path is common.

**Instantiation contract (from legacy operator generation)**: intermediate steps consume/produce **JSONL records** on stdin/stdout; **read_data** / **write_data** bound to manifest paths. Logical **input_keys** / **output_keys** must match how the record dict flows step-to-step (usually a **`records`** stream through the chain).
"""

# 多模态数据准备 System Workflow Context
DATACRAFT_WORKFLOW_CONTEXT = """
## 多模态数据准备 System Workflow Overview

多模态数据准备 is an intelligent data preparation system that transforms raw data into high-quality training data (seed data) through four stages:

**Stage 1: Structured Understanding** - Completed
- Analyze differences between raw data and seed data
- Identify schema changes and quality improvement directions
- Output: Structured understanding results (used as current input)

**Stage 2: Free Fitting** - Current Stage
- **Focus**: Design high-level optimization blueprint based on structured understanding results
- Does not involve specific operators, only focuses on "what to do" (what), not "how to do" (how)
- Output: Global optimization direction, key improvements, transformation strategies, quality focus areas

**Stage 3: Template Combination** - Next Stage
- **Focus**: Use functional templates to fit the optimization blueprint from the free fitting stage
- Select functional templates that best match the task (e.g., content enhancement, field extraction, etc.)
- Generate pipeline sketch with abstract steps, describing functional flow
- Output: Template selection + pipeline sketch with abstract steps

**Stage 4: Constrained Search** - Final Stage
- **Focus**: Map abstract steps to specific operators, optimize and fix the pipeline
- Check operator capabilities, dynamically add missing operators (saved to operator_registry_user.json)
- Merge similar steps, eliminate redundancy, optimize data flow
- Output: Complete, executable logical operator pipeline

**Final Goal**: Generate a complete logical operator orchestration flow that can transform raw data into seed data quality training data.
""" + CLI_WORKFLOW_FOR_LLM

# Stage 1: Free Fitting
FREE_FITTING_SYSTEM_PROMPT = DATACRAFT_WORKFLOW_CONTEXT + """

You are an expert in designing high-level data processing blueprints for 多模态数据准备 system.

**Current Stage: Free Fitting (Stage 2)**

Your task is to analyze the structured understanding results and design a comprehensive optimization blueprint that guides the entire data transformation process.

**Key Focus**: Design high-level "what to do" strategies, NOT "how to do" with specific operators. This blueprint will guide template selection in the next stage.

Design principles:
1. Focus on dataset-level optimization direction, not specific operators
2. Identify key improvements and transformation strategies
3. Define quality focus areas and standards
4. Consider the overall data flow and transformation goals
5. Keep the blueprint high-level and generalizable
6. If the user message includes **Prior DAG assessment feedback** with concrete failures (cycles, broken keys, task mismatch), you MUST fold mitigations into the blueprint and quality_focus — do not ignore it.

Output format: Valid JSON only."""

FREE_FITTING_USER_PROMPT_TEMPLATE = """Based on the structured understanding results, design a high-level optimization blueprint.

## Structured Understanding Results

**Schema Analysis**:
{schema_analysis}

**Dataset Level Delta**:
{dataset_level_delta}

**Basic Information**:
{basic_information}

## Prior DAG assessment feedback (from last orchestration evaluation — MUST address if non-empty)
{prior_orchestration_feedback}

Please design a comprehensive optimization blueprint in JSON format:

{{
    "global_optimization_direction": "High-level description of overall optimization direction for transforming raw data to seed data quality",
    "key_improvements": [
        "List of key improvements needed (as many as relevant)"
    ],
    "transformation_strategies": [
        "List of high-level transformation strategies (as many as relevant)"
    ],
    "quality_focus": [
        "List of key quality focus areas (as many as relevant)"
    ],
    "summary": "A concise summary of the optimization blueprint and the main tasks/strategies needed for the next steps"
}}

Please analyze carefully and provide a complete JSON response."""

# Stage 2: Template Combination
TEMPLATE_COMBINATION_SYSTEM_PROMPT = DATACRAFT_WORKFLOW_CONTEXT + """

You are an expert in selecting and combining pipeline templates for 多模态数据准备 system.

**Current Stage: Template Combination (Stage 3)**

Your task is to select and combine functional templates that best fit the optimization blueprint from the free fitting stage.

**Key Focus**: Select templates that are MOST RELEVANT and TASK-SPECIFIC to the optimization blueprint. Use templates to create a functional pipeline sketch with abstract steps.

Selection principles:
1. **Precision over completeness**: Select templates that directly match the core transformation goals
2. **Task-specific over generic**: Prioritize templates that are specifically relevant to the task type (e.g., QA generation, reasoning, etc.)
3. **Efficient coverage**: Choose templates that efficiently cover the transformation needs
4. **Avoid redundancy**: Don't select multiple templates that serve similar purposes
5. **Focus on core needs**: Prefer task-specific templates over generic ones
6. If **Prior DAG assessment feedback** lists structural or task-fit issues, favor templates and sketches that avoid those failures (e.g. no cyclic flow, coherent key handoff).

Remember: A focused pipeline with well-chosen templates is better than a comprehensive pipeline with many generic templates.

Output format: Valid JSON only."""

TEMPLATE_COMBINATION_USER_PROMPT_TEMPLATE = """Based on the optimization blueprint from the free fitting stage, select and combine templates that best fit the transformation needs.

**Focus**: Select templates that are SPECIFICALLY relevant to this task. Prioritize task-specific templates over generic ones.

## Optimization Blueprint (from Free Fitting stage)
{optimization_blueprint}

## Prior DAG assessment feedback (from last orchestration evaluation — MUST address if non-empty)
{prior_orchestration_feedback}

## Available Templates
{available_templates}

## Template Selection Rules
{template_selection_rules}

**Guidelines**:
- Select templates that directly address the transformation goals
- For each selected template, you can choose to use ALL steps or only KEY steps (specify which steps to use via selected_template_steps)
- Prioritize templates that match the task type and optimization direction
- Consider the efficiency: fewer well-chosen templates are better than many generic ones

Please select and combine templates to create a pipeline sketch in JSON format:

{{
    "selected_templates": [
        "List of template names to use"
    ],
    "selection_rationale": "Explanation of why these templates were selected",
    "template_combination_strategy": "How templates will be combined (sequential/parallel/hybrid)",
    "pipeline_sketch": {{
        "steps": [
            {{
                "step_id": "step_1",
                "template_name": "template_name",
                "functional_description": "What this step does functionally",
                "expected_output": "What this step produces",
                "use_all_template_steps": false,
                "selected_template_steps": ["step_1", "step_2"],
                "description": "Step description"
            }}
        ],
        "total_steps": 0,
        "data_flow": "Description of data flow between steps",
        "note": "This is a high-level sketch. Specific operators will be assigned in the constrained search stage."
    }},
    "coverage_analysis": {{
        "optimization_direction_coverage": "How well templates cover the optimization direction",
        "key_improvements_coverage": "How well templates cover key improvements",
        "quality_focus_coverage": "How well templates cover quality focus areas",
        "missing_capabilities": ["List any missing capabilities not covered by templates"]
    }}
}}

Please analyze carefully and provide a complete JSON response."""

# Stage 3: Constrained Search
CONSTRAINED_SEARCH_SYSTEM_PROMPT = DATACRAFT_WORKFLOW_CONTEXT + """

You are an expert in refining and optimizing data processing pipelines for 多模态数据准备 system.

**Current Stage: Constrained Search (Stage 4) - Final Stage**

Your task is to refine the pipeline sketch into a complete, executable logical operator pipeline.

**Key Focus**: 
1. Map abstract steps (from template combination) to specific operators from the operator registry
2. **Optimize and fix**: Merge similar steps, eliminate redundancy, ensure data flow coherence
3. **Check existing fields**: Before extracting fields, check if they already exist in raw data - if they exist and are valid, use them directly
4. **Check and add**: If operators are missing, dynamically add them (they will be saved to operator_registry_user.json)
5. **Finalize**: Produce a complete logical operator pipeline that can transform raw data to seed data quality

**CRITICAL Refinement Principles**:
0. **MANDATORY Pipeline Structure**:
   - **FIRST step MUST be `read_data`**: The pipeline MUST start with `read_data` operator to load raw data from file
   - **LAST step MUST be `write_data`**: The pipeline MUST end with `write_data` operator to save processed data to file
   - These are non-negotiable requirements for all pipelines
1. **Check existing fields FIRST**: 
   - Before using extraction operators, check structured understanding -> schema_analysis -> raw_fields
   - If a field already exists in raw data and matches the target format, DO NOT extract it - use it directly
   - Only extract fields if they don't exist or need transformation
   - **CRITICAL**: If a field does NOT exist in raw data (check raw_fields), you MUST use `call_llm_for_generation` to GENERATE it first, NOT `call_llm_for_enhancement` (which is for enhancing existing fields)
   - **Generation vs Enhancement**: Use `call_llm_for_generation` when field doesn't exist, use `call_llm_for_enhancement` only when field already exists and needs improvement
2. **Field dependency order**: 
   - **CRITICAL**: Generate all fields that are needed for validation/consistency checks BEFORE the validation step
   - For example, if you need to check consistency between field A and field B, BOTH fields must be generated BEFORE the consistency check step
   - If a field is extracted from another field (e.g., final_answer_latex from solution's <answer> tag), the extraction step must come BEFORE any consistency check that uses that field
3. **Field modification vs extraction**:
   - When adding tags/formatting to an existing field (e.g., adding <think> tags to solution), use operators that MODIFY the field in place, not extract to a new field
   - The operator should update the original field with the new formatting, not create a separate structured field
4. **Efficiency**: Merge similar steps, eliminate redundancy where possible
5. **Avoid duplicate operators**: Don't use the same operator type multiple times for the same purpose
6. Use operators from the registry when available
7. Ensure data flow coherence (outputs of one step feed inputs of next)
8. **One operator per core function**: Don't unnecessarily split a single function across multiple steps
9. Add validation/check steps only if essential for the task
10. Focus on the core transformation needs
11. The structured understanding JSON may contain `orchestration_assessment_feedback` from a **failed** prior assessment. If present and `last_assessment_passed` is false, read `latest` and **fix** those issues in the final_pipeline (no self-loops, full key continuity, satisfy task reasoning).
12. **Parameters (legacy instantiation alignment)**: Fill `parameters` with keys the registry expects (e.g. `field_names`, `schema_rules`, `format_rules`). Paths for `read_data`/`write_data` are often resolved at instantiation from manifest — still declare the logical structure so stubs can substitute placeholders.

**Reference Pipeline Patterns** (for inspiration, NOT to copy exactly):
- **Text SFT Synthesis**: Generate → Refine → Filter (3-5 steps, focus on quality)
- **Reasoning Tasks**: Filter → Generate/Enhance → Validate → Filter (5-8 steps, focus on reasoning quality)
- **Math Reasoning**: Filter → Generate/Enhance → Format → Validate → Filter (6-11 steps, focus on accuracy)
- **Text2SQL**: Filter → Generate variants → Validate → Generate questions → Format (7-9 steps, focus on SQL correctness)

**Key Insight**: Most pipelines follow a pattern of: Input preparation → Content generation/enhancement → Quality validation → Output formatting. Avoid unnecessary extraction steps if fields already exist.

Output format: Valid JSON only."""

CONSTRAINED_SEARCH_USER_PROMPT_TEMPLATE = """Refine the pipeline sketch into a complete, executable pipeline by mapping abstract steps to specific operators.

## Pipeline Sketch (with abstract steps)
{pipeline_sketch}

## Abstract Steps (to be mapped to operators)
{abstract_steps}

## Optimization Blueprint
{optimization_blueprint}

## Available Operators (from operator registry)
{available_operators}

## Understanding Result (CRITICAL - Use this to determine what fields to generate)
{understanding_result}

**KEY INFORMATION FROM STRUCTURED UNDERSTANDING**:
- **Fields that ALREADY EXIST in raw data**: {raw_fields_summary}
- **Raw field details**: {raw_fields_details_summary}
- **New fields that MUST be generated**: {new_fields_summary}
- **New field details and requirements**: {new_fields_details_summary}
- **Format requirements (tags, markers, special formatting)**: {format_requirements_summary}
- **Processing targets**: {processing_targets_summary}
- **Quality standards**: {quality_standards_summary}

**CRITICAL CHECK**: Before using extraction operators, verify if the target fields already exist in raw data. If they exist and are valid, use them directly instead of extracting.

**CRITICAL FORMAT REQUIREMENTS**: 
- Check the "Format requirements" above for any special tags/formatting that need to be added to fields
- If format requirements mention tags like `<think>...</think>` or `<answer>...</answer>`, ensure the pipeline includes steps that explicitly add these tags to the ORIGINAL field (modify in place, don't extract to new field)
- When using `call_llm_for_extraction` to add tags to an existing field:
  - The operator should MODIFY the original field by adding tags around existing content
  - For example, if solution field contains reasoning and answer, add tags: `<think>reasoning content</think><answer>answer content</answer>`
  - The output should be the same field name (e.g., "solution"), not a new structured field
- When using `call_llm_for_enhancement`, the `enhancement_goal` parameter should focus on enhancing the content within tags (e.g., "Enhance the reasoning content within <think> tags for clarity and detail")
- Check seed_field_details -> optimization_opportunity for explicit format requirements (e.g., "Add structured tags like <think>...</think>")

**CRITICAL**: When designing the pipeline, ensure that:
0. **MANDATORY Structure**:
   - **step_1 MUST be `read_data`**: Always start with reading raw data from file
   - **Last step MUST be `write_data`**: Always end with writing processed data to file
   - These are required for all pipelines, regardless of other steps
1. **Check existing fields FIRST**: Before using extraction operators, check if fields already exist in raw data (from structured understanding -> schema_analysis -> raw_fields). If a field exists and is valid, use it directly - don't extract it unnecessarily.
   - **CRITICAL**: If a field does NOT exist in raw_fields, you MUST use `call_llm_for_generation` to CREATE it, NOT `call_llm_for_enhancement` (which only works on existing fields)
   - **Example**: If raw data has no "solution" field, use `call_llm_for_generation` with target_field="solution" to generate it. Only use `call_llm_for_enhancement` if "solution" already exists and needs improvement.
2. **Field dependency order - CRITICAL**: 
   - Generate ALL fields that are needed for validation/consistency checks BEFORE the validation step
   - For example, if consistency check needs to compare field A and field B, BOTH must be generated BEFORE the consistency check step
   - If a field is extracted from another field (e.g., final_answer_latex extracted from solution's <answer> tag), the extraction must happen BEFORE any consistency check
   - **Order matters**: read_data → Field generation (for missing fields) → Field enhancement (for existing fields) → Field extraction → Validation/consistency check → Final formatting → write_data
   - **Specific example**: If consistency check compares "solution" and "final_answer_latex", you MUST have a step that generates "final_answer_latex" (e.g., by extracting from solution's <answer> tag) BEFORE the consistency check step
   - **Check structured understanding**: Look at new_fields in schema_analysis to see which fields need to be generated, and ensure they are all generated before any validation/consistency check that uses them
3. **Field modification vs extraction**:
   - When adding tags/formatting to an existing field (e.g., adding <think> and <answer> tags to solution), the operator should MODIFY the field in place, not extract to a new field
   - The modified field should replace the original field value
4. The final output includes ALL new fields identified in structured understanding
5. Operators that generate content (especially LLM-based operators) should generate the ACTUAL field names (e.g., "question_rewrite", "qa_metadata"), not template names
6. Parameters should reflect the actual field requirements from structured understanding
7. **Avoid duplicate extraction**: Don't use the same extraction operator multiple times for similar purposes
8. **Merge similar steps**: If multiple abstract steps serve the same purpose, merge them into one operator call

## Capability Check Results
{capability_check_results}

**Important**: The pipeline sketch contains abstract steps (functional descriptions from templates). Your task is to:
1. Map abstract steps to specific operators from the operator registry
2. **Optimize**: Merge similar abstract steps into single operator calls when it makes sense
3. **Fix**: Eliminate redundancy, ensure data flow coherence
4. **Complete**: Ensure all transformation goals are addressed AND all required fields from structured understanding are generated

For each abstract step:
1. Analyze the functional_description and expected_output
2. Select the most appropriate operator(s) from the available_operators
3. **Consider merging**: If multiple abstract steps serve similar purposes, merge them into one operator call
4. Ensure data flow coherence (outputs of one step feed inputs of next)

**Goal**: Create an efficient, complete pipeline that achieves the transformation goals. Focus on quality and efficiency rather than a specific step count.

Please refine the pipeline in JSON format:

{{
    "final_pipeline": [
        {{
            "step_id": "step_1",
            "operator": "operator_name (from registry, must match available_operators)",
            "input_keys": ["input_key1"],
            "output_keys": ["output_key1"],
            "parameters": {{
                "param1": "value1"
            }},
            "description": "Clear description of what this step does",
            "mapped_from_abstract_step": "step_1 (the abstract step this operator implements)",
            "refinement_source": "operator_registry|template_mapping|dynamic_addition"
        }}
    ],
    "refinement_summary": {{
        "original_steps_count": 0,
        "final_steps_count": 0,
        "added_operators": ["List of newly added operators if any"],
        "modified_operators": ["List of modified operators"],
        "data_flow_verification": "Verification that data flow is coherent",
        "capability_coverage": "Verification that all required capabilities are covered"
    }}
}}

Please ensure:
1. **MANDATORY**: step_1 is `read_data` and the last step is `write_data`
2. All steps have valid operators from the registry or newly designed
3. Data flow is coherent (each step's inputs come from previous steps' outputs)
4. All required capabilities are handled
5. Parameters are optimized for the task
6. The pipeline is complete and executable
7. **Field generation vs enhancement**: Use `call_llm_for_generation` for fields that don't exist in raw data, use `call_llm_for_enhancement` only for existing fields that need improvement

Please analyze carefully and provide a complete JSON response."""
