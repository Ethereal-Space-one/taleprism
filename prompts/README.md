# Taleprism 提示词工作流 / Prompt workflow

保留原文，用有依据的角色表演与连续场景增强阅读。模板版本：0.1.0。

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

## 使用方式与能力边界 / Capabilities

| 环境 | 可做什么 | 验证范围 |
| --- | --- | --- |
| 文本聊天工具 | 依据整理、角色表演、镜头与道具工作表 | 模板可复制；不同模型的输出质量未逐一比较 |
| 接受参考图并支持编辑的图片工具 | 母版、身份参考、同机位局部编辑与修复 | 《末班灯》用 Codex 会话内生图验证；仍出现过长凳变长、车篮遗漏 |
| 仅接受文字的图片工具 | 独立场景探索 | 不能据此承诺连续镜头一致性 |
| Taleprism 制作台 | 审校、图片回填、连续性检查与导出 | 本机流程可用；网页不调用会话内生图能力 |

工具包本身无需模型密钥。实际调用自己选择的 AI 服务可能需要账户并产生费用。模板没有后台自动请求、遥测或自带服务额度。

**No installation required for this prompt route.** Copy a template, replace its variables, and attach real image files to your chosen tool. The bilingual shared rules and English instructions work with the supplied Chinese fictional source; ask for output in your preferred language. Model performance and cross-view consistency are not guaranteed. Review the images, not just the prompt text.

## 可选声音 / Optional voice

先选对理解人物最有帮助的少量对白，分别记录说话人、面对谁、此刻所知、说话目的、语速与克制程度；逐句试听后接受。不要要求全篇使用同一种强烈情绪。公开示例无系统演示音频；macOS 用户可本地合成，也可使用制作台已有的声音能力。云端 OpenAI 配音尚未完成真实调用验证。

## 开发与版本 / Maintenance

[共用规则](RULES.md)与八模板由 `backend/src/storygal/prompt_library.json` 生成，制作台读取同一文件。维护者修改该文件后运行：

```sh
uv run --project backend python tools/export_prompt_kit.py
uv run --project backend python tools/export_prompt_kit.py --check
```

导出的任务携带模板版本与内容哈希。修改模板不会自动批准已有图片。结构化导入见 [schemas](../schemas/README.md)。代码、模板与原创示例的许可和来源见根目录说明。
