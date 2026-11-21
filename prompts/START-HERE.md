# 用自己的小说开始 / Bring your own novel

## 中文手顺

1. 下载 Release 中的 **Prompt Starter**，完整解压。打开含 `prompts/` 的文件夹；放入你有权使用的一章原文副本（如 UTF-8 的 `chapter.txt`）。先从一章、1–3 张图开始。
2. **有本地目录的 Agent**：在 Codex 中打开该文件夹作为本地项目，或在该目录启动 Claude Code。**只能上传文件的聊天工具**：上传 [01-source.md](01-source.md)、[03-shot-plan.md](03-shot-plan.md) 和章节副本。确认工具能读取这三份文件；如果只有文本输入，复制两份模板的「可复制模板」和要处理的正文。不要交付没有权利分享的未公开稿件。
3. 发这句话：

   > 用 Taleprism 帮我做这一章。先读 `prompts/01-source.md`、`prompts/03-shot-plan.md` 和 `chapter.txt`（上传版读取同名附件）。编号只加在工作表，不改原文。先交一份 Markdown：1–3 个候选镜头、段落编号与逐字引文、这一刻读者该看懂什么、哪些信息不能提前揭示。原文事实和艺术解释分开；不明确的留空并标注。现在不要生图或写回正文。能写文件就另存 `shot-plan.md`，不能就直接回在对话里，等我确认。

4. **先看一页，再做第一张图。** 确认镜头后，按[八步模板](README.md)继续。让 Agent 把人物、场景、道具状态和连续性要求写进第一张图的提示词；有参考图时要实际附图，不是只写文件名。没有生图工具时，交接方式是把提示词和获许可的参考图带到你自己的图片工具。声音、影像或呈现方式的额外点子可以最后再挑，不是必填。
5. **要成书时才开制作台。** 从「用自己的图文开始」导入原 TXT，上传你接受的图，锚定到原段落，先试读再「导出独立阅读器」。分享 Reader ZIP；续作另存可编辑备份。以上 Markdown 不是导入格式。已有制作台工程、想让 Agent 做可导回的方案时，从「章节制作方案」点「导出 AI 任务」，交给 Agent 按任务内 schema 返回 JSON，保留项目、原文和版本字段，再点「导入 AI 方案」作为待审草稿。这是另一路径。

这是文件和提示词的交接，不是插件安装。第一次做镜头计划不需要 Taleprism 密钥；所选 Agent 或生图工具是否联网、收费以及怎样处理上传内容，由该工具决定。

## English walkthrough

1. Download and fully extract the **Prompt Starter** from the Release. In the folder containing `prompts/`, put an authorized copy of one chapter, such as UTF-8 `chapter.txt`.
2. Open that folder as a local project in Codex or start Claude Code there. In an upload-only tool, attach [01-source.md](01-source.md), [03-shot-plan.md](03-shot-plan.md), and your chapter. If attachments are unavailable, paste the copyable blocks and the relevant passage. Confirm what your tool can read and share only text you have permission to use.
3. Send:

   > Use Taleprism for this chapter. Read `prompts/01-source.md`, `prompts/03-shot-plan.md`, and `chapter.txt` (or the attached files with those names). Number the passages in the worksheet without rewriting the original. Propose one to three shots. Give each shot's paragraph number, exact quote, intended reading benefit, and details that must not be revealed yet. Separate interpretation from quoted facts and mark unknowns. Do not generate images or alter the original. Save the Markdown brief as `shot-plan.md` if you can write files; otherwise return it in chat. Stop for review.

4. Review the first brief, then use the [eight templates](README.md) to direct your first image. Attach any actual reference images to an image-capable tool. Extra sound, motion, or presentation ideas can wait until the end.
5. To share an edition, import the original TXT and approved images into the local workbench, place them at their paragraphs, preview, and export a Reader ZIP. Keep the editable backup separately. The Markdown brief is **not** an import file. For a structured round trip, start inside a workbench project with **导出 AI 任务** (Export AI Task), have the agent return JSON using the task schema without changing project/source/revision metadata, then use **导入 AI 方案** (Import AI Plan) to review the draft.

No plugin installation or Taleprism model key is required for the initial handoff. Your chosen agent or image tool may require its own account or fees and may process uploaded text remotely.
