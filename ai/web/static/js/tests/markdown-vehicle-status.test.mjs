import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const dir = dirname(fileURLToPath(import.meta.url));
const vendor = join(dir, '..', '..', 'vendor', 'markdown-it');

function loadMarkdown() {
  const sandbox = {
    window: {},
    document: { readyState: 'complete', getElementById: () => null, addEventListener() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  for (const f of [
    join(vendor, 'markdown-it-tasklists.bundle.js'),
    join(vendor, 'purify.min.js'),
    join(vendor, 'highlight.min.js'),
    join(dir, '..', 'markdown.js'),
  ]) {
    vm.runInNewContext(readFileSync(f, 'utf8'), sandbox, { filename: f });
  }
  sandbox.DOMPurify = sandbox.DOMPurify || sandbox.window?.DOMPurify;
  sandbox.OpMarkdown = sandbox.OpMarkdown || sandbox.window?.OpMarkdown;
  sandbox.hljs = sandbox.hljs || sandbox.window?.hljs;
  return sandbox.window.Markdown;
}

const Markdown = loadMarkdown();
let failed = 0;

function check(name, html, pred) {
  const ok = pred(html);
  console.log(ok ? 'PASS' : 'FAIL', name);
  if (!ok) {
    failed += 1;
    console.log(html.slice(0, 500));
  }
}

const vehicle = '当前车辆状态如下：  项目  状态  ------  ------  车速  0km/h';
check('vehicle dash table', Markdown.render(vehicle), (h) => h.includes('<table') && h.includes('车速'));

const pipe = '| a | b |\n|---|---|\n| 1 | 2 |';
check('gfm pipe table', Markdown.render(pipe), (h) => h.includes('<table') && h.includes('1'));

const tasks = '- [x] done\n- [ ] todo';
check('task list', Markdown.render(tasks), (h) => h.includes('task-list-item') && h.includes('checkbox'));

const code = '```python\nprint("hi")\n```';
check('code fence', Markdown.render(code), (h) => h.includes('md-code-wrap') && h.includes('md-code-copy'));

const glued = '##当前车辆状态报告 ### 基础状态 |项目|值||-------|-----|||车速|0.0km/h (静止)||openpilot|X 未启用| ### 车型指纹 |项目|值||-------|-----|||车型|unknown|';
check('glued vehicle report', Markdown.render(glued), (h) => h.includes('<table') && h.includes('车速') && !h.includes('||'));

const gluedHeader = '##当前车辆状态报告';
check('header spacing', Markdown.render(gluedHeader), (h) => h.includes('<h2') && !h.includes('##当前'));

const el = { classList: { add() {} }, innerHTML: '', textContent: '' };
Object.defineProperty(el, 'innerHTML', { set(v) { this._html = v; }, get() { return this._html || ''; } });
Markdown.renderToElement(el, vehicle, { streaming: true });
check('streaming vehicle', el.innerHTML, (h) => h.includes('<table'));

function loadMarkdownLiteOnly() {
  const sandbox = {
    window: {},
    document: { readyState: 'complete', getElementById: () => null, addEventListener() {} },
  };
  sandbox.window = sandbox;
  sandbox.globalThis = sandbox;
  vm.runInNewContext(readFileSync(join(dir, '..', 'markdown.js'), 'utf8'), sandbox, { filename: 'markdown.js' });
  return sandbox.window.Markdown;
}

const Lite = loadMarkdownLiteOnly();
const oneLine = '当前车辆状态报告 ###基础状态 |项目|值| |---|---| |车速|0.0km/h (静止)| |openpilot启用|❌ 未启用|';
check('lite fallback one-line report', Lite.render(oneLine), (h) => h.includes('<table') && h.includes('车速'));

const userSample = '当前车辆状态报告 ###基础状态 |项目|值| |---|---| |车速|0.0km/h (静止) | |openpilot启用|❌ 未启用| ###车型指纹 |项目|值| |---|---|';
check('user one-line with markdown-it', Markdown.render(userSample), (h) => h.includes('<table') && h.includes('<h3') && h.includes('车速'));

const gluedHeaderTable = '###基础状态|项目|值|\n|---|---|\n|车速|0.0km/h (静止)|\n|openpilot启用|❌ 未启用|';
check('glued header|table no space', Markdown.render(gluedHeaderTable), (h) => h.includes('<table') && h.includes('车速') && !h.includes('基础状态|项目'));

const multilineTable = `| 禁止事项 | 说明 |
| --- | --- |
| 转向/制动指令 | 不会直接发送 |
| 行驶中改参 | 不会未经确认修改 |
| × 无根据的方案 | 不清楚时会说「需要更多信息」
- 📁 文件操作
- 🔍 搜索 |`;
check('multiline table cell', Markdown.render(multilineTable), (h) => h.includes('<table') && h.includes('无根据的方案') && !h.includes('<p>|'));

const userGluedRows = '### 查询结果\n\n| 项目 | 返回值 |\n| 车速 vEgo | 0.0km/h |\n| 是否启用 enabled | false || 点火 ignition | false || 车型指纹 | 空 |';
check('glued rows on one line', Markdown.render(userGluedRows), (h) => h.includes('<table') && h.includes('点火 ignition') && !h.includes('<p>|'));

const dashHeader = '| 项目 | 返回值 | ------ | --------- |\n| 车速 vEgo | 0.0km/h | | |';
check('dash cells stripped from header', Markdown.render(dashHeader), (h) => {
  const head = (h.match(/<thead>[\s\S]*?<\/thead>/) || [''])[0];
  return h.includes('<table') && head.includes('项目') && !head.includes('<th>------</th>') && (head.match(/<th>/g) || []).length === 2;
});

const capability = '基于你当前的PC开发环境, 我整理一下我能做的全部事项：——\n\n🪄 核心能力总览\n\n1️⃣ 车辆诊断 (实车接入时)\n- 读取方向盘转角\n\n2️⃣ 调参与优化';
check('emoji section headers', Markdown.render(capability), (h) => h.includes('<p>') && h.includes('<hr') && h.includes('<h3') && h.includes('核心能力总览') && h.includes('<h4') && h.includes('车辆诊断') && !h.includes('——'));

const diag3 = '### 诊断结论\n\n| 组件 | 返回值 | 说明 |\n| --- | --- | --- |\n| StateReader | 报错 | 无法读取 |';
check('3-col table viewport wrapper', Markdown.render(diag3), (h) => h.includes('markdown-table') && h.includes('markdown-table__viewport') && !h.includes('md-table-wrap'));

const lonePipe = '| StateReader | Params (carFingerprint等) |';
check('lone pipe row becomes table', Markdown.render(lonePipe), (h) => h.includes('<table') && h.includes('StateReader') && !h.includes('<p>|'));

process.exit(failed ? 1 : 0);
