"""Resolve preserved merge history without silently changing saved compositions."""


def resolved_character_id(characters, character_id):
    seen = set()
    current = character_id
    while True:
        if current in seen or current not in characters:
            raise ValueError("人物合并关系缺失或循环，无法恢复引用。")
        seen.add(current)
        character = characters[current]
        target = character.get("merged_into")
        if character["status"] != "merged":
            if target:
                raise ValueError("人物状态与合并关系不一致。")
            return current
        if not target:
            raise ValueError("已合并人物缺少目标。")
        current = target
