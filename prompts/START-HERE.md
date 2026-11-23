# 用自己的小说开始 / Bring your own novel

## 中文手顺

**第一件作品可以只有一章、一幅静图，没有声音。** 目标是让人读到某句话时多看懂一点，不是把一章改写成分镜剧本。

1. 解压 [v0.9.3 AI 创作入门包](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.3/taleprism-agent-starter.zip)，把有权使用的一章原文副本（如 UTF-8 的 `chapter.txt`）放在 `prompts/` **旁边**。用 Codex 打开该目录，或在其中启动 Claude Code。只能上传附件时，上传原文、[01-source.md](01-source.md) 和 [03-shot-plan.md](03-shot-plan.md)；只能贴文字时，贴原文及两份模板的「可复制模板」。不要向外部服务上传无权分享的稿件。
2. **复制下面这条指令。** 它也能配合 v0.9.3 包内的旧模板使用。

   > 先读 chapter.txt、01-source.md 和 03-shot-plan.md（本地模板在 prompts/）。这次先做一页镜头计划，暂不生图，不改原文，段落编号只写在工作表上。最多选三处，一处就够，没有合适位置可以不画。每处写：① 放在哪一段之后？抄出届时已读到的逐字原句。② 这幅图要帮读者看懂什么？画面和公开图注／替代文字可以透露什么？如果用声音，可听见什么？③ 哪个细节还不能出现？到哪一句才能揭示，还是全文都没有证实？没有要保留的悬念就写无。④ 若是续图，写上一幅已选定的参考图、必须保持的东西和本次有意的变化及依据。没有前图就直说。把艺术推断和未确定项与原文事实分开，也不要把防剧透笔记当成公开图注。能写文件就另存 shot-plan.md，否则直接回复。等我选定镜头再继续。

   **怎样判断这一页可用？** 《末班灯》P02 末只写「只有一辆自行车的铃声从雨里穿过」：可以听见远处的铃，不能把穿黄雨衣的小满画进站台或把声景命名为「小满到了」。P04 的回忆里出现她的名字，也不等于她已在场。等到 P05「小满推着自行车进了站台」才适合画她和车。这是选镜示例，不是要求给成书加一段铃声。
3. **只做选定的第一幅。** 用[首图模板](05-first-image.md)出图，在原句旁看成图，再选它作后续参考。若要做下一幅，实际上传这张图和[续图模板](06-continuation.md)，例如「保留原来长凳宽度；图纸因 P03 的动作从卷起变成摊开」。不要把文件名、尚未选用的候选或生成工具的承诺当作参考图。没有生图工具时，交接指令和获许可的参考图即可。
4. **交给另一个视角先看。** 打开本地制作台的「用自己的图文开始」，导入原 TXT、把图放到选好的段落，先出试读稿。让审阅者不看生图提示词，从上一段读过落点，先记实见、实读、实听，再对照原句：图里有没有提前到场的人？标题、图注或 alt 有没有说出读者还猜不到的名字？声音或播放按钮名称有没有抢先揭晓？封面、图集缩略图如会更早出现，也在那个位置检查。没法听就写「未试听」，自己复核就署名自查；不要拿检查表当真人试读。能修就改图、改公开文字或后移，否则撤掉再试，不改小说。
5. **分清试读和定稿。** 作者选定并检查了实际导出的版本，再把整个 Reader ZIP 交给读者；另存可编辑工程备份。不要把含剧透的 `shot-plan.md`、参考图和私下审查理由塞进读本。草稿能导出，不代表已正式签核。[工作台步骤和版本差别](../docs/快速上手.md)；[三镜头实作](../examples/last-light/README.md)。

这条路径不用安装 Agent 插件或配置 Taleprism 密钥；你选用的模型或图片服务可能联网、收费。上述 Markdown **不是导入格式**。已有制作台项目、需要结构化往返时，在「章节制作方案」点「导出 AI 任务」，让 Agent 按任务 schema 返回 JSON，保留项目标识、原文指纹及版本，再「导入 AI 方案」作为待审草稿。不要给该 schema 追加工作表字段。

## English walkthrough

**One chapter, one still image and no sound is a complete first project.** Use a picture when it helps a reader notice something in the prose, not to turn the chapter into a screenplay.

1. Extract the [v0.9.3 AI Author Starter](https://github.com/Ethereal-Space-one/taleprism/releases/download/v0.9.3/taleprism-agent-starter.zip). Put an authorized chapter (e.g. UTF-8 `chapter.txt`) **beside**, not inside, `prompts/`. Open that folder in Codex or start Claude Code there. In an upload-only chat, attach the chapter, [01-source.md](01-source.md) and [03-shot-plan.md](03-shot-plan.md); in a text-only chat paste the chapter and the two copyable template blocks. Share only material you have the right to send to that service.
2. **Copy this prompt.** It also works with the older templates in the v0.9.3 download.

   > Read chapter.txt, 01-source.md and 03-shot-plan.md (the local templates are in prompts/). Give me a one-page shot plan. Do not generate images, rewrite the original or insert numbers into it. Pick up to three moments; one is enough and none is fine. For each: (1) Place it after a specific paragraph and quote the exact words already read. (2) What will the reader notice? What can the image, public caption/alt text and any sound reveal? (3) Hold back one specific detail until its first supporting line, or say it is never confirmed; if there is no reveal to protect, say so. (4) For a continuation, name the last frame selected for this sequence, what must stay, and the intentional change and its basis. Say if there is no earlier frame. Separate artistic choices and unknowns from facts. Keep private spoiler notes out of public copy. Save this as shot-plan.md if you can, or reply in chat. Wait for my selection.

   **What does a usable answer look like?** In *Last Light*, a bicycle bell is audible in P02. Do not yet show a rider or label the sound “Xiao Man arrives.” P04 mentions her in a memory; P05 is the first time she pushes her bicycle onto the platform. This is a planning exercise, not a claim that the published edition plays a bell.
3. Make only the selected [first image](05-first-image.md). Look at it beside the source before choosing it as a reference. For a [continuation](06-continuation.md), attach that actual frame and say what stays and what changes: “Keep the original bench width; the rolled plan now lies open as described in P03.” Do not pass off a filename or the latest unselected candidate as a reference. If the agent has no image tool, use its prompt and authorized references in a tool of your choice.
4. In **用自己的图文开始** in the local workbench, import the original TXT, place the image after its paragraph and export a draft. Ask a reviewer to start a passage earlier without the generation prompt; first describe what they actually see, read and hear, then compare with the source. Check the pixels, title, caption, alt text and any audible cue and player label. Check earlier cover or gallery exposure if applicable. Record self-review as self-review; mark anything unseen or unheard as unchecked. Repair, delay or omit the item, not the prose.
5. Exporting a draft is not formal acceptance. Once the author has checked the actual edition, share the **whole Reader ZIP**, and keep the editable project as a separate backup. Do not put the private spoiler plan, reference material or review rationale in the reader archive. See the [workbench instructions (Chinese)](../docs/快速上手.md) or try the [three-frame walkthrough](../examples/last-light/README.en.md).

No Taleprism plugin or model key is required for the handoff; your chosen service may process uploads remotely or charge for generation. The Markdown is **not** an import file. For a structured workbench round trip, use **导出 AI 任务** (Export AI Task), have the agent return JSON using the supplied schema and original project/source/revision metadata, then use **导入 AI 方案** (Import AI Plan) to review the draft. Do not add worksheet fields to the schema.
