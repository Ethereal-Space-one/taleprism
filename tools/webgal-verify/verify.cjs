// Parse every exported line with the actual, pinned WebGAL parser.
const fs = require('node:fs');
const path = require('node:path');
const { default: SceneParser, SCRIPT_CONFIG, ADD_NEXT_ARG_LIST } = require('webgal-parser');
const root = process.argv[2];
try {
  const expected = JSON.parse(fs.readFileSync(path.join(root, 'storygal-manifest.json'), 'utf8'));
  const script = fs.readFileSync(path.join(root, 'game/scene/start.txt'), 'utf8');
  const parser = new SceneParser(undefined, (name) => name, ADD_NEXT_ARG_LIST, SCRIPT_CONFIG);
  const lines = parser.parse(script, 'start', 'start.txt').sentenceList;
  const dialogue = lines.filter(s => s.commandRaw === 'say');
  if (dialogue.length !== expected.units.length) throw Error('对白条数不匹配');
  const decode = value => {
    if (!/^SGTEXT_(?:[0-9a-f]{6})+$/.test(value)) throw Error('非法正文编码');
    return String.fromCodePoint(...value.slice(7).match(/.{6}/g).map(x => parseInt(x, 16)));
  };
  dialogue.forEach((line, i) => {
    if (decode(line.content) !== expected.units[i].text) throw Error(`第 ${i + 1} 框正文不一致`);
    const speaker = expected.units[i].speaker_name;
    const args = line.args.filter(a => a.key !== 'vocal');
    const vocal = line.args.find(a => a.key === 'vocal');
    const expectedVocal = expected.units[i].vocal_id;
    if ((vocal?.value || null) !== (expectedVocal ? expectedVocal + '.wav' : null)) throw Error('配音挂载不匹配');
    if (expectedVocal && !fs.existsSync(path.join(root, 'game/vocal', expectedVocal + '.wav'))) throw Error('音频文件缺失');
    if (line.args.length !== (expectedVocal ? 2 : 1) || args.length !== 1 || (speaker
      ? args[0].key !== 'speaker' || decode(args[0].value) !== speaker
      : args[0].key !== 'clear' || args[0].value !== true))
      throw Error(`第 ${i + 1} 框出现意外参数`);
  });
  let currentFigure = null;
  let cursor = 0;
  let eventCursor = 0, background = null, diagram = false, textbox = true;
  const events = expected.visual_events || [];
  for (const line of lines) {
    if (line.commandRaw === 'setTextbox') {
      if (!['hide','on'].includes(line.content)) throw Error('文本框状态无效');
      textbox = line.content !== 'hide';
    }
    if (line.commandRaw === 'changeBg') {
      const value = line.content || null;
      if (diagram && value === background) { diagram = false; }
      else {
        const event = events[eventCursor];
        if (!event || event.after_unit_id !== cursor - 1 || value !== event.asset_id + '.png') throw Error('视觉演出锚点或资源不匹配');
        if (!fs.existsSync(path.join(root,'game/background',value))) throw Error('插图资源缺失');
        const next = line.args.some(a=>a.key==='next' && a.value===true);
        if (['diagram','illustration'].includes(event.kind)) {
          if (next || textbox || currentFigure) throw Error('图解必须独立暂停显示并隐藏正文和立绘');
          diagram=true;
        } else { if(!next) throw Error('插图不能增加正文停顿'); background=value; }
        eventCursor++;
      }
    }
    if (line.commandRaw === 'changeFigure') {
      currentFigure = line.content || null;
      if (currentFigure && !(expected.figure_assets || []).some(a => a.id + '.png' === currentFigure))
        throw Error('立绘没有已确认资产依据');
      if (currentFigure && !fs.existsSync(path.join(root, 'game/figure', currentFigure))) throw Error('立绘文件缺失');
    }
    if (line.commandRaw === 'say') {
      if (!textbox || diagram) throw Error('图解后未恢复正文显示');
      const asset = expected.units[cursor++].figure_asset_id;
      if (currentFigure !== (asset ? asset + '.png' : null)) throw Error('立绘和说话人不一致');
    }
  }
  if (eventCursor !== events.length || diagram || !textbox) throw Error('视觉演出未完整结束');
  const allowed = new Set(['say', 'comment', 'end', 'changeFigure','changeBg','setTextbox']);
  if (lines.some(s => !allowed.has(s.commandRaw))) throw Error('出现意外引擎命令');
  process.stdout.write(JSON.stringify({ parser: 'webgal-parser@4.6.5', units: dialogue.length, passed: true }));
} catch (error) {
  process.stderr.write(String(error.message));
  process.exitCode = 1;
}
