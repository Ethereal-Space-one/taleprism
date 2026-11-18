"""Deliberately narrow, deterministic Chinese-text suggestions. Never calls a model."""

import re

# For an optional local cue, err toward omitting weather that is denied, over,
# imagined, or merely compared to something else. This isn't a semantic classifier.
NEGATION = {
    "rain": r"(?:无|無|没[有见]?|沒有|不再|并未|並未|未曾|不曾|不会|不會|别|別)(?:下|落|听到|聽到|一[丝絲滴点點场場]|[风風]也?[无無]?){0,3}[雨]|天[晴旱]|雨.{0,3}(?:已停|停了|停歇|停住|歇了|不再下|过天晴)",
    "wind": r"(?:无|無|没[有见]?|沒有|不再|并未|並未|未曾|不曾|不会|不會)(?:起|刮|吹|一[丝絲点點阵陣]|听到|聽到){0,2}[风風]|[风風].{0,3}(?:已停|停了|停歇|停住|歇了|不再吹)",
    "wave": r"(?:无|無|没有|沒有|不起)(?:一[丝絲点點]|任何)?[浪波]|[风風]平浪[静靜]|水面如[镜鏡]",
    "car": r"(?:无|無|没有|沒有|不见|不見)(?:一[辆輛])?(?:汽?[车車]|[车車][声聲])",
    "pencil": r"(?:钢笔|鋼筆|毛[笔筆]|[圆圓]珠[笔筆]|原子筆|粉[笔筆]|触控笔|觸控筆|蘸水筆|蘸水笔)|(?:没有|沒有|並未|并未|不再)(?:落[笔筆]|[写寫][字下]|落下)|(?:[笔筆]尖|[铅鉛][笔筆]).{0,3}(?:没碰|沒有碰|未落|悬停|懸停)",
}
NEGATION = {key: re.compile(value) for key, value in NEGATION.items()}
UNREAL = re.compile(r"假如|仿佛|彷彿|彷佛|好像|想象|想像|若是|如果|梦[里中]|夢[裡中]|以为|以為")
DENIED = re.compile(r"没有|沒有|并未|並未|并非|並非|不曾|未曾|从未|從未|不是|不把")
SENTENCES = re.compile(r"[^。！？!?；;]+[。！？!?；;]*[”」』’]*")
QUESTION = re.compile(
    r"(?:^|[“「：，])(?:[那这這一][把张張枚只封盏盞块塊本串件根支]?)?([\u3400-\u9fff]{2,8}?)(?:到底|究竟)?(?:藏在|放在|落在|在)(?:哪[里裡儿兒]|何处|何處)[呢呀吗嗎]?[？?]"
)
GIVEN = re.compile(
    r"(?:把|将|將)(?:[这這那一][把张張枚只封盏盞块塊本串件根支]?)?([\u3400-\u9fff]{2,10}?)(?:递给|遞給|交给|交給|借给|借給)"
)
RETURNED = re.compile(
    r"(?:把|将|將)(?:[这這那一][把张張枚只封盏盞块塊本串件根支]?)?([\u3400-\u9fff]{2,10}?)(?:还给|還給|交还|交還|归还|歸還)"
)
QUIET = {
    "sound": "本机线索没有找到明确而必要的声源。此处不铺声床，让文字自己定节奏。",
    "image": "本机线索不足以选出一处值得停看的动作或景物。先不加画，也不把气氛做成动效。",
    "presentation": "本机线索没有找到隔段成立的问答或物件交还。只因意象重现便让人回翻，会打断这次阅读。",
}


def contradicted(parameter, text):
    return parameter in NEGATION and bool(NEGATION[parameter].search(text))


def lines(blocks):
    for i, b in enumerate(blocks, 1):
        if b["heading"]:
            yield i, None
            continue
        for match in SENTENCES.finditer(b["text"]):
            sentence = match.group().strip()
            # Never manufacture a quotation by truncating or removing punctuation.
            if not (2 <= len(sentence) <= 160) or any(
                ord(c) < 32 or ord(c) in (0x2028, 0x2029) for c in sentence
            ):
                continue
            first = b["text"].find(sentence)
            if b["text"].find(sentence, first + 1) >= 0:
                continue
            yield i, sentence


# Each cue requires actual material/action, not the mere presence of a noun.
SOUND_CUES = [
    (
        "pencil",
        r"(?:[铅鉛][笔筆]|[笔筆]尖).{0,18}(?:划[过過]|擦[过過]|[写寫]下|落在|蹭[过過]|沙沙|划了).{0,14}(?:[纸紙]|一[笔筆道横橫]|名字|字)|(?:[纸紙]上|[纸紙]面).{0,10}[铅鉛][笔筆].{0,8}(?:划|蹭|擦|沙沙)",
        "只留一小组轻重不一的笔尖擦纸声，随后收住。不把这个动作铺成整段的背景。",
    ),
    (
        "car",
        r"(?:一[辆輛]|那[辆輛])(?:.{0,5})[车車].{0,12}(?:[驶駛]过|[驶駛]過|[开開]过|[开開]過|呼啸而过|呼嘯而過)",
        "让一辆车的声音靠近、越过，然后远去。不要把一次经过误做持续的车流。",
    ),
    (
        "rain",
        r"(?:雨[点點滴]|雨脚|雨腳).{0,8}(?:敲|打|落|砸|滴).{0,5}(?:窗|檐|瓦|屋顶|屋頂|棚)",
        "把听觉落在承雨的那一小片表面，只用细雨托住这段，不另加雷声或音乐。",
    ),
    (
        "wind",
        r"(?:[风風][声聲]|[风風](?:穿过|穿過|吹过|吹過|灌进|灌進)).{0,14}(?:呼呼|呜呜|嗚嗚|窗缝|窗縫|门缝|門縫|廊下)",
        "听的是风穿过空隙的声音，不是整片天地都在呼啸。声床应留在人声和文字之后。",
    ),
]
IMAGE_CUES = [
    (
        "still",
        r"(?:指尖|指腹|拇指|手指|手背).{0,12}(?:按住|压住|壓住|抹去|擦掉|捻住|捏住|抚平|撫平|摁住)",
        "取手与接触面的近景，把视线停在力气落下的地方。手保持静止，不替人物添加表情。",
    ),
    (
        "rain",
        r"雨(?:[点點滴]|水).{0,8}(?:落在|滑[过過]|打在|敲在).{0,8}(?:玻璃|窗|水[洼窪]|瓦)",
        "先找雨碰到的那一小块表面，把其余地方留静。只有实际底图看得见它、并经作者圈选复核，才考虑雨动效。",
    ),
    (
        "wave",
        r"(?:浪[头頭花]|潮水|波浪).{0,8}(?:拍在|拍向|拍打|撞上|涌上|湧上).{0,6}(?:岸|礁|石滩|石灘)",
        "把水与岸的接触线留在画面内，不让整幅画跟着摇。只有底图确有这条边、并经作者圈选复核，才考虑波浪动效。",
    ),
]
CUES = {
    k: [(p, re.compile(pattern), reason) for p, pattern, reason in items]
    for k, items in (("sound", SOUND_CUES), ("image", IMAGE_CUES))
}


def echo(blocks):
    questions, gifts = {}, {}
    for i, sentence in lines(blocks):
        if sentence is None:
            questions.clear()
            gifts.clear()
            continue
        if UNREAL.search(sentence) or DENIED.search(sentence):
            continue
        later = {"paragraph": i, "quote": sentence}
        if "？" not in sentence and "?" not in sentence:
            # A specific object's location must actually be disclosed afterwards.
            for name, earlier in questions.items():
                if (
                    name in sentence
                    and i - earlier["paragraph"] >= 2
                    and re.search(
                        re.escape(name)
                        + r"(?:原来|原來|其实|其實|一直|竟然|就|仍|还|還){0,3}(?:夹在|夾在|压在|壓在|藏在|躺在|搁在|擱在|塞在).{1,16}",
                        sentence,
                    )
                ):
                    return {
                        "decision": "echo",
                        "earlier": earlier,
                        "later": later,
                        "rationale": f"前一句让「{name}」的位置空着，后一句才把它落在实处。在回答之后再让读者翻回问题，不在开头泄底。",
                    }
            returned = RETURNED.search(sentence)
            if returned:
                name = returned[1]
                if name in gifts and i - gifts[name]["paragraph"] >= 2:
                    return {
                        "decision": "echo",
                        "earlier": gifts[name],
                        "later": later,
                        "rationale": f"上一回是把「{name}」交出去，这一回是交还。两句并置能看清手势的方向变了；中间照常读。",
                    }
        q = QUESTION.search(sentence)
        gift = GIVEN.search(sentence)
        if q:
            questions[q[1]] = later
        if gift and "？" not in sentence and "?" not in sentence:
            gifts[gift[1]] = later


def suggest(lens, blocks):
    if lens == "presentation":
        suggestion = echo(blocks)
        if suggestion:
            return suggestion
    else:
        for i, sentence in lines(blocks):
            if (
                not sentence
                or UNREAL.search(sentence)
                or DENIED.search(sentence)
                or re.search(r"[？?]", sentence)
            ):
                continue
            for value, cue, rationale in CUES[lens]:
                if cue.search(sentence) and not contradicted(value, blocks[i - 1]["text"]):
                    return {
                        "decision": lens,
                        lens: value,
                        "rationale": rationale,
                        "later": {"paragraph": i, "quote": sentence},
                    }
    return {"decision": "quiet", "rationale": QUIET[lens]}
