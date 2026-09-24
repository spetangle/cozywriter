// SPA 组件模板装配测试
//
// 用最小浏览器 stub 按 index.html 的顺序加载 app.js / pages / components，
// 然后驱动真实的 store.mountPage()，验证：
//   1. 页面模板里的 <!--@component:xxx--> 占位符被正确展开（无残留）
//   2. 每个组件的 Alpine.data 都注册了
//   3. 展开后的 HTML 标签配平（防止嵌套错误导致 Alpine 解析失败）
//   4. 组件模板引用的 x-data 名称与注册的 Alpine.data 名称一致
//
// 运行：node tests/test_spa_components.js

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.join(__dirname, '..');
const WEB = path.join(ROOT, 'web', 'static', 'js');

const failures = [];
function check(name, cond, detail = '') {
    console.log(`  ${cond ? 'PASS' : 'FAIL'}  ${name}${!cond && detail ? '  ' + detail : ''}`);
    if (!cond) failures.push(name);
}

// ─── 浏览器环境 stub ───
const alpineDataNames = [];
const listeners = {};
const routeView = { innerHTML: '' };

const sandbox = {
    console,
    setTimeout,
    clearTimeout,
    Date,
    JSON,
    Math,
    Object,
    Array,
    String,
    Number,
    Boolean,
    Promise,
    RegExp,
    Error,
    encodeURIComponent,
    decodeURIComponent,
    fetch: () => Promise.reject(new Error('no network in test')),
    CustomEvent: class { constructor(t, o) { this.type = t; Object.assign(this, o); } },
    Alpine: {
        data: (name) => { alpineDataNames.push(name); },
        store: () => ({ toast: () => {}, navigate: () => {}, breadcrumbs: [] }),
        initTree: () => {},
    },
    localStorage: {
        _d: {},
        getItem(k) { return this._d[k] || null; },
        setItem(k, v) { this._d[k] = String(v); },
        removeItem(k) { delete this._d[k]; },
    },
};
sandbox.window = sandbox;
sandbox.globalThis = sandbox;
sandbox.window.addEventListener = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); };
sandbox.window.dispatchEvent = () => {};
sandbox.window.location = { hash: '#/' };
sandbox.document = {
    addEventListener: (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); },
    dispatchEvent: () => {},
    getElementById: (id) => (id === 'route-view' ? routeView : null),
};

vm.createContext(sandbox);

// ─── 按 index.html 的顺序加载 ───
const files = [
    'app.js',
    'pages/project_list.js',
    'pages/questionnaire.js',
    'pages/novel_editor.js',
    'pages/script_editor.js',
    'pages/project_settings.js',
    'pages/global_settings.js',
    'components/character_panel.js',
    'components/storyboard_panel.js',
    'components/property_panel.js',
];
for (const rel of files) {
    const code = fs.readFileSync(path.join(WEB, rel), 'utf8');
    try {
        vm.runInContext(code, sandbox, { filename: rel });
    } catch (e) {
        console.log(`  FAIL  加载 ${rel} 抛异常: ${e.message}`);
        failures.push(`load ${rel}`);
    }
}

// 触发 alpine:init，让各文件注册 Alpine.data
for (const fn of listeners['alpine:init'] || []) fn();

console.log('\n[1] Alpine.data 注册');
for (const name of ['scriptEditor', 'characterPanel', 'storyboardPanel', 'propertyPanel']) {
    check(`注册了 ${name}`, alpineDataNames.includes(name));
}

// ─── 驱动真实 mountPage ───
console.log('\n[2] mountPage 展开占位符');
const store = sandbox.window.CozyApp.getStore();
store.mountPage('script_editor', { id: 'testproj' });
const html = routeView.innerHTML;

check('生成了 scriptEditor 根节点', html.includes('x-data="scriptEditor"'), html.slice(0, 120));
check('无残留 @component 占位符', !html.includes('@component:'),
    (html.match(/@component:[a-z_]+/g) || []).join(','));
for (const name of ['characterPanel', 'storyboardPanel', 'propertyPanel']) {
    check(`展开了 ${name} 面板`, html.includes(`x-data="${name}"`));
}

// 组件模板内容确实进来了（抽查各面板的标志性文案）
check('角色面板含外貌 tab', html.includes('外貌设定') && html.includes('appearanceFields'));
check('分镜面板含密度选择', html.includes('分镜密度') && html.includes('AI 生成分镜'));
check('道具面板含流转历史', html.includes('流转历史') && html.includes('新建道具'));

console.log('\n[3] 标签配平');
// 统计常见容器标签的开合数量（忽略自闭合与 void 元素）
const voidTags = new Set(['input', 'br', 'hr', 'img', 'meta', 'link', 'option']);
const counts = {};
const tagRe = /<\/?([a-zA-Z][a-zA-Z0-9-]*)\b[^>]*?>/g;
let m;
while ((m = tagRe.exec(html)) !== null) {
    const raw = m[0];
    const tag = m[1].toLowerCase();
    if (voidTags.has(tag)) continue;
    if (raw.endsWith('/>')) continue;
    counts[tag] = counts[tag] || { open: 0, close: 0 };
    if (raw.startsWith('</')) counts[tag].close++;
    else counts[tag].open++;
}
let unbalanced = [];
for (const [tag, c] of Object.entries(counts)) {
    if (c.open !== c.close) unbalanced.push(`${tag}(开${c.open}/闭${c.close})`);
}
check('所有标签开合配平', unbalanced.length === 0, unbalanced.join(' '));

console.log('\n[4] 其他页面模板未被破坏');
for (const page of ['novel_editor', 'project_list', 'global_settings']) {
    routeView.innerHTML = '';
    try {
        store.mountPage(page, { id: 'testproj' });
        const h = routeView.innerHTML;
        check(`${page} 挂载成功且无占位符残留`,
            h.length > 100 && !h.includes('@component:'));
    } catch (e) {
        check(`${page} 挂载成功`, false, e.message);
    }
}

console.log('\n' + (failures.length === 0 ? 'ALL PASS' : `${failures.length} FAILED: ${failures.join(', ')}`));
process.exit(failures.length === 0 ? 0 : 1);
