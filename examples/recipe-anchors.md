# 配方中的对白字节锚点

`tools/build_content_pack.py` 的 `dialogues` 支持 `byte_start`、`byte_end`，用于区分原文中内容相同的对白。`text` 和 `character` 仍为必填字段；`character` 必须与配方 `characters[].name` 对应。

例如，原文严格为 `甲说：「好。」乙说：「好。」`（无 BOM、无换行）时：

```json
{
  "dialogues": [
    {"text": "好。", "character": "甲", "byte_start": 12, "byte_end": 18},
    {"text": "好。", "character": "乙", "byte_start": 33, "byte_end": 39}
  ]
}
```

- 两个锚点字段必须同时提供，且为 JSON 整数。范围从 0 开始，左闭右开，即 `[byte_start, byte_end)`。
- 坐标基于项目的 `source.utf8.txt` 字节，必须落在 UTF-8 字符边界。UTF-8 输入直接使用原文件字节；GB18030 输入按后端相同规则无损转为 UTF-8 后计数。BOM、空格、CRLF 都保留并计入，不能先去空白或转换换行。
- 范围必须恰好覆盖一条完整的最外层对白内容，**不包含外层引号**；嵌套引号、对白内部的空白则保留。该范围解码后必须逐字等于 `text`。
- 不支持旁白范围、对白片段、跨对白范围，或对同一对白重复分配任务。配方任务的顺序不影响定位；也不会按人物提示或“剩下的那一处”猜选。
- 旧写法 `{"text": "唯一的一句对白。", "character": "甲"}` 继续支持，前提是该完整对白在整篇原文中只出现一次。重复时明确报错，要求补齐两个锚点字段。
- 允许的字段为 `text`、`character`、`voice_prefix`、`byte_start`、`byte_end`；未知字段会报错，避免拼错锚点后悄悄退回文字匹配。
- `text`、`character` 必须为非空字符串；锚点必须为整数，布尔值不算整数。可选 `voice_prefix` 若出现，必须为非空字符串，不能有首尾空白或控制字符；不请求该句配音时省略字段，不能用 `null`、数字、布尔值或空字符串代替。关闭配音时仍执行这些类型检查。

可在项目审校接口 `/api/projects/{id}/review` 的 `dialogues` 中读取锚点，或在创建项目前用同一解析器列出全部候选：

```python
from pathlib import Path
from storygal.review import top_dialogues
from storygal.text import decode_source

_, source = decode_source(Path("source.txt").read_bytes())
for line in top_dialogues(source):
    print({key: line[key] for key in ("text", "byte_start", "byte_end")})
```

在项目 Python 环境中运行上述代码，逐条核对上下文后填写 `character`。解析器产生的临时 `id` 不写入配方，稳定引用使用字节范围。

构建器在建立客户端连接前完成全部对白字段类型、原文锚点和说话人引用预检。原文、图片、立绘依赖哈希检查及已校验字节上传保持有效；修改带连续性检查记录的配方后，原配方哈希会失效，需重新核对，不能仅为通过构建而自动更新检查记录。

默认构建不合成语音，也不增加语音能力请求。启用 `--with-local-audio`（函数参数 `with_audio=True`）时，在 `POST /api/projects` 前先请求一次 **服务器** `GET /api/speech/capabilities`。该接口无需项目，只返回服务器本机合成能力，与 `Speech.state` 的 `capabilities` 同源，不读取云端能力、不写项目，也不合成语音。

每个 `voice_prefix` 按大小写敏感的前缀匹配服务器音色名称，必须恰好匹配一个不同名称。完全相同的重复名称视作一个音色；不同名称即使只是系统版本或地区后缀不同，也不会默认选第一个。比如 `Tingting` 同时匹配 `Tingting (zh_CN)` 和 `Tingting (zh_TW)` 时，需填写能唯一匹配的更完整名称。即使前缀本身等于某个完整音色名称，只要还匹配另一名称，也会报歧义。

所有待配音对白一次性完成音色校验，同一人物必须解析到同一音色；通过后使用已解析的完整名称，不在逐句构建时重新猜选。能力接口不可读、响应无效、请求的合成能力不可用、前缀不存在或有歧义时，明确失败，**不创建项目、不写入对白、不触发合成**。没有 `voice_prefix` 的对白不配音；若整份配方都没有待配音任务，合成能力不可用不会阻止构建。服务器在预检之后停用音色或运行时合成失败，仍按正常构建错误处理；预检不保证服务器后续状态不变。
