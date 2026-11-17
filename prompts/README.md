# Taleprism 提示词工作流 / Prompt workflow

保留原文，用有依据的角色表演与连续场景增强阅读。模板版本：0.2.1。

**第一次使用：打开[《末班灯》教程](../examples/last-light/README.md) / [English walkthrough](../examples/last-light/README.en.md)。** 全部参考图在 `samples/last-light/`，无需先安装制作台。GitHub 网页查看文件即可；要在自己的图片工具中使用，请下载原始图片并实际上传，文件名本身不会传送图片。

| 顺序 | 模板 | 完成后得到什么 |
| --- | --- | --- |
| 1 | [原文与依据](01-source.md) | 事实、艺术解释、未知项与不能提前揭示的内容 |
| 2 | [人物与心理](02-character.md) | 每个人的目标、所知、公开姿态、顾虑、视线和动作 |
| 3 | [章节视觉编排](03-shot-plan.md) | 有限预算下各幅图片的叙事用途与插入位置 |
| 4 | [场景与道具](04-scene.md) | 稳定布局与逐镜头物件状态表 |
| 5 | [首图与参考](05-first-image.md) | 人物身份明确、可作为后续依据的场景母版 |
| 6 | [连续镜头编辑](06-continuation.md) | 以明确状态变化为范围的后续图 |
| 7 | [图像审查](07-review.md) | 实际观察到的问题、未知项和检查人记录 |
| 8 | [定点修复](08-repair.md) | 修复一个缺陷，并回查其他内容与后续镜头 |

每份模板都有输入说明、可复制正文、完整填写示例、预期输出与失败恢复方法。把 `{{变量}}` 换成自己的资料；填写示例是参考，不能当作自己生成结果的验收记录。01—04 输出供人阅读的工作表，不是制作台导入文件。

## 读者在此刻应该看到什么 / Reader intent

03 选镜填写四项：读者问题、预期读法、可见线索、此刻不揭示。预算是上限；如果图没有新增理解、方向或有意的情绪节拍，可以不画。不要给题材套固定构图、用色或冲突模式。

将可见动作／线索写进制作台现有的画面安排（`framing`），将不该提前出现的内容放进 `avoid`。完整四项可保留在人用工作表，从 03 传给 07 的 `expected.reader_intent`；不要把工作表原样导入制作台。05／06 能接受随手工简报附带的四项，但不会自动从 03 读取。07 区分单图、相邻镜头、正文位置／尺寸及真人首次阅读；缺哪份证据就只将对应范围标为未检查。程序不代替视觉判断。

## 使用方式与能力边界 / Capabilities

| 环境 | 可做什么 | 验证范围 |
| --- | --- | --- |
| 文本聊天工具 | 依据整理、角色表演、镜头与道具工作表 | 模板可复制；不同模型的输出质量未逐一比较 |
| 接受参考图并支持编辑的图片工具 | 母版、身份参考、同机位局部编辑与修复 | 《末班灯》用 Codex 会话内生图验证；仍出现过长凳变长、车篮遗漏 |
| 仅接受文字的图片工具 | 独立场景探索 | 不能据此承诺连续镜头一致性 |
| Taleprism 制作台 | 审校、图片回填、连续性检查与导出 | 本机流程可用；网页不调用会话内生图能力 |

工具包本身无需模型密钥。实际调用自己选择的 AI 服务可能需要账户并产生费用。模板没有后台自动请求、遥测或自带服务额度。

**No installation required for this prompt route.** Copy a template, replace its variables, and attach real image files to your chosen tool. The bilingual shared rules and English instructions work with the supplied Chinese fictional source; ask for output in your preferred language. Model performance and cross-view consistency are not guaranteed. Review the images, not just the prompt text.

## 相邻镜头与修图候选 / Paired-shot candidates

[成对工作表](paired-shot-continuity-worksheet.json) v2 是人工记录，不是制作台导入协议，也没有自动校验或自动批准功能；它与八模板的版本独立。它只补充共享参考与新候选来源，不改变已有历史记录。

1. 另存一份新工作表，保留旧图、旧提示词和旧检查。`shots` 的 `asset_id`、`sha256`、`actual_observation` 和 `image_inspected` 始终指向**本次实际检查的那张图**，不是计划中的修正。新图的 `result_status` 填 `new_candidate`；旧图可填 `historical`，未知保持 `not_recorded`。
2. 在 `shared_references` 登记本次使用的参考文件、哈希、职责与限制，用 `reference_id` 标识。共享旗色或其他物件色板的 `role` 可填 `palette_only`，船只等物件参考可填 `object_identity`，编辑原图可填 `edit_target`。在 `shared_world_state.reference_ids` 关联约束同一物件的参考；`basis` 区分原文依据与明确的艺术选择，不把色板 RGB 当作原文或历史事实。
3. 每幅候选在 `provenance` 记录原图编号／哈希、**实际提交**的提示词，以及按实际提交顺序排列的 `actual_reference_order`（引用同一参考表中的 ID）。只列实际上传的文件，不把拟用参考写成已经使用。保留工具返回的结果编号；未记录的模型、seed 或旧图哈希保持 `null`，不能倒填。根部 `new_edit_result_id`／`new_edit_result_sha256` 保留给旧版单一结果记录；多图以各 `shots` 的精确结果及来源为准。
4. 实际并排看图后，逐项填写 `pair_checks`。旗色通过不代表光照、动作或空间同时通过；未解决的其他问题保留独立 `warning`，总结果不能写成 `passed`。未看图保持 `not_checked`，修复失败保持 `needs_revision`。助手检查不等于创作者最终批准。

Use a new worksheet for each candidate set. Bind shared palettes and object references by ID and exact file hash, record the actual prompt and ordered attachments, then inspect those exact result images. Keep unrelated warnings separate from a successful scoped repair. This worksheet neither generates an image nor validates a claimed review; creator final art review remains independent.

## 可选环境动效 / Optional ambient motion

选中的当前瞬间确实需要环境动作时，再接[环境动效人工简报与示例](optional-ambient-motion.md)：03 绑定精确原文与批准瞬间，04 先构图、像素锚点与保护区，05／06 保留完整静态底图，07／08 按 `anticipation → contact → consequence → settle` 四拍对照与定点修复。附赤壁浪的推近→撞岸→水花→回流、《末班灯》檐外更明显雨势，以及不替换原定稿的贴水低机位实验。

这是八模板之外的可选旁表，不是新增必填输入或 plan／manifest／runtime 字段；不批量给每镜头加效果。未启用仍照旧使用 03—08。关闭或减少动效优先原图，文字简报不代表已渲染，静图检查不代表循环已通过。

## 可选声音 / Optional voice

先选对理解人物最有帮助的少量对白，分别记录说话人、面对谁、此刻所知、说话目的、语速与克制程度；逐句试听后接受。不要要求全篇使用同一种强烈情绪。公开示例无系统演示音频；macOS 用户可本地合成，也可使用制作台已有的声音能力。云端 OpenAI 配音尚未完成真实调用验证。

## 开发与版本 / Maintenance

[共用规则](RULES.md)与八模板由 `backend/src/storygal/prompt_library.json` 生成，制作台读取同一文件。维护者修改该文件后运行：

```sh
uv run --project backend python tools/export_prompt_kit.py
uv run --project backend python tools/export_prompt_kit.py --check
```

导出的任务携带模板版本与内容哈希。修改模板不会自动批准已有图片。结构化导入见 [schemas](../schemas/README.md)。代码、模板与原创示例的许可和来源见根目录说明。
