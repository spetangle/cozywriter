// CozyWriter SPA - 路由调度器 + 全局状态
// 基于 Alpine.js 的轻量 SPA 架构

(function () {
    'use strict';

    // ─── 路由配置 ───
    const ROUTES = [
        { pattern: '#/', name: 'project_list' },
        { pattern: '#/questionnaire', name: 'questionnaire' },
        { pattern: '#/project/:id/novel', name: 'novel_editor' },
        { pattern: '#/project/:id/script', name: 'script_editor' },
        { pattern: '#/project/:id/settings', name: 'project_settings' },
        { pattern: '#/settings', name: 'global_settings' },
    ];

    // ─── 页面注册表 ───
    const pageRegistry = {};

    // ─── HTML 模板注册表 ───
    // 每个页面 JS 文件通过 window.registerPageTemplate(name, htmlString) 注册自己的 HTML 模板
    const pageTemplates = {};
    window.registerPageTemplate = function (name, template) {
        pageTemplates[name] = template;
    };

    // ─── 组件模板注册表 ───
    // 组件 JS（components/*.js）在页面 JS 之后加载，而页面模板字符串在模块求值时就已固化，
    // 因此页面里只放占位注释，挂载时再惰性替换 —— 这样与脚本加载顺序无关。
    const componentTemplates = {};
    window.registerComponentTemplate = function (name, template) {
        componentTemplates[name] = template;
    };

    // 把 <!--@component:name--> 占位符替换为已注册的组件模板
    function expandComponentTemplates(html) {
        return html.replace(/<!--@component:([A-Za-z0-9_]+)-->/g, (match, name) => {
            const tpl = componentTemplates[name];
            if (tpl === undefined) {
                console.warn('[Router] 组件模板未注册:', name);
                return '';
            }
            return tpl;
        });
    }

    // ─── 路由名 → Alpine.data 名称映射 ───
    const ROUTE_TO_ALPINE = {
        'project_list': 'projectList',
        'questionnaire': 'questionnaire',
        'novel_editor': 'novelEditor',
        'script_editor': 'scriptEditor',
        'project_settings': 'projectSettings',
        'global_settings': 'globalSettings',
    };

    // ─── 全局状态 ───
    const store = {
        currentRoute: { name: 'project_list', params: {} },
        previousRoute: null,
        routeView: null,
        initStatus: null,
        globalLoading: false,
        theme: 'light',
        sidebarCollapsed: false,
        breadcrumbs: [],

        // ─── 路由解析 ───
        parseHash(hash) {
            if (!hash) hash = window.location.hash || '#/';
            if (!hash.startsWith('#')) hash = '#' + hash;

            for (const route of ROUTES) {
                const params = this._matchRoute(hash, route.pattern);
                if (params !== null) {
                    return { name: route.name, params };
                }
            }
            return { name: 'project_list', params: {} };
        },

        _matchRoute(hash, pattern) {
            const hashParts = hash.replace(/^#/, '').split('/').filter(Boolean);
            const patternParts = pattern.replace(/^#/, '').split('/').filter(Boolean);

            if (hashParts.length !== patternParts.length) return null;

            const params = {};
            for (let i = 0; i < patternParts.length; i++) {
                const pp = patternParts[i];
                const hp = hashParts[i];
                if (pp.startsWith(':')) {
                    params[pp.slice(1)] = decodeURIComponent(hp);
                } else if (pp !== hp) {
                    return null;
                }
            }
            return params;
        },

        // ─── 导航 ───
        navigate(path) {
            if (!path.startsWith('/')) path = '/' + path;
            if (!window.location.hash.endsWith(path)) {
                window.location.hash = '#' + path;
            }
        },

        goBack() {
            if (this.previousRoute) {
                const path = this._routeToPath(this.previousRoute);
                window.location.hash = '#' + path;
            } else {
                window.location.hash = '#/';
            }
        },

        _routeToPath(route) {
            const routeDef = ROUTES.find(r => r.name === route.name);
            if (!routeDef) return '#/';
            let path = routeDef.pattern.replace(/^#/, '');
            for (const [key, value] of Object.entries(route.params || {})) {
                path = path.replace(':' + key, encodeURIComponent(value));
            }
            return '#' + path;
        },

        // ─── 路由挂载 ───
        // 注入页面 HTML 模板，然后用 Alpine.initTree 初始化动态注入的内容。
        // 每次挂载都创建一个全新的子 div 作为 Alpine 组件根节点：
        //   - 替换 innerHTML 会移除上一次的 div，Alpine 的 MutationObserver 自动销毁旧作用域
        //   - 新 div 是 Alpine 未处理过的元素，initTree 能可靠初始化
        mountPage(name, params) {
            this.previousRoute = { ...this.currentRoute };
            this.currentRoute = { name, params };
            this._saveLastRoute(name, params);
            this._updateBreadcrumbs(name, params);

            const container = document.getElementById('route-view');
            if (!container) {
                console.warn('[Router] #route-view container not found');
                return;
            }

            // 获取 HTML 模板（由各页面 JS 通过 window.registerPageTemplate 注册）
            const template = pageTemplates[name];
            if (!template) {
                console.warn('[Router] No HTML template registered for page:', name);
                container.innerHTML = `<div class="page-loading"><div class="spinner"></div><p>页面 "${name}" 模板未注册</p></div>`;
                return;
            }

            // 绑定 Alpine 组件（使用 Alpine.data 注册的名称），包裹在全新 div 中
            const alpineName = this._routeToAlpineName(name);
            const html = expandComponentTemplates(template);
            container.innerHTML = `<div x-data="${alpineName}" x-init="init()">${html}</div>`;

            // 通知 Alpine 初始化新注入的 DOM 子树
            try {
                Alpine.initTree(container);
            } catch (e) {
                console.error('[Router] Alpine.initTree failed:', e);
            }
        },

        // 路由名 → Alpine.data 名称
        _routeToAlpineName(routeName) {
            return ROUTE_TO_ALPINE[routeName] || routeName;
        },

        _updateBreadcrumbs(name, params) {
            const map = {
                project_list: [{ label: '项目列表', path: '/' }],
                questionnaire: [
                    { label: '项目列表', path: '/' },
                    { label: '创意问卷', path: '/questionnaire' },
                ],
                novel_editor: [
                    { label: '项目列表', path: '/' },
                    { label: '小说编辑器', path: `/project/${params.id}/novel` },
                ],
                script_editor: [
                    { label: '项目列表', path: '/' },
                    { label: '剧本编辑器', path: `/project/${params.id}/script` },
                ],
                project_settings: [
                    { label: '项目列表', path: '/' },
                    { label: '项目设置', path: `/project/${params.id}/settings` },
                ],
                global_settings: [
                    { label: '全局设置', path: '/settings' },
                ],
            };
            this.breadcrumbs = map[name] || [];
        },

        // ─── 持久化 ───
        _saveLastRoute(name, params) {
            try {
                localStorage.setItem('cozywriter.lastRoute', JSON.stringify({ name, params }));
            } catch (_) {}
        },

        restoreLastRoute() {
            try {
                const raw = localStorage.getItem('cozywriter.lastRoute');
                if (!raw) return null;
                return JSON.parse(raw);
            } catch (_) {
                return null;
            }
        },

        clearLastRoute() {
            try {
                localStorage.removeItem('cozywriter.lastRoute');
            } catch (_) {}
        },

        // ─── 错误处理 ───
        handleError(error, context) {
            console.error(`[App Error] ${context}:`, error);
            const message = error?.message || '未知错误';
            Alpine.store('app').toast(message, 'error');
        },

        toast(message, type = 'info', duration = 3000) {
            const event = new CustomEvent('cozywriter:toast', {
                detail: { message, type, duration },
            });
            document.dispatchEvent(event);
        },
    };

    // ─── 页面注册 API ───
    window.registerPage = function (name, component) {
        pageRegistry[name] = component;
    };

    // ─── Hash 路由监听 ───
    function handleHashChange() {
        const hash = window.location.hash || '#/';
        const { name, params } = store.parseHash(hash);
        store.mountPage(name, params);
    }

    // ─── 启动 SPA ───
    // 注意：Alpine 通过 <script defer> 加载，本脚本先于 Alpine 执行。
    // 因此 store 注册与首屏路由必须在 Alpine 生命周期事件中触发：
    //   - alpine:init      → 注册 $store.app（在 Alpine 遍历 DOM 之前，保证 #app 上的 $store.app 可用）
    //   - alpine:initialized → 启动首屏路由（Alpine 已初始化完毕，可安全调用 Alpine.initTree）
    function startRouting() {
        window.addEventListener('hashchange', handleHashChange);

        const saved = store.restoreLastRoute();
        if (saved && saved.name && saved.params) {
            const path = store._routeToPath(saved);
            if (path !== window.location.hash) {
                window.location.hash = path;
                return;
            }
        }

        handleHashChange();
    }

    document.addEventListener('alpine:init', () => {
        Alpine.store('app', store);
    });

    document.addEventListener('alpine:initialized', () => {
        startRouting();
    });

    window.CozyApp = {
        navigate: (path) => store.navigate(path),
        back: () => store.goBack(),
        getStore: () => store,
        registerPage: window.registerPage,
        parseHash: (h) => store.parseHash(h),
    };
})();