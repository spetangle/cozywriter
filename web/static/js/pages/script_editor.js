document.addEventListener('alpine:init', () => {
Alpine.data('scriptEditor', () => ({
    project: null,
    projectId: null,
    screenplays: [],
    currentScreenplay: null,
    activePanel: 'outline',
    loading: false,
    loadingScreenplays: false,

    characters: [],
    storyboards: [],
    properties: [],
    worldSettings: [],
    themes: [],
    plotPoints: [],

    showCreateScreenplayModal: false,
    createForm: {
        title: '',
        scene_number: 0,
        act: '第一幕',
        scene_type: '对话场景',
        location: '',
        time_of_day: '白天',
        characters_present: [],
        synopsis: '',
    },
    createSubmitting: false,

    showGenerateModal: false,
    generating: false,
    generatePrompt: '',
    generateMode: 'continue',
    taskProgress: 0,

    // 分镜面板的密度/生成状态已下沉到 components/storyboard_panel.js
    // 此处仅保留 storyboards 数组：底部状态栏的「分镜数」需要读它

    tokenUsage: null,
    tokenUsageLoading: false,
    currentLlmLabel: '',

    panels: [
        { id: 'outline', label: '大纲', icon: '📋' },
        { id: 'scene', label: '场景', icon: '🎬' },
        { id: 'character', label: '角色', icon: '👥' },
        { id: 'storyboard', label: '分镜', icon: '🎞️' },
        { id: 'property', label: '道具', icon: '🗝️' },
        { id: 'world', label: '世界观', icon: '🌍' },
        { id: 'theme', label: '主题', icon: '🎯' },
        { id: 'plot', label: '剧情', icon: '📊' },
    ],

    get projectId() {
        return Alpine.store('app').currentRoute.params.id;
    },

    init() {
        const id = Alpine.store('app').currentRoute.params.id;
        this.loadProject(id);
        this.loadScreenplays(id);
        // characters / properties 由对应的面板组件自行加载（见 components/*.js）
        this.loadThemes(id);
        this.loadPlotPoints(id);
        this.loadWorldSettings(id);
        this.loadTokenUsage(id);
        this._loadCurrentLlm();
    },

    async loadProject(id) {
        this.loading = true;
        try {
            const res = await fetch(`/api/projects/${id}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.project = await res.json();
        } catch (e) {
            console.error('加载项目失败:', e);
            Alpine.store('app').toast('加载项目失败: ' + e.message, 'error');
        } finally {
            this.loading = false;
        }
    },

    async loadScreenplays(projectId) {
        this.loadingScreenplays = true;
        try {
            const res = await fetch(`/api/projects/${projectId}/screenplays`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.screenplays = await res.json();
            if (this.screenplays.length > 0 && !this.currentScreenplay) {
                this.selectScreenplay(this.screenplays[0]);
            }
        } catch (e) {
            console.error('加载剧本列表失败:', e);
            Alpine.store('app').toast('加载剧本列表失败: ' + e.message, 'error');
        } finally {
            this.loadingScreenplays = false;
        }
    },

    selectScreenplay(screenplay) {
        this.currentScreenplay = screenplay;
        this.loadStoryboardsForScreenplay(screenplay.id);
    },

    async createScreenplay() {
        const f = this.createForm;
        if (!f.title.trim()) {
            Alpine.store('app').toast('请输入场景标题', 'warning');
            return;
        }
        this.createSubmitting = true;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/screenplays`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: f.title.trim(),
                    scene_number: f.scene_number || (this.screenplays.length + 1),
                    act: f.act,
                    scene_type: f.scene_type,
                    location: f.location.trim(),
                    time_of_day: f.time_of_day,
                    characters_present: f.characters_present,
                    synopsis: f.synopsis.trim(),
                    project_id: this.projectId,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const screenplay = await res.json();
            this.screenplays.push(screenplay);
            this.showCreateScreenplayModal = false;
            Alpine.store('app').toast('场景创建成功', 'success');
            this.selectScreenplay(screenplay);
        } catch (e) {
            console.error('创建场景失败:', e);
            Alpine.store('app').toast('创建失败: ' + e.message, 'error');
        } finally {
            this.createSubmitting = false;
        }
    },

    openCreateScreenplayModal() {
        this.createForm = {
            title: '',
            scene_number: this.screenplays.length + 1,
            act: '第一幕',
            scene_type: '对话场景',
            location: '',
            time_of_day: '白天',
            characters_present: [],
            synopsis: '',
        };
        this.showCreateScreenplayModal = true;
    },

    async deleteScreenplay(screenplayId) {
        if (!confirm('确定删除此场景？')) return;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/screenplays/${screenplayId}`, {
                method: 'DELETE',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.screenplays = this.screenplays.filter(s => s.id !== screenplayId);
            if (this.currentScreenplay?.id === screenplayId) {
                this.currentScreenplay = this.screenplays[0] || null;
            }
            Alpine.store('app').toast('场景已删除', 'success');
        } catch (e) {
            console.error('删除场景失败:', e);
            Alpine.store('app').toast('删除失败: ' + e.message, 'error');
        }
    },

    async _pollTask(task_id, opts = {}) {
        const interval = opts.interval || 2000;
        const timeout = opts.timeout || 600000;
        const onProgress = opts.onProgress || (() => {});
        const t0 = Date.now();
        while (Date.now() - t0 < timeout) {
            try {
                const res = await fetch(`/api/tasks/${task_id}`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const task = await res.json();
                onProgress(task);
                if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                    return task;
                }
            } catch (e) {
                console.warn(`[PollTask ${task_id}] err:`, e);
            }
            await new Promise((r) => setTimeout(r, interval));
        }
        throw new Error(`Task ${task_id} 轮询超时（${timeout}ms）`);
    },

    async generateScreenplay(screenplayId) {
        if (!this.generatePrompt.trim()) {
            Alpine.store('app').toast('请输入生成引导', 'warning');
            return;
        }
        this.generating = true;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/screenplays/${screenplayId}/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: this.generatePrompt.trim(),
                    mode: this.generateMode,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.showGenerateModal = false;
            this.generatePrompt = '';
            Alpine.store('app').toast('场景生成中...', 'info');

            // 后端是异步任务，必须轮询到终态再刷新，否则读到的是旧数据
            const task = await this._pollTask(data.task_id, {
                onProgress: (t) => { this.taskProgress = t.progress || 0; },
            });
            if (task.status !== 'completed') {
                throw new Error(task.error || `任务${task.status}`);
            }
            await this.loadScreenplays(this.projectId);
            await this.loadCharacters(this.projectId);
            await this.loadProperties(this.projectId);
            Alpine.store('app').toast('场景生成完成', 'success');
        } catch (e) {
            console.error('生成场景失败:', e);
            Alpine.store('app').toast('生成失败: ' + e.message, 'error');
        } finally {
            this.generating = false;
            this.taskProgress = 0;
        }
    },

    // 原地替换数组内容，保持引用不变。
    // 面板组件（components/*.js）是嵌套的 Alpine 子作用域，通过作用域链读这些数组；
    // 若改为整体赋值，子作用域调用时会创建同名自有属性遮蔽父级，导致数据分裂。
    _replaceAll(arr, items) {
        arr.length = 0;
        arr.push(...(items || []));
    },

    async loadStoryboardsForScreenplay(screenplayId) {
        try {
            const res = await fetch(`/api/projects/${this.projectId}/screenplays/${screenplayId}/storyboards`);
            if (!res.ok) return;
            this._replaceAll(this.storyboards, await res.json());
        } catch (e) {
            console.warn('加载分镜失败:', e);
        }
    },

    async loadProperties(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/properties`);
            if (!res.ok) return;
            this._replaceAll(this.properties, await res.json());
        } catch (e) {
            console.warn('加载道具失败:', e);
        }
    },

    async loadCharacters(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/characters`);
            if (!res.ok) return;
            this._replaceAll(this.characters, await res.json());
        } catch (e) {
            console.warn('加载角色失败:', e);
        }
    },

    async loadThemes(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/themes`);
            if (!res.ok) return;
            this.themes = await res.json();
        } catch (e) {
            console.warn('加载主题失败:', e);
        }
    },

    async loadPlotPoints(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/plot-points`);
            if (!res.ok) return;
            this.plotPoints = await res.json();
        } catch (e) {
            console.warn('加载剧情点失败:', e);
        }
    },

    async loadWorldSettings(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/worldbuilding`);
            if (!res.ok) return;
            this.worldSettings = await res.json();
        } catch (e) {
            console.warn('加载世界观失败:', e);
        }
    },

    async loadTokenUsage(projectId) {
        this.tokenUsageLoading = true;
        try {
            const res = await fetch(`/api/token-usage/project/${projectId}`);
            if (!res.ok) return;
            this.tokenUsage = await res.json();
        } catch (e) {
            console.warn('加载 token 用量失败:', e);
        } finally {
            this.tokenUsageLoading = false;
        }
    },

    async _loadCurrentLlm() {
        try {
            const res = await fetch('/api/config/status');
            if (!res.ok) return;
            const data = await res.json();
            if (data.default_provider) {
                const providerMap = {
                    anthropic: 'Claude', openai: 'OpenAI', ollama: 'Ollama',
                    minimax: 'MiniMax', mimo: 'MiMo',
                };
                const name = providerMap[data.default_provider.toLowerCase()] || data.default_provider;
                this.currentLlmLabel = data.current_model
                    ? `${name} · ${data.current_model}`
                    : name;
            }
        } catch (_) {}
    },

    setPanel(name) {
        this.activePanel = name;
    },

    async saveScreenplayContent() {
        if (!this.currentScreenplay) return;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/screenplays/${this.currentScreenplay.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: this.currentScreenplay.title,
                    act: this.currentScreenplay.act,
                    scene_type: this.currentScreenplay.scene_type,
                    location: this.currentScreenplay.location,
                    time_of_day: this.currentScreenplay.time_of_day,
                    characters_present: this.currentScreenplay.characters_present,
                    content: this.currentScreenplay.content,
                    synopsis: this.currentScreenplay.synopsis,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('保存成功', 'success');
        } catch (e) {
            console.error('保存失败:', e);
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        }
    },

    get totalScreenplays() {
        return this.screenplays.length;
    },

    get totalStoryboards() {
        return this.storyboards.length;
    },

    get actOptions() {
        return ['第一幕', '第二幕', '第三幕', '第四幕', '尾声'];
    },

    get sceneTypeOptions() {
        return ['对话场景', '动作场景', '情感场景', '悬疑场景', '战斗场景', '过渡场景'];
    },

    get timeOfDayOptions() {
        return ['清晨', '早晨', '中午', '下午', '傍晚', '黄昏', '夜晚', '深夜'];
    },

    formatTime(ts) {
        if (!ts) return '';
        return new Date(ts).toLocaleString('zh-CN');
    },

    backToHome() {
        Alpine.store('app').navigate('/');
    },

    goToSettings() {
        Alpine.store('app').navigate(`/project/${this.projectId}/settings`);
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('script_editor', `
<div class="page script-editor-page">
  <template x-if="loading">
    <div class="page-loading"><div class="spinner"></div><p>加载项目中...</p></div>
  </template>

  <template x-if="!loading && project">
    <div class="editor-layout">
      <!-- 顶部信息栏 -->
      <header class="editor-header">
        <div class="header-left">
          <button class="btn-icon" @click="backToHome()" title="返回">←</button>
          <h2 x-text="project.title"></h2>
          <span class="llm-badge" x-show="currentLlmLabel">🤖 <span x-text="currentLlmLabel"></span></span>
        </div>
        <div class="header-right">
          <button class="btn-secondary" @click="goToSettings()">⚙️ 项目设置</button>
        </div>
      </header>

      <div class="editor-body">
        <!-- 左侧：场景列表（按幕分组） -->
        <aside class="editor-sidebar">
          <div class="sidebar-header">
            <span>🎬 场景列表</span>
            <button class="btn-icon" @click="openCreateScreenplayModal()" title="新建场景">➕</button>
          </div>
          <div class="scene-list">
            <template x-if="loadingScreenplays">
              <p class="loading-hint">⏳ 加载中...</p>
            </template>
            <template x-if="!loadingScreenplays && screenplays.length === 0">
              <p class="empty-hint">暂无场景</p>
            </template>
            <template x-for="sp in screenplays" :key="sp.id">
              <div class="scene-item" :class="{ active: currentScreenplay && currentScreenplay.id === sp.id }" @click="selectScreenplay(sp)">
                <div class="scene-item-header">
                  <span class="scene-act" x-text="sp.act"></span>
                  <span class="scene-num" x-text="'#' + sp.scene_number"></span>
                </div>
                <div class="scene-title" x-text="sp.title"></div>
                <div class="scene-meta">
                  <span x-show="sp.location">📍 <span x-text="sp.location"></span></span>
                  <span x-show="sp.time_of_day">🕐 <span x-text="sp.time_of_day"></span></span>
                </div>
                <button class="btn-tiny btn-danger" @click.stop="deleteScreenplay(sp.id)" title="删除">🗑️</button>
              </div>
            </template>
          </div>
        </aside>

        <!-- 右侧：工具面板 + 编辑区 -->
        <main class="editor-main">
          <!-- 工具面板切换 -->
          <nav class="panel-tabs">
            <template x-for="p in panels" :key="p.id">
              <button class="panel-tab" :class="{ active: activePanel === p.id }" @click="setPanel(p.id)">
                <span x-text="p.icon"></span> <span x-text="p.label"></span>
              </button>
            </template>
          </nav>

          <div class="panel-content">
            <!-- 大纲面板 -->
            <div x-show="activePanel === 'outline'" class="panel-section">
              <template x-if="!currentScreenplay">
                <p class="empty-hint">请选择或创建一个场景</p>
              </template>
              <template x-if="currentScreenplay">
                <div class="outline-panel">
                  <h3>场景概要</h3>
                  <textarea x-model="currentScreenplay.synopsis" rows="4" placeholder="场景概要..."></textarea>
                  <div class="form-actions">
                    <button class="btn-primary" @click="saveScreenplayContent()">💾 保存</button>
                    <button class="btn-secondary" @click="showGenerateModal = true">🤖 AI 生成场景</button>
                  </div>
                </div>
              </template>
            </div>

            <!-- 场景编辑面板 -->
            <div x-show="activePanel === 'scene'" class="panel-section">
              <template x-if="!currentScreenplay">
                <p class="empty-hint">请选择或创建一个场景</p>
              </template>
              <template x-if="currentScreenplay">
                <div class="scene-editor">
                  <div class="scene-info-grid">
                    <label>标题 <input type="text" x-model="currentScreenplay.title"></label>
                    <label>幕
                      <select x-model="currentScreenplay.act">
                        <template x-for="a in actOptions" :key="a"><option :value="a" x-text="a"></option></template>
                      </select>
                    </label>
                    <label>场景类型
                      <select x-model="currentScreenplay.scene_type">
                        <template x-for="s in sceneTypeOptions" :key="s"><option :value="s" x-text="s"></option></template>
                      </select>
                    </label>
                    <label>地点 <input type="text" x-model="currentScreenplay.location"></label>
                    <label>时间
                      <select x-model="currentScreenplay.time_of_day">
                        <template x-for="t in timeOfDayOptions" :key="t"><option :value="t" x-text="t"></option></template>
                      </select>
                    </label>
                  </div>
                  <label>场景正文</label>
                  <textarea class="scene-content-editor" x-model="currentScreenplay.content" rows="18" placeholder="编写场景正文..."></textarea>
                  <div class="form-actions">
                    <button class="btn-primary" @click="saveScreenplayContent()">💾 保存</button>
                    <button class="btn-secondary" @click="showGenerateModal = true">🤖 AI 续写</button>
                  </div>
                </div>
              </template>
            </div>

            <!-- 角色面板（components/character_panel.js） -->
            <div x-show="activePanel === 'character'" class="panel-section">
              <!--@component:character_panel-->
            </div>

            <!-- 分镜面板（components/storyboard_panel.js） -->
            <div x-show="activePanel === 'storyboard'" class="panel-section">
              <!--@component:storyboard_panel-->
            </div>

            <!-- 道具面板（components/property_panel.js） -->
            <div x-show="activePanel === 'property'" class="panel-section">
              <!--@component:property_panel-->
            </div>

            <!-- 世界观面板 -->
            <div x-show="activePanel === 'world'" class="panel-section">
              <h3>🌍 世界观设定</h3>
              <template x-if="worldSettings.length === 0"><p class="empty-hint">暂无世界观设定</p></template>
              <div class="card-list">
                <template x-for="w in worldSettings" :key="w.id">
                  <div class="info-card">
                    <h4 x-text="w.name || w.title || '-'"></h4>
                    <p x-text="w.description || w.content || ''"></p>
                  </div>
                </template>
              </div>
            </div>

            <!-- 主题面板 -->
            <div x-show="activePanel === 'theme'" class="panel-section">
              <h3>🎯 主题列表（共 <span x-text="themes.length"></span> 个）</h3>
              <template x-if="themes.length === 0"><p class="empty-hint">暂无主题</p></template>
              <div class="card-list">
                <template x-for="t in themes" :key="t.id">
                  <div class="info-card">
                    <h4 x-text="t.name || t.title || '-'"></h4>
                    <p x-text="t.description || t.content || ''"></p>
                  </div>
                </template>
              </div>
            </div>

            <!-- 剧情面板 -->
            <div x-show="activePanel === 'plot'" class="panel-section">
              <h3>📊 剧情点（共 <span x-text="plotPoints.length"></span> 个）</h3>
              <template x-if="plotPoints.length === 0"><p class="empty-hint">暂无剧情点</p></template>
              <table class="data-table" x-show="plotPoints.length > 0">
                <thead><tr><th>标题</th><th>重要度</th><th>状态</th><th>标签</th></tr></thead>
                <tbody>
                  <template x-for="pp in plotPoints" :key="pp.id">
                    <tr>
                      <td x-text="pp.title || pp.name || '-'"></td>
                      <td x-text="pp.importance || '-'"></td>
                      <td x-text="pp.status || '-'"></td>
                      <td x-text="(pp.tags && pp.tags.length) ? pp.tags.join('、') : '-'"></td>
                    </tr>
                  </template>
                </tbody>
              </table>
            </div>
          </div>
        </main>
      </div>

      <!-- 底部状态栏 -->
      <footer class="editor-footer">
        <span>🎬 场景数：<strong x-text="totalScreenplays"></strong></span>
        <span>🎞️ 分镜数：<strong x-text="totalStoryboards"></strong></span>
        <template x-if="tokenUsage">
          <span>📊 Token：输入 <strong x-text="tokenUsage.input_tokens || tokenUsage.prompt_tokens || 0"></strong> / 输出 <strong x-text="tokenUsage.output_tokens || tokenUsage.completion_tokens || 0"></strong></span>
        </template>
      </footer>

      <!-- ═══ 创建场景弹窗 ═══ -->
      <template x-if="showCreateScreenplayModal">
        <div class="modal-overlay" @click.self="showCreateScreenplayModal = false">
          <div class="modal">
            <button class="modal-close-x" @click="showCreateScreenplayModal = false">×</button>
            <h2>🎬 新建场景</h2>
            <form @submit.prevent="createScreenplay()">
              <div class="form-grid">
                <label>场景标题
                  <input type="text" x-model="createForm.title" placeholder="例如：酒馆相遇" required>
                </label>
                <label>幕
                  <select x-model="createForm.act">
                    <template x-for="a in actOptions" :key="a"><option :value="a" x-text="a"></option></template>
                  </select>
                </label>
                <label>场景序号
                  <input type="number" x-model.number="createForm.scene_number" min="0">
                </label>
                <label>场景类型
                  <select x-model="createForm.scene_type">
                    <template x-for="s in sceneTypeOptions" :key="s"><option :value="s" x-text="s"></option></template>
                  </select>
                </label>
                <label>地点
                  <input type="text" x-model="createForm.location" placeholder="例如：破旧酒馆">
                </label>
                <label>时间
                  <select x-model="createForm.time_of_day">
                    <template x-for="t in timeOfDayOptions" :key="t"><option :value="t" x-text="t"></option></template>
                  </select>
                </label>
              </div>
              <label>场景概要
                <textarea x-model="createForm.synopsis" rows="3" placeholder="场景概要..."></textarea>
              </label>
              <div class="form-footer">
                <button type="button" class="btn-secondary" @click="showCreateScreenplayModal = false">取消</button>
                <button type="submit" class="btn-primary" :disabled="createSubmitting">
                  <span x-show="!createSubmitting">🎬 创建</span>
                  <span x-show="createSubmitting">⏳ 创建中...</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      </template>

      <!-- ═══ AI 生成弹窗 ═══ -->
      <template x-if="showGenerateModal">
        <div class="modal-overlay" @click.self="showGenerateModal = false">
          <div class="modal">
            <button class="modal-close-x" @click="showGenerateModal = false">×</button>
            <h2>🤖 AI 生成场景</h2>
            <label>生成模式
              <select x-model="generateMode">
                <option value="continue">续写</option>
                <option value="rewrite">重写</option>
              </select>
            </label>
            <label>生成引导
              <textarea x-model="generatePrompt" rows="4" placeholder="描述你希望场景如何发展..."></textarea>
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showGenerateModal = false">取消</button>
              <button class="btn-primary" :disabled="generating || !generatePrompt.trim()" @click="currentScreenplay && generateScreenplay(currentScreenplay.id)">
                <span x-show="!generating">🚀 生成</span>
                <span x-show="generating">⏳ 生成中...</span>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </template>
</div>
`);