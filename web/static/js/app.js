// CozyWriter Alpine.js 主应用

function app() {
  return {
    // ─── State ───
    showSetupWizard: false,
    setupStep: 2,
    selectedProvider: null,
    providerConfig: { apiKey: '', baseUrl: 'http://localhost:11434', model: '' },
    modelStatus: { model_name: '', downloaded: false, cache_size_mb: null },
    downloading: false,

    showSettings: false,
    showProjectSettings: false,
    settings: { defaultProvider: 'anthropic' },

    // 服务商管理
    providers: [],
    editingProvider: null,    // 正在编辑的服务商（null = 查看模式）
    providerForm: { id: '', name: '', api_key: '', base_url: '', model: '' },
    showAddProvider: false,
    providerSaving: false,

    // 任务管理
    showTaskManager: false,
    allTasks: [],
    _taskPollHandle: null,

    // 模型下载进度（SSE）
    downloadProgress: {
      stage: 'idle',     // idle / started / migrating / downloading / finished / error
      current: 0,
      total: 0,
      message: '',
      elapsed_s: 0,
      percent: 0,
      speed_mbps: 0,
    },

    // 项目 & 章节
    projects: [],
    currentProject: null,
    chapters: [],
    currentChapter: null,

    // 面板状态
    activePanel: 'writing',
    subPanel: 'themes',  // 子面板

    // 设定预览数据（从 /api/workflow/project/{id}/bootstrap-data 加载）
    bootstrapData: null,
    bootstrapDataLoading: false,

    // 角色
    characters: [],
    showCharacterForm: false,
    characterForm: { name: '', role: '配角', description: '' },

    // 主题/伏笔
    themes: [],
    showThemeForm: false,
    themeForm: { theme_type: 'core_theme', title: '', description: '' },
    foreshadowings: [],
    showForeshadowingForm: false,
    foreshadowingForm: { title: '', content: '' },

    // ─── 项目引导补全（Bootstrap Workflow） ───
    showCreateProjectModal: false,         // 主创建表单 modal
    showMissingFieldsModal: false,         // 必填缺失时弹出的"补全问卷" modal
    missingFields: [],                     // 后端返回的缺失字段
    missingQuestionnaire: [],              // 后端返回的问卷题目
    bootstrapWizard: {                     // 引导向导页状态
      visible: false,
      projectId: null,
      runId: null,
      status: 'idle',                       // idle / running / completed / committed / failed
      stages: [],                           // stage 列表
      pollHandle: null,                     // 轮询句柄
      errorMsg: '',
      startedAt: null,
      completedAt: null,
      rerunAllBusy: false,                  // "重新生成全部" 是否正在执行
      committing: false,                    // 写入数据库时防止重复提交
    },
    // 「设定文档预览」界面（大纲/角色/世界观/伏笔/主题）的"重新生成"按钮状态
    // 按 stage_id 记录是否正在跑，避免同一 stage 并发触发
    rerunStageBusy: {},
    // 扩写大纲浮层状态（支持扩写 / 缩减 / 无变化）
    showExtendOutlineModal: false,
    extendOutlineOriginalTotal: 0,       // 原目标总章节数 (Project.total_chapters)
    extendOutlineGenerated: 0,            // 已生成一句话大纲的章数
    extendOutlineExtendBy: 0,             // 计划向后扩展的章数 (可负:负数=缩减)
    extendOutlineNewTotal: 0,             // 新目标章节总数
    extendOutlineArchitecture: true,      // 是否同时扩写架构层 (仅扩写时生效)
    extendOutlineBusy: false,             // 是否正在扩写
    // 创建项目表单（12 字段：4 必填 + 8 选填）
    newProjectForm: {
      // 4 必填
      title: '',
      chapter_word_count: 3,
      genre: '',          // 旧版字符串（兼容后端），提交时由 genres 数组覆盖
      genres: [],         // 新版多选（≥1 个）
      description: '',
      // 扩展字段
      total_chapters: 100,  // 预计总章节数，默认100
      // 8 选填
      theme: '',
      tone: '',
      style: '',
      pacing: '',
      premise: '',
      protagonist: '',
      antagonist: '',
      supporting: '',
      notes: '',
    },
    newGenreInput: '',   // 用户输入新题材
    // ── 选题静态选项（与后端 MISSING_QUESTIONNAIRE / STAGE_PROMPTS 对齐） ──
    createFormOptions: {
      chapter_word_options: [2, 3, 4, 5],
      genres: ['玄幻', '都市', '科幻', '武侠', '仙侠', '历史', '悬疑', '现实主义', '奇幻', '其他'],
      tones: ['热血', '治愈', '黑暗', '轻松', '史诗', '悬疑紧张', '浪漫', '幽默', '冷峻'],
      styles: ['优美', '平实', '诗意', '幽默', '冷峻'],
      pacings: ['快节奏', '中等节奏', '慢热型', '起伏型'],
    },

    // 角色弧光
    characterArcs: [],
    showArcForm: false,
    arcForm: { character_id: null, arc_type: 'growth', start_state: '', current_state: '', end_state: '' },

    // 角色关系
    characterRelations: [],
    showRelationForm: false,
    relationForm: { from_character_id: null, to_character_id: null, relation_type: '友情', description: '', strength: 5 },

    // ─── 角色关系图谱（可交互） ───
    relGraphNodes: [],         // 图谱节点（含 _key 唯一标识 + x/y 坐标 + role + name）
    relGraphEdges: [],         // 图谱边（来源 characterRelations + AI relations 合并）
    relGraphView: { x: 0, y: 0, scale: 1 },  // 平移 + 缩放
    relGraphDragging: {       // 拖拽状态
      canvas: false,           // 是否正在拖动画布
      node: null,              // 当前正在拖拽的节点 key
      lastX: 0,                // 鼠标上一帧位置
      lastY: 0,
      panStartView: null,      // 拖画布开始时的视图位置
    },
    relGraphSelectedNodeId: null,    // 当前选中节点
    relGraphSelectedEdgeId: null,    // 当前选中边
    relGraphAddMode: false,          // 是否处于"新建关系"模式
    relGraphAddStep: 'pickFrom',     // pickFrom / pickTo / confirm
    relGraphAddFrom: null,           // 已选的起点节点 key
    relGraphAddTo: null,             // 已选的终点节点 key
    relGraphToggleLabels: true,      // 是否显示关系标签
    relGraphEditForm: { relation_type: '', description: '', strength: 5, status: 'stable' },  // 边编辑表单
    relGraphNewForm: { relation_type: '友情', description: '', strength: 5 },  // 新建表单
    relGraphLoaded: false,           // 是否已加载过图（避免重复 load）

    // 一致性检查
    consistencyResult: null,
    consistencyReport: null,

    // 灵感收集
    inspirations: [],
    inspirationSubPanel: 'list',
    allInspirationTags: [],
    selectedTag: null,
    newInspiration: { content: '', source: '', tagInput: '' },

    // ─── 灵感主界面（1 级功能） ───
    showInspirationHub: false,
    showInspirationEditor: false,
    showCreateFromInspiration: false,
    showFuseInspiration: false,
    inspirations: [],
    inspLoading: false,
    inspSearch: {
      q: '',
      tag: '',
      source: '',
      projectScope: 'global',  // global / current / all
      includeConsumed: false,
    },
    inspTagCloud: [],
    inspSources: [],          // 所有 source 列表（去重）
    inspirationCount: 0,      // topbar badge
    editingInspiration: { id: null, title: '', content: '', source: '', tagInput: '', project_id: null },
    inspForCreateProject: null,  // 当前"创建项目"操作绑定的灵感
    inspForFuse: null,           // 当前"融合"操作绑定的灵感
    createFromInspForm: { title: '', chapter_word_count: 3, genre: '其他', description: '' },
    fuseForm: { project_id: '', target: 'outline', chapterOrder: null, note: '' },
    chapterSelectOptions: [],  // 融合时可选的章节 order 列表
    fuseTargetChapterId: null,  // 用于 chapter:N 格式

    // ─── 题材（多选 + 自定义） ───
    genreList: [],


    // 创意问卷
    activeQuestionnaire: null,
    savedQuestionnaires: [],
    allQuestionnaires: [],
    qStep: 0,
    qAnswers: {},
    qQuestions: [],

    // 大纲/细纲
    // 注意：移除"剧情线/结构/章节细纲"三个标签页后，projectOutline、plotlineForm、
    // showPlotlineForm、expandedChapterId 等手动编辑剧情线/结构相关的状态/方法
    // 不再被 UI 引用，已彻底清理。下面的 chapterOutlines / chapterOutlinesMap
    // 仍保留，因为写作面板的"细纲"标签和项目总览的章节进度条都会用到。
    outlineSubPanel: 'overview',
    chapterOutlines: [],
    chapterOutlinesMap: {},
    // 章节的"已发生事件 + RAG 相似事件"（防重复写作辅助面板）
    chapterPrepInfo: null,

    // 评审
    reviewSubPanel: 'new',
    reviewHistory: [],
    activeReviewSession: null,
    reviewResult: null,

    // 当前使用的 LLM provider + 模型名（顶部工具栏展示用）
    currentLlmLabel: '',

    // 最后浏览位置（用户刷新页面时还原）
    lastView: { projectId: null, chapterId: null, panel: 'writing', writingTab: 'content' },

    // 伏笔面板筛选：'all' | 'planted' | 'active' | 'resolved' | 'abandoned'
    foreshadowingFilter: 'all',

    // 剧情追踪
    plotPoints: [],
    plotSearch: { q: '', status: '', importance: '', rangeMin: null, rangeMax: null },
    plotExpandedId: null,
    showPlotPointForm: false,
    plotForm: { id: null, title: '', description: '', tagInput: '', importance: 'major', status: 'planning',
                intro_chapter_id: null, develop_chapter_id: null, climax_chapter_id: null, resolve_chapter_id: null,
                intro_note: '', develop_note: '', climax_note: '', resolve_note: '' },

    // 预览面板
    previewSubTab: 'content',   // content / outline / review
    writingTab: 'content',       // content / outline / review (写作台内页签)
    
    // 导出功能
    showExportModal: false,
    exportChapterIds: [],        // 选中的章节ID
    exportRechapter: false,      // 是否重新分章
    exportWordsPerChapter: 3000, // 重新分章时每章字数
    exportFormat: 'txt',         // 导出格式: txt / markdown
    exportSaveIndividual: false, // 章节独立保存（每章一个文件，打包zip）
    chapterDirty: false,             // 用户手动编辑过内容
    chapterContentSnapshot: '',      // 进入章节时的内容快照（用于 diff）
    previewChapter: null,
    previewReview: null,

    // AI 生成
    showGenerateModal: false,
    generateMode: 'continue',
    generatePrompt: '',
    generateWordCount: '3000',
    generating: false,
    generatedText: null,

    // 一键生成设置浮层
    showPipelineSetupModal: false,
    pipelineSetupChapter: 1,  // 默认生成下一章
    pipelineSetupGuide: '',   // 内容引导

    // ─── 批量生成 ───
    showBatchGenerateModal: false,
    batchGenerateStart: 1,     // 从第几章之后开始
    batchGenerateCount: 5,     // 生成章节数量
    batchGenerateGuide: '',    // 内容引导（选填）
    batchGenerating: false,
    batchTask: null,           // { id, status, result }
    batchPollHandle: null,     // setInterval handle

    // 修订功能
    showReviseConfirmModal: false,

    // 一键生成已有内容章节时的二次确认
    showRegenerateConfirmModal: false,
    _pendingPipelineGuide: '',  // 用户在 setup 浮层填的引导，触发确认时暂存

    // 字数调整（独立功能）
    showWordAdjustModal: false,
    wordAdjustPlan: null,         // { action: 'compress'|'expand'|'none', delta: N }
    wordAdjustTaskId: null,       // 当前异步任务 id
    wordAdjustSubmitting: false,  // 防重复提交
    // 自定义字数上下限（输入框默认填项目设定值，方便直接修改）
    wordAdjustUseCustom: false,
    wordAdjustCustomMin: null,
    wordAdjustCustomTarget: null,
    wordAdjustCustomMax: null,
    // 按目标字数 ± 百分比 快捷设置
    wordAdjustPctInput: 10,

    // ─── 9 步章节生成流水线（chapter_pipeline）───
    // 后端：/api/chapters/generate-pipeline (POST) → task_id
    // 轮询 /api/tasks/{id} 拿实时 9 step 状态
    showPipelineProgress: false,
    pipelineTask: null,        // 当前正在跟踪的 task 完整对象（含 result.stages）
    pipelinePollHandle: null,  // setInterval 句柄
    pipelineStartTs: 0,        // pipelineStartedAt，用于 elapsed_text
    // 任务管理弹窗：chapter_pipeline 类型的任务是否展开子任务详情
    expandedTaskIds: [],

    // ─── Init ───
    async init() {
      await this.checkInitStatus();
    },

    async checkInitStatus() {
      try {
        const res = await fetch('/api/init/status');
        const data = await res.json();
        this.showSetupWizard = data.needs_setup;
        if (!data.needs_setup) {
          await this.loadProjects();
          // 加载全局数据（不阻塞 wizard 恢复）
          this.loadGenres();
          this.loadInspirationCount();
          // 加载当前 LLM provider / 模型名（顶部工具栏展示）
          this._loadCurrentLlm();
          // 恢复批量生成任务（页面刷新后）
          this._rehydrateBatchTask();
          // 检查是否有进行中的 workflow run，有则自动恢复 wizard
          await this._rehydrateBootstrapIfNeeded();
          // 恢复用户上次浏览的位置（project / chapter / panel / writingTab）
          await this._rehydrateLastView();
        } else {
          await this.refreshModelStatus();
        }
      } catch (e) {
        console.error('初始化检查失败:', e);
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
      } catch (e) { /* ignore */ }
    },

    // 页面刷新后恢复批量生成任务（从 localStorage）
    async _rehydrateBatchTask() {
      try {
        const raw = localStorage.getItem('cozywriter.batchTask');
        if (!raw) return;
        const saved = JSON.parse(raw);
        if (!saved || !saved.id) {
          localStorage.removeItem('cozywriter.batchTask');
          return;
        }
        // 查询后端 task 状态
        const res = await fetch('/api/tasks/' + saved.id);
        if (!res.ok) {
          // 后端已无此 task（重启后丢失），清掉 localStorage
          localStorage.removeItem('cozywriter.batchTask');
          return;
        }
        const data = await res.json();
        if (['completed', 'failed', 'cancelled'].includes(data.status)) {
          // 已结束：清掉 localStorage，不恢复浮层（用户看到时已晚）
          localStorage.removeItem('cozywriter.batchTask');
          return;
        }
        // 仍在进行：恢复轮询 + 浮层
        console.log('[BatchTask] 恢复批量任务:', saved.id);
        this.batchTask = data;
        this.batchGenerating = true;
        this.startBatchPolling();
      } catch (e) {
        console.warn('[BatchTask] rehydrate failed:', e);
        try { localStorage.removeItem('cozywriter.batchTask'); } catch (_) {}
      }
    },

    // 页面刷新后恢复上次浏览位置（项目 + 章节 + 面板 + 写作台标签页）
    async _rehydrateLastView() {
      try {
        const raw = localStorage.getItem('cozywriter.lastView');
        if (!raw) return;
        const saved = JSON.parse(raw);
        if (!saved || !saved.projectId) return;
        // 校验项目是否还存在
        const project = this.projects.find(p => p.id === saved.projectId);
        if (!project) {
          console.log('[LastView] 项目已不存在，清掉 lastView');
          localStorage.removeItem('cozywriter.lastView');
          return;
        }
        // 打开项目
        await this.openProject(project);
        // 恢复面板
        if (saved.panel && ['writing', 'outline-plan', 'character-matrix', 'worldbuilding', 'theme', 'check', 'inspirations'].includes(saved.panel)) {
          this.activePanel = saved.panel;
        }
        // 恢复章节（如该章节还在项目里）
        if (saved.chapterId) {
          const ch = this.chapters.find(c => c.id === saved.chapterId);
          if (ch) {
            await this.selectChapter(ch);
            // 恢复写作台 tab
            if (saved.writingTab && ['content', 'outline', 'review'].includes(saved.writingTab)) {
              this.writingTab = saved.writingTab;
            }
          }
        }
        console.log('[LastView] 已恢复上次浏览位置', saved);
      } catch (e) {
        console.warn('[LastView] rehydrate failed:', e);
        try { localStorage.removeItem('cozywriter.lastView'); } catch (_) {}
      }
    },

    // 保存当前浏览位置（项目 / 章节 / 面板 / 写作台 tab）
    _saveLastView() {
      try {
        const payload = {
          projectId: this.currentProject ? this.currentProject.id : null,
          chapterId: this.currentChapter ? this.currentChapter.id : null,
          panel: this.activePanel,
          writingTab: this.writingTab,
        };
        localStorage.setItem('cozywriter.lastView', JSON.stringify(payload));
      } catch (_) { /* localStorage may be disabled */ }
    },

    async _rehydrateBootstrapIfNeeded() {
      try {
        const res = await fetch('/api/workflow/in-flight');
        if (!res.ok) return;
        const data = await res.json();
        if (!data.run) return;
        // 有进行中的 run → 自动重开 wizard
        const run = data.run;
        console.log('[Bootstrap] rehydrating in-flight run:', run.run_id, 'project', run.project_id);
        this.openBootstrapWizard(run.project_id, run.run_id);
      } catch (e) {
        console.warn('[Bootstrap] rehydrate check failed:', e);
      }
    },

    async refreshModelStatus() {
      try {
        const res = await fetch('/api/models/status');
        this.modelStatus = await res.json();
      } catch (e) { console.error(e); }
    },

    // ─── Setup Wizard ───
    nextSetupStep() { this.setupStep = 3; },

    async saveProvider() {
      try {
        await fetch('/api/config/save-provider', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: this.selectedProvider,
            apiKey: this.providerConfig.apiKey || undefined,
            baseUrl: this.providerConfig.baseUrl || undefined,
          }),
        });
        this.setupStep = 4;
        await this.refreshModelStatus();
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    // ─── 全局设置 ───
    async openGlobalSettings() {
      await this.loadProviders();
      this.showSettings = true;
    },

    async loadProviders() {
      try {
        const res = await fetch('/api/providers');
        this.providers = await res.json();
        const def = this.providers.find(p => p.is_default);
        if (def) this.settings.defaultProvider = def.id;
      } catch (e) { console.error('加载服务商失败:', e); }
    },

    async setDefaultProvider(providerId) {
      try {
        await fetch('/api/providers/set-default', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider_id: providerId }),
        });
        await this.loadProviders();
      } catch (e) { alert('切换失败: ' + e.message); }
    },

    startEditProvider(provider) {
      this.editingProvider = provider.id;
      this.providerForm = {
        id: provider.id,
        name: provider.name,
        api_key: '',
        base_url: provider.base_url || '',
        model: provider.model || '',
      };
    },

    cancelEditProvider() {
      this.editingProvider = null;
      this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
    },

    async saveProviderEdit() {
      if (this.providerSaving) return;
      this.providerSaving = true;
      try {
        const pid = this.editingProvider;
        const body = {};
        if (this.providerForm.name) body.name = this.providerForm.name;
        if (this.providerForm.api_key) body.api_key = this.providerForm.api_key;
        if (this.providerForm.base_url !== undefined) body.base_url = this.providerForm.base_url;
        if (this.providerForm.model !== undefined) body.model = this.providerForm.model;

        const res = await fetch(`/api/providers/${pid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || '保存失败');
        }
        this.editingProvider = null;
        await this.loadProviders();
      } catch (e) { alert('保存失败: ' + e.message); }
      finally { this.providerSaving = false; }
    },

    startAddProvider() {
      this.showAddProvider = true;
      this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
    },

    cancelAddProvider() {
      this.showAddProvider = false;
      this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
    },

    async createProvider() {
      if (this.providerSaving) return;
      if (!this.providerForm.id || !this.providerForm.name) {
        alert('ID 和名称为必填');
        return;
      }
      this.providerSaving = true;
      try {
        const res = await fetch('/api/providers', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            id: this.providerForm.id,
            name: this.providerForm.name,
            api_key: this.providerForm.api_key || undefined,
            base_url: this.providerForm.base_url || undefined,
            model: this.providerForm.model || undefined,
          }),
        });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || '创建失败');
        }
        this.showAddProvider = false;
        await this.loadProviders();
      } catch (e) { alert('创建失败: ' + e.message); }
      finally { this.providerSaving = false; }
    },

    async deleteProvider(providerId) {
      if (!confirm(`确认删除服务商 "${providerId}"？`)) return;
      try {
        const res = await fetch(`/api/providers/${providerId}`, { method: 'DELETE' });
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || '删除失败');
        }
        await this.loadProviders();
      } catch (e) { alert('删除失败: ' + e.message); }
    },

    async downloadModel() {
      if (this.downloading) return;
      this.downloading = true;
      this.downloadProgress = {
        stage: 'started',
        current: 0,
        total: 0,
        message: '准备下载...',
        elapsed_s: 0,
        percent: 0,
        speed_mbps: 0,
      };
      try {
        const res = await fetch('/api/models/download', { method: 'POST' });
        if (!res.ok || !res.body) {
          throw new Error(`HTTP ${res.status}`);
        }
        // 解析 SSE 流
        const reader = res.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          // SSE 事件以 \n\n 分隔
          let sepIdx;
          while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
            const block = buffer.slice(0, sepIdx);
            buffer = buffer.slice(sepIdx + 2);
            for (const line of block.split('\n')) {
              if (line.startsWith('data: ')) {
                try {
                  const data = JSON.parse(line.slice(6));
                  this._onDownloadProgress(data);
                } catch (e) {
                  console.warn('bad SSE chunk', e);
                }
              }
            }
          }
        }
        await this.refreshModelStatus();
      } catch (e) {
        this.downloadProgress = {
          ...this.downloadProgress,
          stage: 'error',
          message: '下载失败: ' + e.message,
        };
        setTimeout(() => alert('下载失败: ' + e.message), 100);
      } finally {
        this.downloading = false;
      }
    },

    _onDownloadProgress(data) {
      // 计算百分比和速度
      let percent = 0;
      if (data.total > 0) {
        percent = Math.min(100, Math.round((data.current / data.total) * 100));
      }
      let speed_mbps = 0;
      if (data.elapsed_s > 0 && data.current > 0 && data.stage === 'downloading') {
        const bytes_per_s = data.current / data.elapsed_s;
        speed_mbps = bytes_per_s / 1024 / 1024;
      }
      this.downloadProgress = {
        stage: data.stage,
        current: data.current,
        total: data.total,
        message: data.message || '',
        elapsed_s: data.elapsed_s || 0,
        percent,
        speed_mbps,
        cache_size_mb: data.cache_size_mb,
      };
    },

    formatBytes(n) {
      if (n < 1024) return n + ' B';
      if (n < 1024 * 1024) return (n / 1024).toFixed(1) + ' KB';
      if (n < 1024 * 1024 * 1024) return (n / 1024 / 1024).toFixed(1) + ' MB';
      return (n / 1024 / 1024 / 1024).toFixed(2) + ' GB';
    },

    finishSetup() {
      this.showSetupWizard = false;
      this.loadProjects();
    },

    // ─── 任务管理 ───

    async openTaskManager() {
      this.showTaskManager = true;
      await this.refreshAllTasks();
      // 每 3s 刷新（任务管理 UI 主动轮询）
      if (this._taskPollHandle) clearInterval(this._taskPollHandle);
      this._taskPollHandle = setInterval(() => {
        if (this.showTaskManager) this.refreshAllTasks();
      }, 3000);
    },

    async refreshAllTasks() {
      try {
        const res = await fetch('/api/tasks/all');
        if (!res.ok) {
          // 后端没这个接口时回退：聚合 in-flight + 项目任务
          const all = [];
          if (this.currentProject) {
            const r2 = await fetch(`/api/tasks/project/${this.currentProject.id}`);
            if (r2.ok) all.push(...(await r2.json()));
          }
          this.allTasks = all;
          return;
        }
        this.allTasks = await res.json();
      } catch (e) {
        console.warn('refreshAllTasks failed:', e);
      }
    },

    async terminateAllTasks() {
      if (!confirm('确定终止所有正在运行的任务？\n这会打断 LLM 调用，可能导致部分 stage 不完整。')) return;
      try {
        const res = await fetch('/api/tasks/terminate-all', { method: 'POST' });
        if (res.ok) {
          const data = await res.json();
          alert(`已终止 ${data.terminated} 个任务，跳过 ${data.skipped} 个`);
          await this.refreshAllTasks();
        } else {
          alert('终止失败: HTTP ' + res.status);
        }
      } catch (e) {
        alert('终止失败: ' + e.message);
      }
    },

    async terminateOneTask(taskId) {
      if (!confirm('确定终止任务 ' + taskId + ' ？')) return;
      try {
        const res = await fetch(`/api/tasks/${taskId}/terminate`, { method: 'POST' });
        if (res.ok) {
          await this.refreshAllTasks();
        } else {
          const err = await res.json().catch(() => ({}));
          alert('终止失败: ' + (err.detail || res.status));
        }
      } catch (e) {
        alert('终止失败: ' + e.message);
      }
    },

    /**
     * 重新生成单个 bootstrap 任务（重跑该 run 中所有 failed stage）
     */
    async rerunOneBootstrapTask(task, forceAll = false) {
      if (!task.run_id) {
        alert('该任务没有关联的 workflow run，无法重跑。');
        return;
      }
      const label = forceAll ? '全部 stage（包括已成功的）' : '所有 failed stage';
      if (!confirm(`确定重新生成任务「${task.id}」吗？\n将重跑该 run 中${label}。`)) return;
      try {
        const res = await fetch(`/api/workflow/run/${task.run_id}/rerun-all?force_all=${forceAll}`, {
          method: 'POST',
        });
        const data = await res.json();
        if (data.status === 'submitted') {
          // 异步模式：轮询 task 直到完成
          const polledTask = await this._pollTask(data.task_id, {
            onProgress: () => this.refreshAllTasks(),
          });
          if (polledTask.status === 'completed' && polledTask.result) {
            const success = (polledTask.result.rerun_stages || []).length;
            const still = (polledTask.result.still_failed || []).length;
            alert(`重跑完成：成功 ${success} 个 stage，仍失败 ${still} 个。`);
            await this.refreshAllTasks();
          } else {
            alert('重跑失败: ' + (polledTask.error || 'unknown'));
          }
        } else if (data.status === 'ok') {
          // 兼容同步返回（旧版 API）
          const success = (data.rerun_stages || []).length;
          const still = (data.still_failed || []).length;
          alert(`重跑完成：成功 ${success} 个 stage，仍失败 ${still} 个。`);
          await this.refreshAllTasks();
        } else {
          alert('重跑失败: ' + (data.error || data.detail || 'unknown'));
        }
      } catch (e) {
        alert('重跑失败: ' + e.message);
      }
    },

    /**
     * 任务管理弹窗【重跑所有失败项 / 重跑全部设定】按钮
     * forceAll=false：只重跑失败/取消的项目
     * forceAll=true：重跑全部 bootstrap 项目（覆盖已成功的结果）
     */
    async rerunAllBootstrapTasks(forceAll = false) {
      const seenRunIds = new Set();
      const uniqueRuns = [];
      for (const t of this.allTasks) {
        if (t.task_type !== 'bootstrap' || !t.run_id || seenRunIds.has(t.run_id)) continue;
        if (!forceAll && !['failed', 'cancelled'].includes(t.status)) continue;
        seenRunIds.add(t.run_id);
        uniqueRuns.push(t);
      }
      if (uniqueRuns.length === 0) {
        alert(forceAll ? '没有可重跑的 bootstrap 项目。' : '没有需要重跑的失败项。');
        return;
      }
      const label = forceAll ? `${uniqueRuns.length} 个项目（包括已成功的 stage 也会重新生成）` : `${uniqueRuns.length} 个失败项目`;
      if (!confirm(`确定对 ${label}按顺序重新生成吗？`)) return;

      let totalSuccess = 0;
      let totalStillFailed = 0;
      for (let i = 0; i < uniqueRuns.length; i++) {
        const t = uniqueRuns[i];
        try {
          const res = await fetch(`/api/workflow/run/${t.run_id}/rerun-all?force_all=${forceAll}`, {
            method: 'POST',
          });
          const data = await res.json();
          if (data.status === 'submitted') {
            // 异步模式：轮询 task 直到完成
            const task = await this._pollTask(data.task_id, {
              onProgress: () => this.refreshAllTasks(),
            });
            if (task.status === 'completed' && task.result) {
              totalSuccess += (task.result.rerun_stages || []).length;
              totalStillFailed += (task.result.still_failed || []).length;
            } else {
              totalStillFailed += 1;
            }
          } else {
            // 兼容同步返回（旧版 API）
            if (data.status === 'ok') {
              totalSuccess += (data.rerun_stages || []).length;
              totalStillFailed += (data.still_failed || []).length;
            } else {
              totalStillFailed += 1;
            }
          }
        } catch (e) {
          console.error(`rerun-all for project ${t.id} failed:`, e);
          totalStillFailed += 1;
        }
      }
      alert(`重跑完成：成功 ${totalSuccess} 个 stage，仍失败 ${totalStillFailed} 个。`);
      await this.refreshAllTasks();
    },

    get activeTaskCount() {
      return this.allTasks.filter((t) => ['pending', 'running'].includes(t.status)).length;
    },

    get completedTaskCount() {
      return this.allTasks.filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status)).length;
    },

    /**
     * 是否有失败/取消的 bootstrap 任务（用于启用顶部"重新生成全部"按钮）
     */
    get hasFailedBootstrapTasks() {
      return this.allTasks.some(
        (t) => t.task_type === 'bootstrap' && ['failed', 'cancelled'].includes(t.status) && t.run_id
      );
    },

    /** 是否有任意 bootstrap 任务（用于启用"重跑全部设定"按钮） */
    get hasBootstrapTasks() {
      return this.allTasks.some(
        (t) => t.task_type === 'bootstrap' && t.run_id
      );
    },

    // ─── 项目删除 ───

    async deleteCurrentProject() {
      if (!this.currentProject) return;
      const p = this.currentProject;
      const ok = confirm(
        `⚠️ 即将永久删除项目《${p.title}》\n\n` +
        `将删除：所有章节 / 角色 / 世界观 / 伏笔 / 大纲 / 灵感 / 工作流记录\n` +
        `（Embedding 模型 / Chroma 向量索引 等公共资源不受影响）\n\n` +
        `此操作不可撤销！\n\n确定删除？`
      );
      if (!ok) return;
      try {
        const res = await fetch(`/api/projects/${p.id}`, { method: 'DELETE' });
        if (res.ok) {
          // 从本地列表移除
          this.projects = this.projects.filter((x) => x.id !== p.id);
          this.currentProject = null;
          this.chapters = [];
          this.characters = [];
          this.themes = [];
          this.foreshadowings = [];
          this.showProjectSettings = false;
          alert('项目已删除');
        } else {
          const err = await res.json().catch(() => ({}));
          alert('删除失败: ' + (err.detail || res.status));
        }
      } catch (e) {
        alert('删除失败: ' + e.message);
      }
    },

    // ─── 项目管理 ───
    async loadProjects() {
      try {
        const res = await fetch('/api/projects');
        this.projects = await res.json();
      } catch (e) { console.error(e); }
    },

    async createProject() {
      const title = prompt('请输入小说标题:');
      if (!title) return;
      try {
        const res = await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, description: '' }),
        });
        const project = await res.json();
        this.projects.unshift(project);
        this.openProject(project);
      } catch (e) { alert('创建失败: ' + e.message); }
    },

    // ─── 项目引导补全：新版创建流程 ───

    openCreateProjectModal() {
      // 重置表单
      this.newProjectForm = {
        title: '',
        chapter_word_count: 3,
        genre: '',
        genres: [],
        description: '',
        total_chapters: 100,
        theme: '',
        tone: '',
        style: '',
        pacing: '',
        premise: '',
        protagonist: '',
        antagonist: '',
        supporting: '',
        notes: '',
      };
      this.newGenreInput = '';
      this.showCreateProjectModal = true;
    },

    confirmCloseCreateProject() {
      const f = this.newProjectForm;
      const hasInput = (f.title || '').trim() || (f.description || '').trim() || (f.genre || '').trim();
      // 简单提示：仅有 4 必填之一有内容才二次确认
      if (hasInput) {
        if (!confirm('关闭后已输入的信息将丢失，确定要关闭吗？')) return;
      }
      this.showCreateProjectModal = false;
    },

    confirmCloseMissingFields() {
      // 检查用户是否已开始填写
      let hasInput = false;
      for (const q of this.missingQuestionnaire) {
        const el = document.getElementById('miss-' + q.id);
        if (el && (el.value || '').trim()) { hasInput = true; break; }
      }
      if (hasInput) {
        if (!confirm('关闭后已填写的内容将丢失，确定要关闭吗？')) return;
      }
      this.showMissingFieldsModal = false;
      this.missingFields = [];
      this.missingQuestionnaire = [];
    },

    _stripEmptyFields(obj) {
      // 把空字符串 / null 字段剔除，提交时只发有值的字段
      const out = {};
      for (const [k, v] of Object.entries(obj)) {
        if (v === '' || v === null || v === undefined) continue;
        out[k] = v;
      }
      return out;
    },

    async submitCreateProject(autoCommit = true) {
      // 前端二次校验 4 必填
      const f = this.newProjectForm;
      const missing = [];
      if (!(f.title || '').trim()) missing.push('title');
      if (!f.chapter_word_count) missing.push('chapter_word_count');
      // 题材：多选数组，至少 1 个
      if (!Array.isArray(f.genres) || f.genres.length === 0) missing.push('genre');
      if (!(f.description || '').trim()) missing.push('description');
      if (missing.length > 0) {
        // 前端检测到缺失，不发请求，直接弹补全 modal
        this.missingFields = missing;
        this.missingQuestionnaire = missing.map((field) => ({
          id: field,
          question: this._fieldLabel(field),
          type: this._fieldType(field),
          options: this._fieldOptions(field),
          required: true,
        }));
        this.showMissingFieldsModal = true;
        return;
      }

      // 把 genres 数组作为 genre 字段（兼容后端 list/str 双重支持）
      const payload = this._stripEmptyFields({
        ...f,
        genre: f.genres,  // 数组形式（后端会 join）
        auto_commit: autoCommit,
      });

      try {
        const res = await fetch('/api/projects', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json();

        if (data.status === 'missing_required') {
          // 后端二次校验发现缺失
          this.missingFields = data.missing || [];
          this.missingQuestionnaire = data.questionnaire || [];
          this.showMissingFieldsModal = true;
          return;
        }

        // 创建成功 + 启动 workflow
        this.showCreateProjectModal = false;
        this.projects.unshift({
          id: data.project_id,
          title: f.title,
          description: f.description,
        });
        this.openBootstrapWizard(data.project_id, data.run_id);
      } catch (e) {
        alert('创建失败: ' + e.message);
      }
    },

    _fieldLabel(field) {
      return {
        title: '请输入书名',
        chapter_word_count: '每章目标字数（千字）？',
        genre: '小说题材？',
        description: '用一句话描述你的故事',
      }[field] || field;
    },

    _fieldType(field) {
      if (field === 'title') return 'text';
      if (field === 'description') return 'textarea';
      return 'select';
    },

    _fieldOptions(field) {
      const o = this.createFormOptions;
      if (field === 'chapter_word_count') return o.chapter_word_options;
      if (field === 'genre') return o.genres;
      return [];
    },

    fillMissingFromModal() {
      // 从 missingFieldsModal 取值回写到 newProjectForm
      for (const q of this.missingQuestionnaire) {
        const fid = q.id;
        const el = document.getElementById('miss-' + fid);
        if (!el) continue;
        const val = el.value;
        if (val !== '' && val !== null) {
          if (fid === 'chapter_word_count') {
            this.newProjectForm.chapter_word_count = parseInt(val) || 0;
          } else {
            this.newProjectForm[fid] = val;
          }
        }
      }
      this.showMissingFieldsModal = false;
      this.missingFields = [];
      this.missingQuestionnaire = [];
      // 重新提交
      this.submitCreateProject(true);
    },

    // ─── 项目首页 AI 补全 banner ───
    bootstrapBanner: {
      visible: false,
      projectId: null,
      kind: '',           // 'in_flight' | 'awaiting_commit' | 'partial_failed'
      runId: null,
      message: '',
    },
    _bannerDismissed: new Set(),

    dismissBootstrapBanner() {
      this.bootstrapBanner.visible = false;
      if (this.bootstrapBanner.projectId) {
        this._bannerDismissed.add(this.bootstrapBanner.projectId);
      }
    },

    async _maybeShowBootstrapBanner(projectId) {
      // 如果用户已 dismiss 过这个项目，跳过
      if (this._bannerDismissed.has(projectId)) {
        this.bootstrapBanner.visible = false;
        return;
      }
      try {
        const res = await fetch(`/api/workflow/project/${projectId}/latest`);
        if (!res.ok) {
          this.bootstrapBanner.visible = false;
          return;
        }
        const data = await res.json();
        const status = data.status;
        const stages = data.stages || [];
        const results = data.stage_results || {};

        // 1) 已 committed → 完全完成，不显示
        if (status === 'committed') {
          this.bootstrapBanner.visible = false;
          return;
        }

        // 2) pending / running → 任务在进行中（包括用户杀了进程后 run 仍卡在这状态）
        if (status === 'pending' || status === 'running') {
          const total = stages.length;
          const done = stages.filter((s) =>
            ['ok', 'user_filled', 'skipped'].includes(s.status)
          ).length;
          this.bootstrapBanner = {
            visible: true,
            projectId,
            runId: data.run_id,
            kind: 'in_flight',
            message: `AI 补全进行中 ${done}/${total} 步。点击查看实时进度。`,
          };
          return;
        }

        // 3) completed → 所有 stage 跑过但未 commit（待用户确认入库）
        if (status === 'completed') {
          this.bootstrapBanner = {
            visible: true,
            projectId,
            runId: data.run_id,
            kind: 'awaiting_commit',
            message: 'AI 补全已完成，等待你确认写入数据库。',
          };
          return;
        }

        // 4) failed / partial → 部分失败
        // ⚠️ 修复反馈 bug：之前只看 status，没看实际 failed 数。
        //    有时 status='partial'/'failed' 但所有 stage 都 ok/user_filled/skipped
        //    （例如重跑成功后状态还没及时收敛），却仍错误地显示"部分失败"。
        //    这里加上 failedCount === 0 的兜底：→ 转为 awaiting_commit 路径。
        if (status === 'failed' || status === 'partial') {
          const failedCount = stages.filter((s) => s.status === 'failed').length;
          if (failedCount === 0) {
            // 实际没有失败 stage，降级为"待提交"提示（用户可点"写入数据库"入库）
            this.bootstrapBanner = {
              visible: true,
              projectId,
              runId: data.run_id,
              kind: 'awaiting_commit',
              message: 'AI 补全已完成，等待你确认写入数据库。',
            };
            return;
          }
          this.bootstrapBanner = {
            visible: true,
            projectId,
            runId: data.run_id,
            kind: 'partial_failed',
            message: `AI 补全部分失败（${failedCount} 个 stage）。可重跑失败项或继续。`,
          };
          return;
        }

        // 5) cancelled → 可能是服务重启/崩溃导致
        if (status === 'cancelled') {
          // 检查 stage_results 里的错误是否含"服务重启"
          const errMsgs = Object.values(data.stage_results || {})
            .map((s) => (typeof s === 'object' ? (s.error || '') : ''))
            .join(' ');
          const isAborted = /服务重启|重启|Restart|aborted|orphan/i.test(errMsgs);
          this.bootstrapBanner = {
            visible: true,
            projectId,
            runId: data.run_id,
            kind: isAborted ? 'aborted' : 'cancelled',
            message: isAborted
              ? 'AI 补全因服务重启被中断，可点击重新启动。'
              : 'AI 补全任务已被取消。',
          };
          return;
        }

        this.bootstrapBanner.visible = false;
      } catch (e) {
        console.warn('[Bootstrap banner] check failed:', e);
        this.bootstrapBanner.visible = false;
      }
    },

    // ─── Bootstrap Wizard ───

    async openBootstrapWizard(projectId, runId) {
      this.bootstrapWizard = {
        visible: true,
        projectId,
        runId,
        status: 'running',
        stages: [],
        pollHandle: null,
        errorMsg: '',
        startedAt: Date.now(),
        completedAt: null,
        rerunAllBusy: false,
        committing: false,
      };
      // 立即拉一次
      await this._pollBootstrapStatus();
      // 启动轮询（5s 一次，LLM 慢，给后端留够时间）
      this.bootstrapWizard.pollHandle = setInterval(
        () => this._pollBootstrapStatus(),
        5000
      );
      // 同时每秒 tick 一次：更新 running stage 的"已耗时"显示
      this.bootstrapWizard.tickHandle = setInterval(
        () => this._tickBootstrapElapsed(),
        1000
      );
    },

    async _pollBootstrapStatus() {
      const wiz = this.bootstrapWizard;
      if (!wiz.visible || !wiz.projectId) return;
      try {
        const res = await fetch(`/api/workflow/project/${wiz.projectId}/latest`);
        if (!res.ok) return;
        const data = await res.json();
        wiz.runId = data.run_id;
        wiz.stages = data.stages || [];
        const statuses = wiz.stages.map((s) => s.status);
        const allDone = statuses.every((s) =>
          ['ok', 'user_filled', 'skipped', 'failed'].includes(s)
        );
        const failedCount = wiz.stages.filter((s) => s.status === 'failed').length;
        if (data.status === 'committed') {
          wiz.status = 'committed';
          wiz.completedAt = Date.now();
          this._stopBootstrapPolling();
        } else if (data.status === 'failed' && failedCount > 0) {
          // run.status='failed' 且实际有 stage failed → 真正的失败
          wiz.status = 'failed';
          wiz.errorMsg = '有 stage 执行失败';
          this._stopBootstrapPolling();
        } else if (allDone && (data.status === 'completed' || failedCount === 0)) {
          // 后端已自动 commit（auto_commit=true），但前端保险起见也自动调一次 commit
          // （用户无感，不会卡住）
          wiz.status = 'committing';
          wiz.completedAt = Date.now();
          this._stopBootstrapPolling();
          // 自动提交：不需要用户点按钮
          this.commitBootstrap(true).then(() => {
            wiz.status = 'committed';
          }).catch((e) => {
            console.error('[Bootstrap auto-commit] failed:', e);
            // 自动 commit 失败时降级为 completed，让用户手动点（兼容旧数据）
            wiz.status = 'completed';
          });
        }
      } catch (e) {
        console.error('[Bootstrap poll] failed:', e);
      }
    },

    /**
     * 轮询一个 task_id 直到完成（completed / failed / cancelled）。
     * 用于异步 LLM 任务：rerun / rerun-all / review / generate / chapter_pipeline 等。
     *
     * @param {string} task_id - 后端 submit_llm_task 返回的 task.id
     * @param {object} opts
     * @param {number} [opts.interval=1500] 轮询间隔 ms
     * @param {number} [opts.timeout=600000] 总超时 ms（10 分钟）
     * @param {function} [opts.onProgress] 每次轮询回调 (task) => void
     * @returns {Promise<object>} 终态 task 对象
     */
    async _pollTask(task_id, opts = {}) {
      const interval = opts.interval || 2000;
      const timeout = opts.timeout || 600_000;
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

    /**
     * 每秒 tick：给所有 running stage 更新 _tick_now，触发 Alpine 重渲染耗时显示。
     * 用数组 push/pop 强制触发响应式（直接改属性 Alpine 不会响应）。
     */
    _tickBootstrapElapsed() {
      const wiz = this.bootstrapWizard;
      if (!wiz.visible || !wiz.stages) return;
      const hasRunning = wiz.stages.some(
        (s) => s.status === 'running' && s.started_at && !s.completed_at
      );
      if (!hasRunning) return;
      const now = Date.now();
      // 强制响应式：用新数组替换（Alpine 检测到 identity 变化）
      wiz.stages = wiz.stages.map((s) => {
        if (s.status === 'running' && s.started_at && !s.completed_at) {
          return { ...s, _tick_now: now };
        }
        return s;
      });
    },

    _stopBootstrapPolling() {
      const wiz = this.bootstrapWizard;
      if (wiz.pollHandle) {
        clearInterval(wiz.pollHandle);
        wiz.pollHandle = null;
      }
      if (wiz.tickHandle) {
        clearInterval(wiz.tickHandle);
        wiz.tickHandle = null;
      }
    },

    async rerunBootstrapStage(stageId) {
      const wiz = this.bootstrapWizard;
      if (!wiz.runId) return;
      if (!confirm(`确定重新生成 stage「${stageId}」吗？将覆盖之前的结果。`)) return;
      try {
        // 异步：后端立即返回 task_id
        const res = await fetch(`/api/workflow/run/${wiz.runId}/rerun`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stage_id: stageId }),
        });
        const data = await res.json();
        if (data.status !== 'submitted') {
          alert('重跑失败: ' + (data.error || JSON.stringify(data)));
          return;
        }
        // 轮询 task
        const task = await this._pollTask(data.task_id);
        if (task.status === 'completed') {
          // 重新拉 stage 状态
          await this._pollBootstrapStatus();
        } else {
          alert('重跑失败: ' + (task.error || 'unknown'));
        }
      } catch (e) {
        alert('重跑失败: ' + e.message);
      }
    },

    /**
     * 从「设定文档预览」面板（大纲/角色/世界观/伏笔/主题）触发的 stage 重跑。
     * 与 wizard 内的 rerunBootstrapStage 不同：这里从 currentProject 查最新 run，
     * 不依赖 wizard 是否打开。
     *
     * 重跑后自动 commit（因为用户已经在看文档了，希望立即看到新结果）。
     */
    async rerunBootstrapStageFromPanel(stageId) {
      if (!this.currentProject) {
        alert('请先打开一个项目');
        return;
      }
      // 取该 stage 的中文明称做提示
      const stageLabel = {
        'stage_1_base': '基础外推',
        'stage_2a_theme': '主旨/基调',
        'stage_2b_style': '文风/节奏',
        'stage_2c_world': '世界观',
        'stage_3a_protagonist': '主角',
        'stage_3b_antagonist': '反派',
        'stage_3c_supporting': '配角',
        'stage_3d_arcs': '角色弧光',
        'stage_4a_outline': '项目大纲',
        'stage_4b_foreshadow': '伏笔',
      }[stageId] || stageId;
      if (!confirm(`确定重新生成「${stageLabel}」吗？将覆盖之前的结果。`)) return;

      this.rerunStageBusy[stageId] = true;
      try {
        // 取最新 run_id
        const lr = await fetch(`/api/workflow/project/${this.currentProject.id}/latest`);
        if (!lr.ok) {
          alert('未找到 bootstrap 运行记录，请先完成设定生成。');
          return;
        }
        const runData = await lr.json();
        const runId = runData.run_id;
        if (runData.status === 'committed' || runData.status === 'failed') {
          // committed 后支持 rerun，failed 也支持
        }

        const res = await fetch(`/api/workflow/run/${runId}/rerun`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stage_id: stageId }),
        });
        const data = await res.json();
        if (data.status !== 'submitted') {
          alert('重跑失败: ' + (data.error || JSON.stringify(data)));
          return;
        }
        const task = await this._pollTask(data.task_id, { onProgress: () => this.refreshAllTasks() });
        if (task.status === 'completed') {
          // 自动 commit 让用户立即看到新结果
          await fetch(`/api/workflow/run/${runId}/commit`, { method: 'POST' });
          // 刷新当前项目的 bootstrapData（更新"设定文档预览"显示）
          await this._refreshBootstrapData();
          // 重新打开项目，让角色/世界观/伏笔等列表也刷新
          if (this.currentProject) {
            await this.openProject(this.currentProject);
          }
          // 弹个轻量提示
          this.toast?.(`✅ ${stageLabel} 已重新生成`);
        } else {
          alert('重跑失败: ' + (task.error || 'unknown'));
        }
      } catch (e) {
        alert('重跑失败: ' + e.message);
      } finally {
        this.rerunStageBusy[stageId] = false;
      }
    },

    /**
     * 「重新生成」按钮的提示文本。已 commit 的项目也允许 rerun（虽然要慎重）。
     * 仅当 stage 是 failed/cancelled 时才强烈推荐，否则只是「可重新生成」。
     */
    rerunStageBtnTitle(stageId) {
      return '点击用 LLM 重新生成该部分设定（会覆盖现有内容）';
    },

    /**
     * 「扩写 / 缩减大纲」浮层入口
     * 大纲面板 → 📈 扩写大纲 按钮 → 打开浮层
     *
     * 浮层展示 4 个状态数字:
     *   原目标总章节数、原已生成大纲章数、计划向后扩展章数、新目标章节总数
     * 其中"计划向后扩展"和"新目标章节总数"双向联动。
     */
    openExtendOutlineModal() {
      if (!this.currentProject) return;
      this.extendOutlineOriginalTotal = this.currentProject.total_chapters || 0;
      // 已生成大纲章数:从 bootstrapData.outline.chapter_outlines 算
      let generated = 0;
      if (this.bootstrapData && this.bootstrapData.outline
          && Array.isArray(this.bootstrapData.outline.chapter_outlines)) {
        generated = this.bootstrapData.outline.chapter_outlines.length;
      }
      this.extendOutlineGenerated = generated;
      // 默认建议: 扩写 + 100 (无变化)
      this.extendOutlineExtendBy = 100;
      this.extendOutlineNewTotal = generated + 100;
      this.extendOutlineArchitecture = true;
      this.extendOutlineBusy = false;
      this.showExtendOutlineModal = true;
    },

    extendOutlineBtnTitle() {
      return '基于已有大纲扩写更多章节,或缩减小说篇幅';
    },

    /**
     * 双向联动输入:
     *   - 用户改 "计划向后扩展" → 自动算 newTotal = generated + extendBy
     *   - 用户改 "新目标章节总数" → 自动算 extendBy = newTotal - generated
     */
    onExtendOutlineChange(which, rawValue) {
      // 容错:空 / 非数字
      const v = parseInt(rawValue);
      if (isNaN(v)) return;
      if (which === 'extendBy') {
        this.extendOutlineExtendBy = v;
        this.extendOutlineNewTotal = this.extendOutlineGenerated + v;
      } else if (which === 'newTotal') {
        // newTotal 不能 < 0,夹回 0
        this.extendOutlineNewTotal = Math.max(0, v);
        this.extendOutlineExtendBy = this.extendOutlineNewTotal - this.extendOutlineGenerated;
      }
    },

    /**
     * 提交按钮可用性:
     *   - 无变化(0)  → 不让提交,提示关闭
     *   - 扩写 (>0)  → 可提交
     *   - 缩减 (<0)  → 可提交,但 newTotal 必须 >= 0
     */
    canSubmitExtendOutline() {
      if (this.extendOutlineBusy) return false;
      if (this.extendOutlineExtendBy === 0) return false;  // 0 = 无变化
      if (this.extendOutlineNewTotal < 0) return false;
      return true;
    },

    /**
     * 确认扩写/缩减:调后端 extend-outline API
     * 异步模式: 拿到 task_id 后轮询, 完成后刷新项目数据 + bootstrapData
     */
    async confirmExtendOutline() {
      if (!this.currentProject) return;
      const newTotal = this.extendOutlineNewTotal;
      const generated = this.extendOutlineGenerated;
      const diff = this.extendOutlineExtendBy;  // >0 扩写, <0 缩减

      // 安全检查
      if (newTotal < 0) {
        alert('新目标章节总数不能 < 0');
        return;
      }
      if (diff === 0) {
        // 0 = 无变化,直接关
        this.showExtendOutlineModal = false;
        return;
      }

      // 二次确认
      const isExpand = diff > 0;
      const confirmMsg = isExpand
        ? `确定把项目「${this.currentProject.title}」的大纲从 ${generated} 章扩到 ${newTotal} 章吗？\n\n` +
          `• 已有章节:不会修改\n` +
          `• 新增章节: ${diff} 章\n` +
          `• 架构层(分卷/剧情线/四幕): ${this.extendOutlineArchitecture ? '同步扩写' : '保留原架构'}`
        : `确定把项目「${this.currentProject.title}」的大纲从 ${generated} 章缩减到 ${newTotal} 章吗？\n\n` +
          `• 尾部删除 ${Math.abs(diff)} 章\n` +
          `• 保留的章节(1-${newTotal})不会修改\n` +
          `• 警告:已生成的对应章节细纲/伏笔也会被清理`;
      if (!confirm(confirmMsg)) return;

      this.extendOutlineBusy = true;
      this.showExtendOutlineModal = false;
      try {
        const res = await fetch(
          `/api/workflow/project/${this.currentProject.id}/extend-outline` +
          `?target_chapters=${newTotal}&extend_architecture=${this.extendOutlineArchitecture}`,
          { method: 'POST' }
        );
        const data = await res.json();

        // 无变化:直接同步返回
        if (data.status === 'ok' && !data.task_id) {
          await this._afterExtendOutline(data, isExpand);
          return;
        }

        // 已提交任务
        if (data.status === 'submitted' && data.task_id) {
          const action = isExpand ? '扩写' : '缩减';
          alert(
            `⏳ 大纲${action}任务已提交\n\n` +
            `${data.description}\n\n` +
            `任务 ID: ${data.task_id}\n` +
            `可在「任务管理」中查看实时进度。\n` +
            `完成后会自动刷新项目数据。`
          );
          // 刷新任务列表(让任务管理面板显示)
          if (this.refreshAllTasks) this.refreshAllTasks();
          // 自动打开任务管理面板,用户能看到进度
          this.showTaskManager = true;
          // 轮询任务直到完成
          const task = await this._pollTask(data.task_id, {
            onProgress: () => {
              if (this.refreshAllTasks) this.refreshAllTasks();
            },
          });
          if (task.status === 'completed' && task.result) {
            await this._afterExtendOutline(task.result, isExpand);
          } else if (task.status === 'failed') {
            alert('操作失败: ' + (task.error || 'unknown'));
          }
          return;
        }

        // 直接失败
        alert('操作失败: ' + (data.error || JSON.stringify(data)));
      } catch (e) {
        console.error('[confirmExtendOutline] failed:', e);
        alert('操作失败: ' + e.message);
      } finally {
        this.extendOutlineBusy = false;
      }
    },

    /**
     * 扩写/缩减完成后:弹结果 + 刷新项目数据 + 重新加载 bootstrapData
     */
    async _afterExtendOutline(data, isExpand) {
      if (!this.currentProject) return;
      if (data.status !== 'ok') {
        alert('操作失败: ' + (data.error || JSON.stringify(data)));
        return;
      }
      const action = isExpand ? '扩写' : '缩减';
      // 弹结果统计
      if (isExpand) {
        alert(
          `✅ 大纲${action}完成!\n\n` +
          `原 ${data.old_total} 章 → 新 ${data.new_total} 章\n` +
          `新增 chapter_outlines: ${data.added_chapters} 章\n` +
          `新增 volumes: ${(data.added_volumes || []).length} 个\n` +
          `新增 plot_lines: ${(data.added_plot_lines || []).length} 条\n` +
          `新增 acts: ${(data.added_acts || []).length} 个`
        );
      } else {
        alert(
          `✅ 大纲${action}完成!\n\n` +
          `原 ${data.old_total} 章 → 新 ${data.new_total} 章\n` +
          `删除尾部 ${data.removed_chapters || 0} 章\n` +
          `保留 ${data.kept_chapters || 0} 章`
        );
      }
      // 刷新项目数据(后端 Project.total_chapters 已更新)
      // 关键: 必须用后端返回的最新数据刷新 currentProject, 否则前端还显示旧 total_chapters
      try {
        const projRes = await fetch(`/api/projects/${this.currentProject.id}`);
        if (projRes.ok) {
          const freshProj = await projRes.json();
          // 更新 currentProject
          Object.assign(this.currentProject, freshProj);
          // 重新计算字数
          this._recalcProjectWordCount();
        }
      } catch (e) {
        console.warn('[afterExtendOutline] fetch project failed:', e);
      }
      // 重新拉 bootstrapData(让大纲面板显示新 chapter_outlines)
      await this._refreshBootstrapData();
      // 重新加载章节列表(如果扩写到 > existing, 不会自动创建 Chapter; 但要刷新 total_chapters)
      // 如果是缩减, 也不会删 Chapter(只是删 chapter_outlines 元数据)
      await this.loadChapters(this.currentProject.id);
      console.log(
        `[afterExtendOutline] ${action} 完成:`,
        `${data.old_total} → ${data.new_total},`,
        `kept=${data.kept_chapters || '-'}, added=${data.added_chapters || '-'}, removed=${data.removed_chapters || '-'}`
      );
    },

    /**
     * 重新拉取 bootstrapData 用于刷新"设定文档预览"界面。
     */
    async _refreshBootstrapData() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/workflow/project/${this.currentProject.id}/bootstrap-data`);
        if (res.ok) {
          this.bootstrapData = await res.json();
        }
      } catch (e) {
        console.warn('[refreshBootstrapData] failed:', e);
      }
    },

    /**
     * 计算 wizard 当前"缺失项"数量：failed / cancelled / 未开始的 stage 总数。
     * 保留以兼容遗留调用。
     */
    bootstrapMissingCount() {
      const wiz = this.bootstrapWizard;
      if (!wiz || !wiz.stages) return 0;
      return wiz.stages.filter(
        (s) => !['ok', 'user_filled', 'skipped'].includes(s.status)
      ).length;
    },

    /**
     * 一键重跑所有未完成 stage（按依赖顺序串行）
     * 异步：提交后立即返回，后端跑完会刷 stage 状态
     *
     * @param {boolean} [forceAll=false]
     *   - false（默认）：只重跑 failed/cancelled/未开始的 stage（缺失项）
     *   - true：重跑全部 stage（包括已成功的）（所有项）
     */
    async rerunBootstrapAllStages(forceAll = false) {
      const wiz = this.bootstrapWizard;
      if (!wiz.runId) return;
      const missingCount = this.bootstrapMissingCount();
      if (!forceAll && missingCount === 0) {
        alert('当前没有未完成的 stage，无需重跑。');
        return;
      }
      const msg = forceAll
        ? `确定【重跑所有项】吗？\n将覆盖全部已成功的 stage（包括用户手填的项会保留）。\n生成所有 stage 预计耗时较长。`
        : `确定重新生成 ${missingCount} 个【缺失项】吗？\n（按依赖顺序串行重跑：已成功的不会重复跑）`;
      if (!confirm(msg)) return;

      wiz.rerunAllBusy = true;
      try {
        // 异步：后端立即返回 task_id
        const res = await fetch(`/api/workflow/run/${wiz.runId}/rerun-all?force_all=${forceAll}`, {
          method: 'POST',
        });
        const data = await res.json();
        if (data.status !== 'submitted') {
          alert('重跑失败: ' + (data.error || JSON.stringify(data)));
          return;
        }
        // 轮询：每个 stage 状态会随 _pollBootstrapStatus 实时刷新
        const task = await this._pollTask(data.task_id, {
          onProgress: () => this._pollBootstrapStatus(),
        });
        if (task.status === 'completed') {
          // ⚠️ 后端 _refresh_inmem_task_from_run 会覆盖 task.result（变成 stage_results / run_status），
          //     原 rerun_stages / still_failed 拿不到。这里直接从 wiz.stages 重新统计。
          const stages = wiz.stages || [];
          let success = 0, stillFailed = 0, skipped = 0;
          for (const s of stages) {
            if (s.status === 'ok') success++;
            else if (s.status === 'failed' || s.status === 'cancelled') stillFailed++;
            else if (s.status === 'skipped') skipped++;
            // user_filled 不计入（用户手填，本就不需重跑）
          }
          // 也参考后端 task.result 里的 run_status 判断总体状态
          const runStatus = (task.result && task.result.run_status) || '';
          const statusNote = runStatus === 'completed' ? '\n本次全部完成（可点击“写入数据库”入库）。'
                           : runStatus === 'partial' ? '\n本次部分完成：仍有 stage 失败。'
                           : runStatus === 'failed' ? '\n本次总体失败。'
                           : '';
          alert(`重跑完成：成功 ${success} 个，仍失败 ${stillFailed} 个，跳过 ${skipped} 个。${statusNote}`);
          await this._pollBootstrapStatus();
        } else if (task.status === 'failed') {
          alert('重跑失败: ' + (task.error || 'unknown'));
        } else {
          alert('重跑被取消: ' + (task.error || 'cancelled'));
        }
      } catch (e) {
        alert('重跑失败: ' + e.message);
      } finally {
        wiz.rerunAllBusy = false;
      }
    },

    async commitBootstrap(auto = false) {
      const wiz = this.bootstrapWizard;
      if (!wiz.runId) return;
      // 手动点击时守护；auto 触发时允许连续（如轮询里调用）
      if (!auto && wiz.committing) return;
      wiz.committing = true;
      try {
        const res = await fetch(`/api/workflow/run/${wiz.runId}/commit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        const data = await res.json();
        if (data.status === 'committed' || data.status === 'already_committed') {
          wiz.status = 'committed';
          wiz.completedAt = Date.now();
          this._stopBootstrapPolling();
          // 刷新当前项目数据
          if (this.currentProject) {
            await this.openProject(this.currentProject);
          }
          // 自动提交不弹 alert（用户体验流畅），手动点击才提示
          if (!auto) {
            const summary = data.summary || {};
            const msg = '✅ AI 补全已成功写入数据库！\n\n' +
              `主题: ${summary.themes || 0} 条\n` +
              `世界观: ${summary.world_entries || 0} 条\n` +
              `角色: ${summary.characters || 0} 个\n` +
              `角色关系: ${summary.relations || 0} 条\n` +
              `角色弧光: ${summary.arcs || 0} 条\n` +
              `伏笔: ${summary.foreshadowings || 0} 条\n\n` +
              '点确定后可进入写作台开始创作！';
            alert(msg);
          }
        } else {
          // 失败时：auto 模式让 wizard 退回 completed 等用户手动重试；手动模式弹 alert
          if (auto) {
            throw new Error(data.error || 'commit failed');
          }
          alert('提交失败: ' + (data.error || 'unknown'));
        }
      } finally {
        wiz.committing = false;
      }
    },

    closeBootstrapWizard() {
      this._stopBootstrapPolling();
      this.bootstrapWizard.visible = false;
      // 跳转到项目首页
      if (this.bootstrapWizard.projectId) {
        const proj = this.projects.find((p) => p.id === this.bootstrapWizard.projectId);
        if (proj) this.openProject(proj);
      }
    },

    bootstrapStageIcon(status) {
      return {
        pending: '⏳',
        running: '🔄',
        ok: '✅',
        user_filled: '👤',
        skipped: '⏭️',
        failed: '❌',
      }[status] || '⏳';
    },

    /**
     * 格式化每个 stage 的耗时显示：
     * - 未开始 → ''
     * - 运行中 → '已耗时 12.3s'（实时刷新）
     * - 已完成 → '耗时 8.1s'（最终值）
     */
    formatStageElapsed(stage) {
      if (!stage) return '';
      // 防御：started_at 缺失、不是数字、或看起来是 epoch 早期（<= 0 / 太早）
      // → 不显示耗时，避免出现 "494417h" 之类的鬼数字
      const startSec = Number(stage.started_at);
      if (!Number.isFinite(startSec) || startSec <= 0 || startSec < 1_000_000_000) {
        return '';
      }
      const startMs = startSec * 1000;  // 后端 time.time() 是秒
      let elapsedMs;
      let label;
      if (stage.completed_at) {
        const endSec = Number(stage.completed_at);
        if (!Number.isFinite(endSec) || endSec < startSec) return '';
        elapsedMs = endSec * 1000 - startMs;
        label = '耗时';
      } else if (stage.status === 'running') {
        const now = stage._tick_now || Date.now();
        elapsedMs = now - startMs;
        label = '已耗时';
      } else {
        // 终态但既没 completed_at 也不在 running（防御性兜底）→ 不显示
        return '';
      }
      // 防御：elapsedMs 异常（NaN / 负数 / 超过 30 天）→ 不显示
      if (!Number.isFinite(elapsedMs) || elapsedMs < 0 || elapsedMs > 30 * 24 * 3600 * 1000) {
        return '';
      }
      // 自适应单位：< 60s 用秒，< 60min 用 Xm Ys，>= 1h 用 Xh Ym
      const totalSec = elapsedMs / 1000;
      let text;
      if (totalSec < 60) {
        text = `${totalSec.toFixed(1)}s`;
      } else if (totalSec < 3600) {
        const m = Math.floor(totalSec / 60);
        const s = totalSec - m * 60;
        text = `${m}m ${s.toFixed(0)}s`;
      } else {
        const h = Math.floor(totalSec / 3600);
        const m = Math.floor((totalSec - h * 3600) / 60);
        text = `${h}h ${m}m`;
      }
      return ` · ${label} ${text}`;
    },

    bootstrapProgressPct() {
      const wiz = this.bootstrapWizard;
      if (!wiz.stages || wiz.stages.length === 0) return 0;
      const done = wiz.stages.filter((s) =>
        ['ok', 'user_filled', 'skipped'].includes(s.status)
      ).length;
      return Math.round((done / wiz.stages.length) * 100);
    },

    bootstrapDurationText() {
      const wiz = this.bootstrapWizard;
      if (!wiz.startedAt) return '';
      const end = wiz.completedAt || Date.now();
      const sec = Math.round((end - wiz.startedAt) / 1000);
      if (sec < 60) return `${sec} 秒`;
      return `${Math.floor(sec / 60)} 分 ${sec % 60} 秒`;
    },

    async openProject(project) {
      this.currentProject = { ...project };
      this.activePanel = 'writing';
      this.outlineSubPanel = 'overview';
      this._saveLastView();
      await Promise.all([
        this.loadChapters(project.id),
        this.loadCharacters(project.id),
        this.loadThemes(project.id),
        this.loadForeshadowings(project.id),
        this.loadCharacterArcs(project.id),
        this.loadCharacterRelations(project.id),
        this.loadConsistencyReport(project.id),
        this.loadChapterOutlines(project.id),
        this.loadPlotPoints(),
        // 设定预览数据：失败不阻塞打开项目（catch 静默）
        this.loadBootstrapData(project.id).catch((e) => {
          console.warn('[BootstrapData] load failed (silently ignored):', e);
        }),
      ]);
      // 重新计算项目总字数 = 已写章节字数总和
      // (后端 Project.word_count 不实时累加,前端在打开项目时算一次,
      // 之后每次 saveChapter 时增量更新)
      this._recalcProjectWordCount();
      // 检查是否需要显示 AI 补全 banner
      this._maybeShowBootstrapBanner(project.id);
      // 启动 banner 轮询（让 banner 在 rerun 后能自动刷新状态）
      this._startBannerPolling(project.id);
    },

    /**
     * 重新计算项目总字数 = 已写章节字数总和,并更新 currentProject.word_count。
     * 用于侧边栏"字数进度"显示(已写 / 目标总字数)。
     */
    _recalcProjectWordCount() {
      if (!this.chapters || !this.currentProject) return;
      const total = this.chapters.reduce((s, c) => s + (c.word_count || 0), 0);
      this.currentProject.word_count = total;
    },

    /**
     * 从 bootstrapData.characters 中提取所有 AI 生成的"主角/反派/配角"，
     * 统一为一个数组供【角色】页签下的"🤖 AI 生成角色"区块渲染。
     *
     * 数据来源：bootstrapData.characters.protagonist / antagonist / supporting
     * 返回：扁平数组，每项形如 { name, role, profile, description }
     */
    bootstrapAiCharacters() {
      const bd = this.bootstrapData;
      if (!bd || !bd.characters) return [];
      const c = bd.characters;
      const out = [];
      // 主角（单对象）
      if (c.protagonist && (c.protagonist.name || c.protagonist.profile)) {
        out.push({
          name: c.protagonist.name || '主角',
          role: c.protagonist.role || '主角',
          profile: c.protagonist.profile || {},
          description: c.protagonist.description || '',
        });
      }
      // 反派（单对象）
      if (c.antagonist && (c.antagonist.name || c.antagonist.profile)) {
        out.push({
          name: c.antagonist.name || '反派',
          role: c.antagonist.role || '反派',
          profile: c.antagonist.profile || {},
          description: c.antagonist.description || '',
        });
      }
      // 配角（数组）
      const supporting = Array.isArray(c.supporting) ? c.supporting : [];
      for (const s of supporting) {
        if (s && (s.name || s.profile)) {
          out.push({
            name: s.name || '配角',
            role: s.role || '配角',
            profile: s.profile || {},
            description: s.description || '',
          });
        }
      }
      return out;
    },

    /**
     * 合并 AI 生成 + 手动添加的角色为统一列表。
     * 排序规则：主角 → 反派 → 配角 → 龙套（按 role 字段）
     * 同 role 内按 name 排序。
     * 每项携带 _source 标记 ('ai' / 'manual')，供模板显示 AI 角标。
     */
    mergedCharacters() {
      const aiChars = this.bootstrapAiCharacters().map((c) => ({
        ...c,
        _source: 'ai',
        _id: c.name,  // 临时 id 用 name 区分
      }));
      const manualChars = (this.characters || []).map((c) => ({
        ...c,
        _source: 'manual',
        _id: c.id,
        name: c.name,
        role: c.role || '配角',
        profile: c.profile || {},
        description: c.description || '',
      }));
      // 去重：手动角色如果和 AI 角色同名,优先保留手动（用户编辑过）
      const aiNames = new Set(aiChars.map((c) => c.name));
      const merged = [
        ...manualChars,
        ...aiChars.filter((c) => !aiNames.has(c.name) || !manualChars.find((m) => m.name === c.name)),
      ];
      // 主角置顶
      const roleOrder = { '主角': 0, '反派': 1, '配角': 2, '龙套': 3 };
      merged.sort((a, b) => {
        const ra = roleOrder[a.role] ?? 9;
        const rb = roleOrder[b.role] ?? 9;
        if (ra !== rb) return ra - rb;
        return (a.name || '').localeCompare(b.name || '', 'zh-CN');
      });
      return merged;
    },

    /**
     * 从 bootstrapData.characters.relations 中提取 AI 生成的关系矩阵。
     * 返回数组，每项形如 { from, to, type, description, strength, status }。
     */
    bootstrapAiRelations() {
      const bd = this.bootstrapData;
      if (!bd || !bd.characters) return [];
      const rels = bd.characters.relations;
      return Array.isArray(rels) ? rels : [];
    },

    /**
     * 概述 AI 生成的大纲（用于"🤖 AI 生成大纲"区块右上角的 hint 文本）。
     * 例："概要 432 字 + 3 剧情线 + 4 幕结构 + 节奏 1 段"
     */
    bootstrapAiOutlineSummary() {
      const o = this.bootstrapData && this.bootstrapData.outline;
      if (!o) return '';
      const parts = [];
      if (o.outline_text) parts.push(`概要 ${o.outline_text.length} 字`);
      if (Array.isArray(o.plot_lines) && o.plot_lines.length) {
        parts.push(`${o.plot_lines.length} 剧情线`);
      }
      const acts = o.structure && Array.isArray(o.structure.acts) ? o.structure.acts : [];
      if (acts.length) parts.push(`${acts.length} 幕结构`);
      if (o.pacing_notes) parts.push('节奏规划');
      return parts.join(' · ');
    },

    /**
     * 估算的总章节数。优先级：
     *   1. currentProject.total_chapters（Project 表，写入后才有）
     *   2. bootstrapData.base.total_chapters（AI 在 stage_1_base 推导的值，跑过引导补全就有）
     *   3. null（都没有）
     *
     * 用于大纲页面"预设总章节"的兜底显示：用户看到的"30 章"不能因为
     * Project.total_chapters 没写就显示"未设定"，而忽略 AI 已经算出来的数字。
     */
    effectiveTotalChapters() {
      const cp = this.currentProject;
      if (cp && cp.total_chapters) return cp.total_chapters;
      const base = this.bootstrapData && this.bootstrapData.base;
      if (base && base.total_chapters) return base.total_chapters;
      return null;
    },

    /**
     * 估算的总字数（千字）。类似 effectiveTotalChapters：从 base.est_total_words 兜底。
     */
    effectiveEstTotalWords() {
      const cp = this.currentProject;
      if (cp && cp.target_word_count) {
        // Project 表只有每章字数 → 乘以章节数
        const chs = this.effectiveTotalChapters();
        if (chs && cp.target_word_count) return chs * cp.target_word_count;
        return cp.target_word_count;
      }
      const base = this.bootstrapData && this.bootstrapData.base;
      if (base && base.est_total_words) return base.est_total_words;
      return null;
    },

    /**
     * 提取 AI 生成的主题（来自 bootstrapData.theme）
     * 返回 { theme, tone } 或空对象。
     */
    bootstrapAiTheme() {
      const t = this.bootstrapData && this.bootstrapData.theme;
      return t && (t.theme || t.tone) ? t : null;
    },

    /**
     * 提取 AI 生成的伏笔列表（按周期分组）
     * 返回 { "短周期": [...], "中周期": [...], "长周期": [...], "未分类": [...] } 或空对象。
     */
    bootstrapAiForeshadowings() {
      const f = this.bootstrapData && this.bootstrapData.foreshadowings;
      if (!f || !f.by_period) return null;
      // 过滤掉空的周期，只保留有内容的
      const result = {};
      for (const [period, items] of Object.entries(f.by_period)) {
        if (Array.isArray(items) && items.length > 0) {
          result[period] = items;
        }
      }
      return Object.keys(result).length > 0 ? result : null;
    },

    /**
     * 加载 bootstrap 设定数据（从 /api/workflow/project/{id}/bootstrap-data）。
     * 用于"设定预览"面板：把 stage_results 整理成可读结构。
     * 调用失败（如项目没有 bootstrap run）→ 静默忽略，UI 仍可正常使用。
     */
    async loadBootstrapData(projectId) {
      this.bootstrapDataLoading = true;
      try {
        const res = await fetch(`/api/workflow/project/${projectId}/bootstrap-data`);
        if (!res.ok) {
          // 404 = 没有 run（项目没跑过 bootstrap）→ 静默置空
          this.bootstrapData = null;
          return;
        }
        this.bootstrapData = await res.json();
      } catch (e) {
        this.bootstrapData = null;
        throw e;  // 让调用方决定是否需要提示用户
      } finally {
        this.bootstrapDataLoading = false;
      }
    },

    /**
     * 启动 banner 轮询：每 5s 重新评估 banner 状态
     * 用户进入项目页时启动，离开时停止
     */
    _startBannerPolling(projectId) {
      this._stopBannerPolling();
      this._bannerPollHandle = setInterval(async () => {
        // 只有当前在这个项目页时才轮询（避免污染）
        if (this.currentProject && this.currentProject.id === projectId) {
          await this._maybeShowBootstrapBanner(projectId);
        } else {
          this._stopBannerPolling();
        }
      }, 5000);
    },

    _stopBannerPolling() {
      if (this._bannerPollHandle) {
        clearInterval(this._bannerPollHandle);
        this._bannerPollHandle = null;
      }
    },

    backToHome() {
      // 关闭 banner（避免在 home 页面也显示）
      this.bootstrapBanner.visible = false;
      this.currentProject = null;
      this.currentChapter = null;
      this.activePanel = 'writing';
      this.chapters = [];
      this.characters = [];
      this.themes = [];
      this.foreshadowings = [];
      this.characterArcs = [];
      this.characterRelations = [];
      this.chapterOutlines = [];
      this.plotPoints = [];
      this.consistencyReport = null;
      // 停掉 banner 轮询
      this._stopBannerPolling();
      // 刷新项目列表（确保最新）
      this.loadProjects();
    },

    // ─── 灵感主界面 ───

    async openInspirationHub() {
      this.showInspirationHub = true;
      this.inspLoading = true;
      await Promise.all([
        this.loadInspirationHub(),
        this.loadInspirationTags(),
        this.loadInspirationSources(),
        this.loadInspirationCount(),
      ]);
      this.inspLoading = false;
    },

    async loadInspirationHub() {
      try {
        const params = new URLSearchParams();
        if (this.inspSearch.q) params.set('q', this.inspSearch.q);
        if (this.inspSearch.tag) params.set('tag', this.inspSearch.tag);
        if (this.inspSearch.source) params.set('source', this.inspSearch.source);
        if (this.inspSearch.includeConsumed) params.set('include_consumed', 'true');
        // 范围
        if (this.inspSearch.projectScope === 'global') {
          params.set('project_id', '0');
        } else if (this.inspSearch.projectScope === 'current' && this.currentProject) {
          params.set('project_id', String(this.currentProject.id));
        } else if (this.inspSearch.projectScope === 'all') {
          params.set('project_id', '-1');
        }
        const res = await fetch('/api/inspirations?' + params);
        if (res.ok) this.inspirations = await res.json();
      } catch (e) { console.error('loadInspirationHub:', e); }
    },

    async loadInspirationTags() {
      try {
        // 全局标签云（不指定 project_id）
        const res = await fetch('/api/inspirations/tags');
        if (res.ok) this.inspTagCloud = await res.json();
      } catch (e) {}
    },

    async loadInspirationSources() {
      try {
        const res = await fetch('/api/inspirations/sources');
        if (res.ok) this.inspSources = await res.json();
      } catch (e) {}
    },

    async loadInspirationCount() {
      try {
        const res = await fetch('/api/inspirations?project_id=0');
        if (res.ok) {
          const list = await res.json();
          this.inspirationCount = list.length;
        }
      } catch (e) {}
    },

    openInspirationEditor(insp = null) {
      if (insp) {
        this.editingInspiration = {
          id: insp.id,
          title: insp.title || '',
          content: insp.content || '',
          source: insp.source || '',
          tagInput: (insp.tags || []).join(', '),
          project_id: insp.project_id || null,
        };
      } else {
        this.editingInspiration = {
          id: null,
          title: '',
          content: '',
          source: '',
          tagInput: '',
          project_id: null,
        };
      }
      this.showInspirationEditor = true;
    },

    async saveInspirationFromEditor() {
      const e = this.editingInspiration;
      if (!e.content || !e.content.trim()) {
        alert('内容不能为空');
        return;
      }
      const tags = (e.tagInput || '').split(',').map((t) => t.trim()).filter(Boolean);
      const payload = {
        title: e.title,
        content: e.content,
        source: e.source,
        tags,
        project_id: e.project_id,
      };
      try {
        const url = e.id ? `/api/inspirations/${e.id}` : '/api/inspirations';
        const method = e.id ? 'PUT' : 'POST';
        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (res.ok) {
          this.showInspirationEditor = false;
          await this.openInspirationHub();
        } else {
          alert('保存失败: ' + res.status);
        }
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    async deleteInspirationById(inspId) {
      if (!confirm('确定删除此灵感？此操作不可撤销。')) return;
      try {
        const res = await fetch(`/api/inspirations/${inspId}`, { method: 'DELETE' });
        if (res.ok) await this.openInspirationHub();
      } catch (e) { alert('删除失败: ' + e.message); }
    },

    // ─── 以灵感创建项目 ───

    openCreateProjectFromInspiration(insp) {
      this.inspForCreateProject = insp;
      this.createFromInspForm = {
        title: insp.title || `灵感 #${insp.id} 衍生项目`,
        chapter_word_count: 3,
        genre: insp.tags?.[0] || '其他',
        description: insp.content.substring(0, 200),
      };
      this.showCreateFromInspiration = true;
    },

    async submitCreateProjectFromInspiration() {
      const insp = this.inspForCreateProject;
      if (!insp) return;
      const f = this.createFromInspForm;
      try {
        const res = await fetch(`/api/inspirations/${insp.id}/create-project`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: f.title,
            chapter_word_count: f.chapter_word_count,
            genre: f.genre,
            description: f.description,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          this.showCreateFromInspiration = false;
          this.showInspirationHub = false;
          alert(`已创建项目《${f.title}》！开始引导补全...`);
          // 跳转到项目 + 打开 wizard
          if (data.run_id) {
            this.openBootstrapWizard(data.project_id, data.run_id);
          } else {
            // 兜底：直接进项目
            await this.loadProjects();
            const proj = this.projects.find((p) => p.id === data.project_id);
            if (proj) await this.openProject(proj);
          }
        } else {
          const err = await res.json().catch(() => ({}));
          alert('创建失败: ' + (err.detail || res.status));
        }
      } catch (e) { alert('创建失败: ' + e.message); }
    },

    // ─── 融合灵感到项目 ───

    async openFuseInspiration(insp) {
      this.inspForFuse = insp;
      this.fuseForm = { project_id: this.currentProject?.id || '', target: 'outline', chapterOrder: null, note: '' };
      // 准备章节下拉选项
      this.chapterSelectOptions = (this.chapters || []).map((c) => c.order);
      this.showFuseInspiration = true;
    },

    async submitFuseInspiration() {
      const insp = this.inspForFuse;
      if (!insp) return;
      const f = this.fuseForm;
      if (!f.project_id) { alert('请选择目标项目'); return; }
      // 把 chapter + chapterOrder 拼成 target
      let target = f.target;
      if ((f.target === 'chapter' || f.target === 'chapter_content') && f.chapterOrder != null) {
        target = `${f.target === 'chapter' ? 'chapter' : 'chapter_content'}:${f.chapterOrder}`;
      }
      try {
        const res = await fetch(`/api/inspirations/${insp.id}/fuse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: f.project_id,  // 8位 hex string,不要 parseInt
            target,
            note: f.note,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          this.showFuseInspiration = false;
          this.showInspirationHub = false;
          alert(`✅ ${data.message}\n（灵感已标记为"已融合"）`);
          // 重新打开 hub 看到最新状态
          await this.openInspirationHub();
          // 如果融合到当前项目，刷新项目数据
          if (this.currentProject && data.project_id === this.currentProject.id) {
            await this.openProject(this.currentProject);
          }
        } else {
          const err = await res.json().catch(() => ({}));
          alert('融合失败: ' + (err.detail || res.status));
        }
      } catch (e) { alert('融合失败: ' + e.message); }
    },

    // ─── 题材 ───

    async loadGenres() {
      try {
        const res = await fetch('/api/genres');
        if (res.ok) this.genreList = await res.json();
      } catch (e) {}
    },

    async addCustomGenre(name) {
      name = (name || '').trim();
      if (!name) return null;
      // 已经在列表里
      if (this.genreList.find((g) => g.name === name)) return null;
      try {
        const res = await fetch('/api/genres', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name }),
        });
        if (res.ok) {
          const g = await res.json();
          this.genreList.push(g);
          return g;
        }
      } catch (e) {}
      return null;
    },

    addGenreToNewProject(evt) {
      const name = evt.target.value;
      if (!name) return;
      if (!this.newProjectForm.genres.includes(name)) {
        this.newProjectForm.genres.push(name);
      }
      evt.target.value = '';
    },

    /**
     * 移除已选题材（创建项目表单中已选 chip 上的 × 按钮）
     * 修复：之前模板里使用 `:key="g + '-' + i"` 并直接 splice(i,1)，
     * 删除任一标签后剩余项的索引都会变化，导致 x-for 重新渲染异常，
     * 表现是"删一个，全部消失"。
     * 这里改为按值查找并过滤，避开了索引带来的 key 不稳定问题。
     */
    removeGenre(name) {
      const idx = this.newProjectForm.genres.indexOf(name);
      if (idx >= 0) {
        this.newProjectForm.genres.splice(idx, 1);
      }
    },

    async submitNewGenre() {
      const name = (this.newGenreInput || '').trim();
      if (!name) return;
      const g = await this.addCustomGenre(name);
      if (g) {
        // 自动加到当前表单的已选
        if (!this.newProjectForm.genres.includes(g.name)) {
          this.newProjectForm.genres.push(g.name);
        }
        this.newGenreInput = '';
      } else {
        alert('题材已存在或添加失败');
      }
    },

    // ─── 旧版灵感 API 兼容（项目内右侧面板还引用） ───

    async saveInspiration() {
      // 兼容旧版（项目内右侧面板用）→ 跳到新版 hub
      this.openInspirationHub();
    },

    async deleteInspiration(inspId) {
      return this.deleteInspirationById(inspId);
    },

    async saveProjectSettings() {
      if (!this.currentProject) return;
      try {
        await fetch(`/api/projects/${this.currentProject.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: this.currentProject.title,
            description: this.currentProject.description,
            writing_style: this.currentProject.writing_style,
            ai味去除程度: this.currentProject.ai味去除程度,
            target_word_count: parseInt(this.currentProject.target_word_count) || 3000,
            word_count_min: parseInt(this.currentProject.word_count_min) || 2700,
            word_count_max: parseInt(this.currentProject.word_count_max) || 3300,
            total_chapters: parseInt(this.currentProject.total_chapters) || 0,
          }),
        });
        this.showProjectSettings = false;
      } catch (e) { console.error(e); }
    },

    // ─── 章节 ───
    async loadChapters(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/chapters`);
        this.chapters = await res.json();
        // 加载后重新计算项目总字数(用于侧边栏字数进度)
        this._recalcProjectWordCount();
      } catch (e) { console.error(e); }
    },

    async createChapter() {
      if (!this.currentProject) return;
      const title = prompt('请输入章节标题:', `第 ${this.chapters.length + 1} 章`);
      if (!title) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/chapters`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title, order: this.chapters.length }),
        });
        const ch = await res.json();
        this.chapters.push(ch);
        this.selectChapter(ch);
      } catch (e) { alert('创建失败: ' + e.message); }
    },

    async selectChapter(chapter) {
      if (!chapter || !this.currentProject) return;
      this.activePanel = 'writing';
      this.chapterDirty = false;
      this._saveLastView();
      // 从服务器重新拉取最新章节数据（pipeline 生成后 content 已更新）
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/chapters/${chapter.id}`);
        if (res.ok) {
          this.currentChapter = await res.json();
        } else {
          this.currentChapter = chapter;
        }
      } catch (e) {
        this.currentChapter = chapter;
      }
      // 记录内容快照（用于保存时对比）
      this.chapterContentSnapshot = (this.currentChapter && this.currentChapter.content) || '';
      this.chapterDirty = false;
      // 如果该章节有进行中的任务，自动打开任务面板
      this._autoOpenTaskPanelForChapter(this.currentChapter);
      // 加载该章节的评审数据
      this._loadChapterReview(this.currentChapter);
      // 加载该章节的 prep-info（已发生事件 + RAG 相似事件）
      this.loadChapterPrepInfo(chapter.id);
    },

    async loadChapterPrepInfo(chapterId) {
      if (!chapterId || !this.currentProject) return;
      this.chapterPrepInfo = null;
      try {
        const res = await fetch(
          `/api/projects/${this.currentProject.id}/chapters/${chapterId}/prep-info`
        );
        if (res.ok) {
          this.chapterPrepInfo = await res.json();
        }
      } catch (e) {
        console.warn('[loadChapterPrepInfo] failed:', e);
      }
    },

    async _loadChapterReview(chapter) {
      if (!chapter || !this.currentProject) return;
      this.previewReview = null;
      try {
        const res = await fetch(`/api/reviews/project/${this.currentProject.id}`);
        const all = await res.json();
        const found = all.find(r => r.chapter_id === chapter.id);
        if (found) this.previewReview = found;
      } catch (e) { /* ignore */ }
    },

    _autoOpenTaskPanelForChapter(chapter) {
      if (!chapter || !this.tasks) return;
      const runningTask = this.tasks.find(t =>
        t.status === 'running' &&
        t.description &&
        t.description.includes('[' + chapter.id + ']')
      );
      if (runningTask) {
        this.showTaskPanel = true;
      }
    },

    async saveChapter(silent) {
      if (!this.currentChapter) return;
      // 非静默模式：手动保存，弹确认
      if (!silent) {
        if (!this.chapterDirty) {
          alert('内容未发生变更，无需保存。');
          return;
        }
        const oldLen = this.chapterContentSnapshot.length;
        const newLen = (this.currentChapter.content || '').length;
        const diff = newLen - oldLen;
        const diffText = diff > 0 ? `+${diff} 字` : diff < 0 ? `${diff} 字` : '字数未变（可能修改了内容）';
        const msg = `确认保存？\n\n章节：${this.currentChapter.title}\n原字数：${oldLen} → 现字数：${newLen}（${diffText}）`;
        if (!confirm(msg)) return;
      }
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/chapters/${this.currentChapter.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: this.currentChapter.title,
            content: this.currentChapter.content,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          alert('保存失败: ' + (err.detail || `HTTP ${res.status}`));
          return;
        }
        const ch = await res.json();
        this.currentChapter = ch;
        // 更新快照 + 清除 dirty
        this.chapterContentSnapshot = ch.content || '';
        this.chapterDirty = false;
        // 更新章节列表中的记录
        const idx = this.chapters.findIndex(c => c.id === ch.id);
        if (idx >= 0) this.chapters[idx] = ch;
        // 更新项目总字数
        const total = this.chapters.reduce((s, c) => s + (c.word_count || 0), 0);
        this.currentProject.word_count = total;
      } catch (e) {
        console.error('保存失败:', e);
        alert('保存失败: ' + e.message);
      }
    },

    onContentChange() {
      const text = this.currentChapter?.content || '';
      const chinese = (text.match(/[一-鿿]/g) || []).length;
      const english = (text.match(/[a-zA-Z]+/g) || []).length;
      if (this.currentChapter) {
        this.currentChapter.word_count = chinese + english;
      }
      this.chapterDirty = true;
    },

    // ─── 字数辅助 ───
    get wordProgressPercent() {
      if (!this.currentProject || !this.currentProject.target_word_count) return 0;
      return Math.min(100, (this.currentProject.word_count / this.currentProject.target_word_count) * 100);
    },

    getWordCountStyle(chapter) {
      if (!this.currentProject) return '';
      const max = this.currentProject.word_count_max || this.currentProject.target_word_count * 1.5;
      const min = this.currentProject.word_count_min || this.currentProject.target_word_count * 0.5;
      if (chapter.word_count > max) return 'color: #ef4444';
      if (chapter.word_count < min) return 'color: #f59e0b';
      return 'color: #22c55e';
    },

    getWordCountBadgeClass(chapter) {
      if (!this.currentProject) return '';
      const max = this.currentProject.word_count_max || this.currentProject.target_word_count * 1.5;
      const min = this.currentProject.word_count_min || this.currentProject.target_word_count * 0.5;
      if (chapter.word_count > max) return 'badge-over';
      if (chapter.word_count < min) return 'badge-under';
      return 'badge-ok';
    },

    wordCountStatus(chapter) {
      if (!this.currentProject) return '';
      const max = this.currentProject.word_count_max || this.currentProject.target_word_count * 1.5;
      const min = this.currentProject.word_count_min || this.currentProject.target_word_count * 0.5;
      if (chapter.word_count > max) return `⚠️ 超限（上限 ${max} 字）`;
      if (chapter.word_count < min) return `⚠️ 字数不足（下限 ${min} 字）`;
      return `✅ 字数正常`;
    },

    getChapterTitle(chapterId) {
      const ch = this.chapters.find(c => c.id === chapterId);
      return ch ? ch.title : '未知章节';
    },

    // ─── 主题 ───
    async loadThemes(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/themes`);
        this.themes = await res.json();
      } catch (e) { console.error(e); }
    },

    async saveTheme() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/themes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.themeForm),
        });
        const t = await res.json();
        this.themes.push(t);
        this.showThemeForm = false;
        this.themeForm = { theme_type: 'core_theme', title: '', description: '' };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    // ─── 伏笔 ───
    async loadForeshadowings(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/foreshadowings`);
        this.foreshadowings = await res.json();
      } catch (e) { console.error(e); }
    },

    // ─── 剧情追踪 ───
    async loadPlotPoints() {
      if (!this.currentProject) return;
      try {
        const params = new URLSearchParams();
        if (this.plotSearch.q) params.set('q', this.plotSearch.q);
        if (this.plotSearch.status) params.set('status', this.plotSearch.status);
        if (this.plotSearch.importance) params.set('importance', this.plotSearch.importance);
        if (this.plotSearch.rangeMin || this.plotSearch.rangeMax) {
          const lo = this.plotSearch.rangeMin || '';
          const hi = this.plotSearch.rangeMax || '';
          params.set('chapter_range', `${lo}-${hi}`);
        }
        const res = await fetch(`/api/projects/${this.currentProject.id}/plot-points?${params}`);
        this.plotPoints = await res.json();
      } catch (e) { console.error(e); }
    },

    openPlotPointForm(pp = null) {
      if (pp) {
        this.plotForm = {
          id: pp.id,
          title: pp.title || '',
          description: pp.description || '',
          tagInput: (pp.tags || []).join(', '),
          importance: pp.importance || 'major',
          status: pp.status || 'planning',
          intro_chapter_id: pp.intro_chapter_id || null,
          develop_chapter_id: pp.develop_chapter_id || null,
          climax_chapter_id: pp.climax_chapter_id || null,
          resolve_chapter_id: pp.resolve_chapter_id || null,
          intro_note: pp.intro_note || '',
          develop_note: pp.develop_note || '',
          climax_note: pp.climax_note || '',
          resolve_note: pp.resolve_note || '',
        };
      } else {
        this.plotForm = {
          id: null, title: '', description: '', tagInput: '',
          importance: 'major', status: 'planning',
          intro_chapter_id: null, develop_chapter_id: null, climax_chapter_id: null, resolve_chapter_id: null,
          intro_note: '', develop_note: '', climax_note: '', resolve_note: '',
        };
      }
      this.showPlotPointForm = true;
    },

    async savePlotPoint() {
      if (!this.currentProject) return;
      if (!this.plotForm.title.trim()) {
        alert('请输入标题');
        return;
      }
      const tags = (this.plotForm.tagInput || '').split(',').map((t) => t.trim()).filter(Boolean);
      const payload = {
        title: this.plotForm.title,
        description: this.plotForm.description,
        tags,
        importance: this.plotForm.importance,
        status: this.plotForm.status,
        intro_chapter_id: this.plotForm.intro_chapter_id || null,
        develop_chapter_id: this.plotForm.develop_chapter_id || null,
        climax_chapter_id: this.plotForm.climax_chapter_id || null,
        resolve_chapter_id: this.plotForm.resolve_chapter_id || null,
        intro_note: this.plotForm.intro_note,
        develop_note: this.plotForm.develop_note,
        climax_note: this.plotForm.climax_note,
        resolve_note: this.plotForm.resolve_note,
      };
      try {
        const url = this.plotForm.id
          ? `/api/projects/${this.currentProject.id}/plot-points/${this.plotForm.id}`
          : `/api/projects/${this.currentProject.id}/plot-points`;
        const method = this.plotForm.id ? 'PUT' : 'POST';
        const res = await fetch(url, {
          method,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        this.showPlotPointForm = false;
        await this.loadPlotPoints();
      } catch (e) {
        alert('保存失败：' + e.message);
      }
    },

    async deletePlotPoint(pp) {
      if (!confirm(`确定删除剧情点「${pp.title}」？`)) return;
      try {
        const res = await fetch(
          `/api/projects/${this.currentProject.id}/plot-points/${pp.id}`,
          { method: 'DELETE' }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await this.loadPlotPoints();
      } catch (e) {
        alert('删除失败：' + e.message);
      }
    },

    togglePlotExpanded(id) {
      this.plotExpandedId = this.plotExpandedId === id ? null : id;
    },

    /** 把 chapter id 映射成 "第N章" 显示；null 返回 null */
    getChapterOrder(chapterId) {
      if (!chapterId) return null;
      const ch = this.chapters.find((c) => c.id === chapterId);
      return ch ? ch.order + 1 : null;
    },

    plotStatusLabel(s) {
      return ({
        planning: '规划中',
        introduced: '已引入',
        developing: '发展中',
        climaxed: '高潮中',
        resolved: '已回收',
        abandoned: '已废弃',
      })[s] || s;
    },

    async saveForeshadowing() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/foreshadowings`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.foreshadowingForm),
        });
        const f = await res.json();
        this.foreshadowings.push(f);
        this.showForeshadowingForm = false;
        this.foreshadowingForm = { title: '', content: '' };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    async resolveForeshadowing(f) {
      await fetch(`/api/projects/${this.currentProject.id}/foreshadowings/${f.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'resolved', resolve_chapter_id: this.currentChapter?.id }),
      });
      f.status = 'resolved';
    },

    async abandonForeshadowing(f) {
      await fetch(`/api/projects/${this.currentProject.id}/foreshadowings/${f.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'abandoned' }),
      });
      f.status = 'abandoned';
    },

    // ─── 角色 ───
    async loadCharacters(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/characters`);
        this.characters = await res.json();
      } catch (e) { console.error(e); }
    },

    async saveCharacter() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/characters`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.characterForm),
        });
        const c = await res.json();
        this.characters.push(c);
        this.showCharacterForm = false;
        this.characterForm = { name: '', role: '配角', description: '' };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    getCharacterName(id) {
      const c = this.characters.find(ch => ch.id === id);
      return c ? c.name : '未知';
    },

    // ─── 角色弧光 ───
    async loadCharacterArcs(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/character-arcs`);
        this.characterArcs = await res.json();
      } catch (e) { console.error(e); }
    },

    async saveArc() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/character-arcs`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.arcForm),
        });
        const a = await res.json();
        this.characterArcs.push(a);
        this.showArcForm = false;
        this.arcForm = { character_id: null, arc_type: 'growth', start_state: '', current_state: '', end_state: '' };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    // ─── 角色关系 ───
    async loadCharacterRelations(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/character-relations`);
        this.characterRelations = await res.json();
      } catch (e) { console.error(e); }
    },

    async saveRelation() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/character-relations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(this.relationForm),
        });
        const r = await res.json();
        this.characterRelations.push(r);
        this.showRelationForm = false;
        this.relationForm = { from_character_id: null, to_character_id: null, relation_type: '友情', description: '', strength: 5 };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    // ─── 角色关系图谱（可交互） ───
    // ──────────────────────────────────────────────────────────
    // 设计：
    //  1. 节点来自 mergedCharacters()（AI + 手动合并），边来自手动 characterRelations + AI bootstrapData.relations
    //  2. 节点唯一 key: 手动角色用 'm-{id}', AI 角色用 'a-{name}'
    //  3. 边的 from/to 引用上面的 _key；加载时把 AI 关系 from/to (name) 转成 _key
    //  4. 节点位置 (x,y) 自动用环形布局；用户拖动后保存到 localStorage
    //  5. SVG 渲染：g[transform=translate+scale] 处理 pan/zoom；node 是 g 元素，绑定 mousedown 拖拽
    //  6. 新建关系模式：依次点两个节点 → 弹出表单 → POST /character-relations
    //  7. 边编辑：选中边 → 右侧面板显示表单 → PUT /character-relations/{id}
    //  8. 边删除：DELETE /character-relations/{id}
    // ──────────────────────────────────────────────────────────

    /**
     * 角色 → 图谱节点 key 映射。
     * 手动角色（_source='manual'，有 id）→ 'm-{id}'
     * AI 角色（_source='ai'，无 id）→ 'a-{name}'
     */
    relGraphCharKey(c) {
      if (!c) return null;
      if (c._source === 'manual' && c._id) return 'm-' + c._id;
      return 'a-' + (c.name || 'unknown');
    },

    /**
     * 把所有 AI 关系 (from/to 是 name) 和 手动关系 (from_character_id/to_character_id 是 id)
     * 统一转成图谱边的 from/to（key 形式），并合并去重。
     */
    getAllGraphRelations() {
      const chars = this.mergedCharacters();
      const keyByName = {};    // name → key
      const keyById = {};      // id → key
      for (const c of chars) {
        const key = this.relGraphCharKey(c);
        if (c.name) keyByName[c.name] = key;
        if (c._id) keyById[c._id] = key;
      }

      const edges = [];
      const seen = new Set();

      // 手动关系（有 id，可编辑/删除）
      for (const r of (this.characterRelations || [])) {
        const from = keyById[r.from_character_id];
        const to = keyById[r.to_character_id];
        if (!from || !to || from === to) continue;
        const dedupKey = from + '|' + to + '|' + (r.relation_type || '');
        if (seen.has(dedupKey)) continue;
        seen.add(dedupKey);
        edges.push({
          id: 'm-' + r.id,
          _realId: r.id,
          _editable: true,
          from,
          to,
          relation_type: r.relation_type || '未分类',
          description: r.description || '',
          strength: r.strength || 5,
          status: r.status || 'stable',
        });
      }

      // AI 关系（只读）
      for (const r of (this.bootstrapAiRelations() || [])) {
        const from = keyByName[r.from];
        const to = keyByName[r.to];
        if (!from || !to || from === to) continue;
        const dedupKey = from + '|' + to + '|' + (r.type || '');
        if (seen.has(dedupKey)) continue;
        seen.add(dedupKey);
        edges.push({
          id: 'ai-' + (r.from + '-' + r.to + '-' + (r.type || '')),
          _editable: false,
          from,
          to,
          relation_type: r.type || '未分类',
          description: r.description || '',
          strength: r.strength || 5,
          status: r.status || 'stable',
        });
      }

      return edges;
    },

    /**
     * 把节点摆放到一个圆环（主角居中，其它环上均匀分布）。
     * 已存在的节点保持当前 x/y；新增的节点补到合适位置。
     */
    relGraphAutoLayout() {
      const chars = this.mergedCharacters();
      if (chars.length === 0) {
        this.relGraphNodes = [];
        this.relGraphEdges = [];
        this._renderRelGraphSvg();
        return;
      }
      const W = (this.$refs.relGraphWrap && this.$refs.relGraphWrap.clientWidth) || 900;
      const H = (this.$refs.relGraphWrap && this.$refs.relGraphWrap.clientHeight) || 600;
      const cx = W / 2;
      const cy = H / 2;

      // 已有位置：内存 > localStorage
      const savedPos = this._loadRelGraphPositions();
      const oldPos = {};
      for (const n of this.relGraphNodes) oldPos[n._key] = { x: n.x, y: n.y };
      for (const k of Object.keys(savedPos)) {
        if (!oldPos[k] && this._isFinite(savedPos[k].x) && this._isFinite(savedPos[k].y)) {
          oldPos[k] = savedPos[k];
        }
      }

      const roleOrder = { '主角': 0, '反派': 1, '配角': 2, '龙套': 3 };
      const sorted = chars.slice().sort((a, b) => {
        const ra = roleOrder[a.role] ?? 9;
        const rb = roleOrder[b.role] ?? 9;
        if (ra !== rb) return ra - rb;
        return (a.name || '').localeCompare(b.name || '', 'zh-CN');
      });

      // 主角居中
      const protagonists = sorted.filter((c) => c.role === '主角');
      const others = sorted.filter((c) => c.role !== '主角');
      const nodes = [];

      // 主角：1 个居中，多个第一圈
      if (protagonists.length === 1) {
        const c = protagonists[0];
        const key = this.relGraphCharKey(c);
        const old = oldPos[key];
        nodes.push({
          _key: key,
          _id: c._id,
          _source: c._source,
          name: c.name || '未命名',
          role: c.role,
          description: c.description || '',
          profile: c.profile || {},
          _roleIcon: '👑',
          x: old && this._isFinite(old.x) ? old.x : cx,
          y: old && this._isFinite(old.y) ? old.y : cy,
        });
      } else if (protagonists.length > 1) {
        const r = Math.min(W, H) * 0.18;
        protagonists.forEach((c, i) => {
          const key = this.relGraphCharKey(c);
          const old = oldPos[key];
          const ang = (i / protagonists.length) * Math.PI * 2 - Math.PI / 2;
          nodes.push({
            _key: key,
            _id: c._id,
            _source: c._source,
            name: c.name || '未命名',
            role: c.role,
            description: c.description || '',
            profile: c.profile || {},
            _roleIcon: '👑',
            x: old && this._isFinite(old.x) ? old.x : cx + Math.cos(ang) * r,
            y: old && this._isFinite(old.y) ? old.y : cy + Math.sin(ang) * r,
          });
        });
      }

      // 其它角色均匀分布在多圈
      if (others.length > 0) {
        const ringCount = Math.min(3, Math.ceil(others.length / 8));
        const minR = Math.min(W, H) * 0.22;
        const maxR = Math.min(W, H) * 0.4;
        others.forEach((c, i) => {
          const ring = Math.min(ringCount - 1, Math.floor(i / Math.ceil(others.length / ringCount)));
          const ringStart = ringCount === 1 ? 0 : Math.floor(i / Math.ceil(others.length / ringCount)) * Math.ceil(others.length / ringCount);
          const ringSize = Math.min(others.length - ringStart, Math.ceil(others.length / ringCount));
          const idxInRing = i - ringStart;
          const r = minR + (maxR - minR) * (ring / Math.max(1, ringCount - 1));
          const ang = (idxInRing / ringSize) * Math.PI * 2 - Math.PI / 2;
          const key = this.relGraphCharKey(c);
          const old = oldPos[key];
          const roleIcon = c.role === '反派' ? '⚔️' : c.role === '龙套' ? '🗣️' : '🎭';
          nodes.push({
            _key: key,
            _id: c._id,
            _source: c._source,
            name: c.name || '未命名',
            role: c.role || '配角',
            description: c.description || '',
            profile: c.profile || {},
            _roleIcon: roleIcon,
            x: old && this._isFinite(old.x) ? old.x : cx + Math.cos(ang) * r,
            y: old && this._isFinite(old.y) ? old.y : cy + Math.sin(ang) * r,
          });
        });
      }

      this.relGraphNodes = nodes;
      this.relGraphEdges = this.getAllGraphRelations();
      this._saveRelGraphPositions();
      this._applyRelGraphTransform();
      this._renderRelGraphSvg();
    },

    _isFinite(v) { return typeof v === 'number' && Number.isFinite(v); },

    /**
     * 加载（首次打开面板时）：保证节点 / 边准备好并渲染。
     * 渲染逻辑 = 重建 SVG DOM（避免 Alpine 频繁 diff 卡顿）。
     */
    renderRelationGraph() {
      // 每次切换到图谱页都重建一次（AI 数据可能变化）
      const chars = this.mergedCharacters();
      if (chars.length === 0) {
        this.relGraphNodes = [];
        this.relGraphEdges = [];
        this._renderRelGraphSvg();
        return;
      }
      // 自动布局：保留用户已拖动的位置
      this.relGraphAutoLayout();
    },

    /**
     * 把 relGraphNodes / relGraphEdges 真正画到 SVG。
     * 直接 DOM 操作（不用 Alpine x-for）——节点/边很多时 x-for 频繁 diff 会卡。
     */
    _renderRelGraphSvg() {
      if (!this.$refs.relGraphEdges || !this.$refs.relGraphNodes) return;
      const edgesG = this.$refs.relGraphEdges;
      const nodesG = this.$refs.relGraphNodes;
      const SVG_NS = 'http://www.w3.org/2000/svg';
      edgesG.innerHTML = '';
      nodesG.innerHTML = '';

      // ─── 边 ───
      const nodeByKey = {};
      for (const n of this.relGraphNodes) nodeByKey[n._key] = n;

      for (const e of this.relGraphEdges) {
        const fromN = nodeByKey[e.from];
        const toN = nodeByKey[e.to];
        if (!fromN || !toN) continue;
        const dx = toN.x - fromN.x;
        const dy = toN.y - fromN.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len === 0) continue;
        // 缩短线条：避开节点圆（半径约 32）
        const ux = dx / len, uy = dy / len;
        const r1 = 32, r2 = 32;
        const x1 = fromN.x + ux * r1;
        const y1 = fromN.y + uy * r1;
        const x2 = toN.x - ux * r2;
        const y2 = toN.y - uy * r2;
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;

        // 命中层（透明粗线，方便点击）
        const hit = document.createElementNS(SVG_NS, 'line');
        hit.setAttribute('class', 'rg-edge-hit');
        hit.setAttribute('x1', x1); hit.setAttribute('y1', y1);
        hit.setAttribute('x2', x2); hit.setAttribute('y2', y2);
        hit.dataset.edgeId = e.id;
        hit.addEventListener('click', (ev) => {
          ev.stopPropagation();
          this.relGraphSelectedEdgeId = e.id;
          this.relGraphSelectedNodeId = null;
          this.relGraphEditForm = {
            relation_type: e.relation_type,
            description: e.description,
            strength: e.strength,
            status: e.status,
          };
          this._renderRelGraphSvg();
        });
        edgesG.appendChild(hit);

        // 可见边
        const line = document.createElementNS(SVG_NS, 'line');
        const status = e.status || 'stable';
        line.setAttribute('class', `rg-edge status-${status}` + (this.relGraphSelectedEdgeId === e.id ? ' selected' : ''));
        const width = 1 + (e.strength || 5) * 0.3;
        line.setAttribute('stroke-width', width);
        line.setAttribute('marker-end', `url(#rg-arrow-${status})`);
        line.setAttribute('x1', x1); line.setAttribute('y1', y1);
        line.setAttribute('x2', x2); line.setAttribute('y2', y2);
        edgesG.appendChild(line);

        // 标签（关系类型）
        if (this.relGraphToggleLabels) {
          const labelText = e.relation_type || '关系';
          // 估算文字宽度
          const labelW = Math.max(28, labelText.length * 12 + 10);
          const labelH = 16;
          const bg = document.createElementNS(SVG_NS, 'rect');
          bg.setAttribute('class', `rg-edge-label-bg status-${status}`);
          bg.setAttribute('x', mx - labelW / 2);
          bg.setAttribute('y', my - labelH / 2);
          bg.setAttribute('width', labelW);
          bg.setAttribute('height', labelH);
          edgesG.appendChild(bg);
          const text = document.createElementNS(SVG_NS, 'text');
          text.setAttribute('class', 'rg-edge-label');
          text.setAttribute('x', mx);
          text.setAttribute('y', my + 1);
          text.textContent = labelText;
          edgesG.appendChild(text);
        }
      }

      // ─── 节点 ───
      for (const n of this.relGraphNodes) {
        const g = document.createElementNS(SVG_NS, 'g');
        const isSelected = this.relGraphSelectedNodeId === n._key;
        const isAddSource = this.relGraphAddMode && this.relGraphAddFrom === n._key;
        const isAddTarget = this.relGraphAddMode && this.relGraphAddFrom && this.relGraphAddFrom !== n._key && this.relGraphAddStep === 'pickTo';
        g.setAttribute('class', 'rg-node-group' + (isSelected ? ' selected' : ''));
        g.setAttribute('transform', `translate(${n.x}, ${n.y})`);
        g.dataset.nodeKey = n._key;
        g.style.cursor = this.relGraphAddMode ? 'crosshair' : 'pointer';

        // 圆环
        const circle = document.createElementNS(SVG_NS, 'circle');
        circle.setAttribute('class', `rg-node-circle role-${n.role || '配角'}`);
        circle.setAttribute('r', isSelected ? 34 : 30);
        circle.setAttribute('cx', 0);
        circle.setAttribute('cy', 0);
        g.appendChild(circle);

        // 高亮"待选"状态
        if (this.relGraphAddMode && isAddSource) {
          const halo = document.createElementNS(SVG_NS, 'circle');
          halo.setAttribute('r', 38);
          halo.setAttribute('fill', 'none');
          halo.setAttribute('stroke', '#6366f1');
          halo.setAttribute('stroke-width', '2');
          halo.setAttribute('stroke-dasharray', '4 3');
          g.appendChild(halo);
        }

        // 图标（emoji）
        const icon = document.createElementNS(SVG_NS, 'text');
        icon.setAttribute('class', 'rg-node-icon');
        icon.setAttribute('x', 0);
        icon.setAttribute('y', -2);
        icon.textContent = n._roleIcon || '👤';
        g.appendChild(icon);

        // 角色标签
        const roleLabel = document.createElementNS(SVG_NS, 'text');
        roleLabel.setAttribute('class', 'rg-node-role');
        roleLabel.setAttribute('x', 0);
        roleLabel.setAttribute('y', 14);
        roleLabel.textContent = n.role || '配角';
        g.appendChild(roleLabel);

        // 名字
        const nameLabel = document.createElementNS(SVG_NS, 'text');
        nameLabel.setAttribute('class', `rg-node-label role-${n.role || '配角'}`);
        nameLabel.setAttribute('x', 0);
        nameLabel.setAttribute('y', 44);
        nameLabel.textContent = n.name;
        g.appendChild(nameLabel);

        // 鼠标事件
        g.addEventListener('mousedown', (ev) => this._onNodeMouseDown(ev, n._key));
        g.addEventListener('mouseenter', (ev) => this._showRelGraphTooltip(ev, `${n.name} · ${n.role || '配角'}`));
        g.addEventListener('mousemove', (ev) => this._showRelGraphTooltip(ev, `${n.name} · ${n.role || '配角'}`));
        g.addEventListener('mouseleave', () => this._hideRelGraphTooltip());
        g.addEventListener('click', (ev) => this._onNodeClick(ev, n._key));

        nodesG.appendChild(g);
      }
    },

    /**
     * 应用 pan/zoom 到 content group
     */
    _applyRelGraphTransform() {
      if (!this.$refs.relGraphContent) return;
      const v = this.relGraphView;
      this.$refs.relGraphContent.setAttribute(
        'transform',
        `translate(${v.x}, ${v.y}) scale(${v.scale})`
      );
    },

    /**
     * 把当前节点位置保存到 localStorage（按项目 ID 隔离）。
     */
    _saveRelGraphPositions() {
      if (!this.currentProject) return;
      try {
        const key = `relGraph-pos-${this.currentProject.id}`;
        const data = {};
        for (const n of this.relGraphNodes) {
          data[n._key] = { x: n.x, y: n.y };
        }
        localStorage.setItem(key, JSON.stringify(data));
      } catch (e) {}
    },

    _loadRelGraphPositions() {
      if (!this.currentProject) return {};
      try {
        const key = `relGraph-pos-${this.currentProject.id}`;
        const raw = localStorage.getItem(key);
        if (!raw) return {};
        return JSON.parse(raw);
      } catch (e) { return {}; }
    },

    // ─── 交互：拖拽节点 ───
    _onNodeMouseDown(ev, nodeKey) {
      if (this.relGraphAddMode) return;  // 添加模式下交给 click 处理
      ev.stopPropagation();
      ev.preventDefault();
      const node = this.relGraphNodes.find((n) => n._key === nodeKey);
      if (!node) return;

      // 把屏幕坐标换算成 SVG 坐标
      const svg = this.$refs.relGraphSvg;
      const pt = this._screenToSvg(ev.clientX, ev.clientY);

      this.relGraphDragging.node = nodeKey;
      this.relGraphDragging.lastX = pt.x;
      this.relGraphDragging.lastY = pt.y;
      // 选中节点
      this.relGraphSelectedNodeId = nodeKey;
      this.relGraphSelectedEdgeId = null;
      this._renderRelGraphSvg();

      const move = (e) => {
        const p = this._screenToSvg(e.clientX, e.clientY);
        const dx = p.x - this.relGraphDragging.lastX;
        const dy = p.y - this.relGraphDragging.lastY;
        this.relGraphDragging.lastX = p.x;
        this.relGraphDragging.lastY = p.y;
        const node = this.relGraphNodes.find((n) => n._key === this.relGraphDragging.node);
        if (node) {
          node.x += dx;
          node.y += dy;
          this._renderRelGraphSvg();
        }
      };
      const up = () => {
        this.relGraphDragging.node = null;
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', up);
        this._saveRelGraphPositions();
      };
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', up);
    },

    // ─── 交互：拖画布 ───
    onRelGraphCanvasMouseDown(ev) {
      // 节点拖拽已 stopPropagation，所以这里只有"点空白"会进来
      if (ev.target.closest('.rg-node-group')) return;
      if (this.relGraphAddMode) return;  // 添加模式不拖画布
      ev.preventDefault();
      this.relGraphDragging.canvas = true;
      this.relGraphDragging.lastX = ev.clientX;
      this.relGraphDragging.lastY = ev.clientY;
      this.relGraphDragging.panStartView = { ...this.relGraphView };
      // 选中清空
      this.relGraphSelectedNodeId = null;
      this.relGraphSelectedEdgeId = null;
      this._renderRelGraphSvg();
    },

    onRelGraphCanvasMouseMove(ev) {
      if (!this.relGraphDragging.canvas) return;
      const dx = ev.clientX - this.relGraphDragging.lastX;
      const dy = ev.clientY - this.relGraphDragging.lastY;
      this.relGraphDragging.lastX = ev.clientX;
      this.relGraphDragging.lastY = ev.clientY;
      this.relGraphView.x += dx;
      this.relGraphView.y += dy;
      this._applyRelGraphTransform();
    },

    onRelGraphCanvasMouseUp() {
      if (this.relGraphDragging.canvas) {
        this.relGraphDragging.canvas = false;
      }
    },

    // ─── 交互：滚轮缩放（以鼠标位置为中心） ───
    onRelGraphWheel(ev) {
      const svg = this.$refs.relGraphSvg;
      if (!svg) return;
      const rect = svg.getBoundingClientRect();
      const mx = ev.clientX - rect.left;
      const my = ev.clientY - rect.top;
      const factor = ev.deltaY < 0 ? 1.15 : 0.87;
      const newScale = Math.min(3, Math.max(0.2, this.relGraphView.scale * factor));
      const realFactor = newScale / this.relGraphView.scale;
      // 保持鼠标点不动：tx = mx - (mx - tx) * factor
      this.relGraphView.x = mx - (mx - this.relGraphView.x) * realFactor;
      this.relGraphView.y = my - (my - this.relGraphView.y) * realFactor;
      this.relGraphView.scale = newScale;
      this._applyRelGraphTransform();
    },

    relGraphZoomIn() {
      this.relGraphView.scale = Math.min(3, this.relGraphView.scale * 1.2);
      this._applyRelGraphTransform();
    },
    relGraphZoomOut() {
      this.relGraphView.scale = Math.max(0.2, this.relGraphView.scale * 0.85);
      this._applyRelGraphTransform();
    },
    relGraphResetView() {
      this.relGraphView = { x: 0, y: 0, scale: 1 };
      this._applyRelGraphTransform();
    },

    // ─── 屏幕坐标 → SVG 内容坐标（考虑 pan + zoom） ───
    _screenToSvg(clientX, clientY) {
      const svg = this.$refs.relGraphSvg;
      const rect = svg.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      return {
        x: (mx - this.relGraphView.x) / this.relGraphView.scale,
        y: (my - this.relGraphView.y) / this.relGraphView.scale,
      };
    },

    // ─── 节点点击 ───
    _onNodeClick(ev, nodeKey) {
      if (this.relGraphAddMode) {
        ev.stopPropagation();
        this._handleAddModeClick(nodeKey);
        return;
      }
      // 普通点击：选中节点
      this.relGraphSelectedNodeId = nodeKey;
      this.relGraphSelectedEdgeId = null;
      this._renderRelGraphSvg();
    },

    _handleAddModeClick(nodeKey) {
      if (this.relGraphAddStep === 'pickFrom') {
        this.relGraphAddFrom = nodeKey;
        this.relGraphAddStep = 'pickTo';
      } else if (this.relGraphAddStep === 'pickTo') {
        if (nodeKey === this.relGraphAddFrom) return;  // 不能自环
        this.relGraphAddTo = nodeKey;
        this.relGraphAddStep = 'confirm';
      }
      this._renderRelGraphSvg();
    },

    // ─── Tooltip ───
    _showRelGraphTooltip(ev, text) {
      const tip = this.$refs.relGraphTooltip;
      const wrap = this.$refs.relGraphWrap;
      if (!tip || !wrap) return;
      const rect = wrap.getBoundingClientRect();
      tip.textContent = text;
      tip.style.left = (ev.clientX - rect.left) + 'px';
      tip.style.top = (ev.clientY - rect.top) + 'px';
      tip.classList.remove('hidden');
    },
    _hideRelGraphTooltip() {
      const tip = this.$refs.relGraphTooltip;
      if (tip) tip.classList.add('hidden');
    },

    // ─── 节点查询 ───
    getRelGraphNodeById(key) {
      return this.relGraphNodes.find((n) => n._key === key);
    },
    getRelGraphEdgeById(id) {
      return this.relGraphEdges.find((e) => e.id === id);
    },
    getRelGraphCharName(key) {
      const n = this.relGraphNodes.find((nn) => nn._key === key);
      return n ? n.name : '未知';
    },
    getRelGraphNodeRelations(key) {
      return this.relGraphEdges.filter((e) => e.from === key || e.to === key);
    },

    // ─── 边编辑保存 ───
    async saveRelationGraphEdit() {
      const edge = this.getRelGraphEdgeById(this.relGraphSelectedEdgeId);
      if (!edge || !edge._editable || !edge._realId) {
        alert('该关系不可编辑（仅可编辑手动添加的关系）');
        return;
      }
      try {
        const res = await fetch(
          `/api/projects/${this.currentProject.id}/character-relations/${edge._realId}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.relGraphEditForm),
          }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const updated = await res.json();
        // 同步更新 characterRelations 数组
        const idx = this.characterRelations.findIndex((r) => r.id === edge._realId);
        if (idx >= 0) this.characterRelations[idx] = updated;
        // 重渲染图谱
        this.relGraphEdges = this.getAllGraphRelations();
        this._renderRelGraphSvg();
        alert('✓ 已保存');
      } catch (e) {
        alert('保存失败：' + e.message);
      }
    },

    async deleteRelationFromGraph(realId) {
      if (!confirm('确定删除这条关系？')) return;
      try {
        const res = await fetch(
          `/api/projects/${this.currentProject.id}/character-relations/${realId}`,
          { method: 'DELETE' }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        // 从手动数组里删掉
        this.characterRelations = this.characterRelations.filter((r) => r.id !== realId);
        this.relGraphSelectedEdgeId = null;
        this.relGraphEdges = this.getAllGraphRelations();
        this._renderRelGraphSvg();
      } catch (e) {
        alert('删除失败：' + e.message);
      }
    },

    // ─── 新建关系（通过图谱两节点连） ───
    async confirmRelationGraphCreate() {
      const fromNode = this.getRelGraphNodeById(this.relGraphAddFrom);
      const toNode = this.getRelGraphNodeById(this.relGraphAddTo);
      if (!fromNode || !toNode) return;

      // AI 角色无法直接创建手动关系（没有 db id），提示用户先到「角色」页转手动
      if (!fromNode._id || !toNode._id) {
        alert('AI 生成的角色暂不支持直接在图谱中新建关系，请先在「角色」面板手动添加同名角色。');
        this.relGraphAddStep = 'pickFrom';
        this.relGraphAddFrom = null;
        this.relGraphAddTo = null;
        return;
      }

      try {
        const payload = {
          from_character_id: fromNode._id,
          to_character_id: toNode._id,
          relation_type: this.relGraphNewForm.relation_type,
          description: this.relGraphNewForm.description || '',
          strength: this.relGraphNewForm.strength,
        };
        const res = await fetch(
          `/api/projects/${this.currentProject.id}/character-relations`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          }
        );
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const r = await res.json();
        this.characterRelations.push(r);
        this.relGraphEdges = this.getAllGraphRelations();
        this.relGraphAddStep = 'pickFrom';
        this.relGraphAddFrom = null;
        this.relGraphAddTo = null;
        this.relGraphNewForm = { relation_type: '友情', description: '', strength: 5 };
        // 自动选中刚创建的边
        this.relGraphSelectedEdgeId = 'm-' + r.id;
        this.relGraphSelectedNodeId = null;
        this._renderRelGraphSvg();
      } catch (e) {
        alert('创建失败：' + e.message);
      }
    },

    // ─── 一致性检查 ───
    async loadConsistencyReport(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/consistency/report`);
        this.consistencyReport = await res.json();
      } catch (e) { console.error(e); }
    },

    async runConsistencyCheck() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/consistency/check`);
        this.consistencyResult = await res.json();
        await this.loadConsistencyReport(this.currentProject.id);
      } catch (e) { alert('检查失败: ' + e.message); }
    },

    // ─── 评审 ───
    async loadReviewHistory() {
      if (!this.currentProject) return;
      try {
        const res = await fetch(`/api/reviews/project/${this.currentProject.id}`);
        this.reviewHistory = await res.json();
      } catch (e) { console.error(e); }
    },

    async startReview(chapter) {
      this.activeReviewSession = { chapter_id: chapter.id };
      this.reviewResult = null;
      try {
        // 异步：后端立即返回 task_id
        const res = await fetch('/api/reviews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_id: chapter.id,
            session_type: 'chapter',
          }),
        });
        const data = await res.json();
        if (data.status !== 'submitted' || !data.task_id) {
          alert('评审失败: ' + (data.error || JSON.stringify(data)));
          this.activeReviewSession = null;
          return;
        }
        // 轮询 task
        const task = await this._pollTask(data.task_id);
        if (task.status === 'completed') {
          // task.result 包含 session_id / overall_score / scores / critique
          this.reviewResult = task.result;
          await this.loadReviewHistory();
        } else {
          alert('评审失败: ' + (task.error || 'unknown'));
          this.activeReviewSession = null;
        }
      } catch (e) {
        alert('评审失败: ' + e.message);
        this.activeReviewSession = null;
      }
    },

    showReviewDetail(rev) {
      this.activeReviewSession = rev;
      this.reviewResult = rev;
    },

    async reviseFromReview() {
      if (!this.reviewResult) return;
      try {
        const res = await fetch(`/api/reviews/${this.reviewResult.id}/revise`, { method: 'POST' });
        const newRev = await res.json();
        this.reviewResult = newRev;
        alert('修订完成！修订版已生成。');
      } catch (e) { alert('修订失败: ' + e.message); }
    },

    // ─── 预览面板 ───
    async openPreview(chapter) {
      if (!chapter) return;
      this.previewChapter = chapter;
      this.previewSubTab = 'content';
      this.previewReview = null;
      this.activePanel = 'writing';
      // 静默加载该章节最新的评审结果
      try {
        const res = await fetch(`/api/reviews/project/${this.currentProject.id}`);
        const all = await res.json();
        const found = all.find(r => r.chapter_id === chapter.id);
        if (found) this.previewReview = found;
      } catch (e) { /* ignore */ }
    },

    // ─── 章节生成 9 步流水线 ───

    // 9 步元数据（与后端 llm.chapter_pipeline.PIPELINE_STAGES_META 对齐）
    PIPELINE_STAGES_META: [
      { id: '1_prep',           label: '准备上下文' },
      { id: '2_outline_gen',    label: '生成章节细纲' },
      { id: '3_outline_review', label: '细纲评审' },
      { id: '4_text_gen',       label: '生成正文' },
      { id: '5_word_adjust',    label: '字数调整' },
      { id: '6_review',         label: '正文评审' },
      { id: '7_revise',         label: '自动修订' },
      { id: '8_save',           label: '保存到数据库' },
      { id: '9_post',           label: '后处理（弧光/伏笔/一致性）' },
    ],

    get canRunPipeline() {
      // 必须有项目 + 章节
      return !!(this.currentProject && this.currentChapter);
    },

    /**
     * 启动 9 步章节生成流水线：
     *  1. POST /api/chapters/generate-pipeline → 拿 task_id
     *  2. 弹出 showPipelineProgress 弹窗
     *  3. setInterval 轮询 /api/tasks/{id}，每次把 result.stages 推进 UI
     *  4. 终态（completed/failed/cancelled）停止轮询
     */
    async runChapterPipeline(guide) {
      if (!this.canRunPipeline) {
        alert('请先选择项目和章节');
        return;
      }
      if (this.pipelinePollHandle) {
        alert('已有流水线正在运行，请等待完成');
        return;
      }
      try {
        const res = await fetch('/api/chapters/generate-pipeline', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_id: this.currentChapter.id,
            auto_revise: true,
            revision_threshold: 6.5,
            guide: guide || '',
          }),
        });
        const data = await res.json();
        if (!res.ok || !data.task_id) {
          alert('流水线提交失败：' + (data.detail || JSON.stringify(data)));
          return;
        }
        // 打开面板
        this.pipelineTask = { id: data.task_id, status: 'pending', result: { stages: {} } };
        this.pipelineStartTs = Date.now();
        this.showPipelineProgress = true;
        // 开始轮询
        this.pipelinePollHandle = setInterval(() => this._pollPipelineTask(), 2000);
        this._pollPipelineTask();  // 立即拉一次
        // 同时刷新任务管理列表
        if (this.refreshAllTasks) this.refreshAllTasks();
      } catch (e) {
        alert('启动流水线失败：' + e.message);
      }
    },

    async _pollPipelineTask() {
      if (!this.pipelineTask) return;
      try {
        const res = await fetch('/api/tasks/' + this.pipelineTask.id);
        if (!res.ok) return;
        const task = await res.json();
        this.pipelineTask = task;
        // 同步刷新任务管理列表（让顶部 badge 数字也变）
        if (this.refreshAllTasks) this.refreshAllTasks();
        if (['completed', 'failed', 'cancelled'].includes(task.status)) {
          clearInterval(this.pipelinePollHandle);
          this.pipelinePollHandle = null;
          // 完成后自动重拉章节（拿到最新 content）
          if (task.status === 'completed') {
            try { await this.selectChapter(this.currentChapter); } catch (e) { /* ignore */ }
          }
        }
      } catch (e) {
        console.warn('[Pipeline] poll failed:', e);
      }
    },

    closePipelinePanel(navigateToChapter) {
      // 只有在终态才允许关
      const s = this.pipelineStatus;
      const taskDone = !this.pipelineTask || ['completed','failed','cancelled'].includes(this.pipelineTask.status);
      if (!taskDone && s === 'running') {
        if (!confirm('流水线还在运行中，确认关闭此面板？（不会停止后台任务）')) return;
        // 用户选择关：停掉轮询但不动后端任务
        if (this.pipelinePollHandle) {
          clearInterval(this.pipelinePollHandle);
          this.pipelinePollHandle = null;
        }
      } else {
        if (this.pipelinePollHandle) {
          clearInterval(this.pipelinePollHandle);
          this.pipelinePollHandle = null;
        }
      }
      this.showPipelineProgress = false;
      if (navigateToChapter) {
        // 已经在写作台，不用跳
      }
    },

    onPipelineCompletedAndClose() {
      this.closePipelinePanel(false);
      // 重拉章节列表（确保字数/状态更新）
      if (this.currentProject && this.loadChapters) {
        this.loadChapters(this.currentProject.id);
      }
    },

    // 把后端 task.result.stages 合并成 9 步视图（永远显示 9 行）
    get pipelineStagesView() {
      const meta = this.PIPELINE_STAGES_META;
      const backendStages = (this.pipelineTask && this.pipelineTask.result && this.pipelineTask.result.stages) || {};
      const now = Date.now();
      return meta.map(m => {
        const s = backendStages[m.id] || {};
        const startedAtMs = s.started_at ? Math.floor(s.started_at * 1000) : null;
        // running 阶段：实时算 elapsed
        let elapsed_display = '0.0';
        let elapsed_pct = 0;
        if (s.status === 'running') {
          if (startedAtMs) {
            const e = (now - startedAtMs) / 1000;
            elapsed_display = e.toFixed(1);
            // 假设单阶段最多 90s 满，进度条走 e/90
            elapsed_pct = Math.min(95, (e / 90) * 100);
          } else {
            elapsed_display = ((now - this.pipelineStartTs) / 1000).toFixed(1);
            elapsed_pct = 30;
          }
        } else if (s.duration_ms != null) {
          elapsed_display = (s.duration_ms / 1000).toFixed(1);
          elapsed_pct = 100;
        }
        return {
          id: m.id,
          label: s.label || m.label,
          status: s.status || 'pending',
          duration_ms: s.duration_ms,
          duration_display: elapsed_display,
          elapsed_display: elapsed_display,
          elapsed_pct: elapsed_pct,
          error: s.error || null,
        };
      });
    },

    get pipelineProgressPct() {
      if (!this.pipelineTask || !this.pipelineTask.result) return 0;
      return this.pipelineTask.result.progress_pct || 0;
    },

    get pipelineStatus() {
      return (this.pipelineTask && this.pipelineTask.status) || 'pending';
    },

    get pipelineFinalResult() {
      if (!this.pipelineTask || !this.pipelineTask.result) return null;
      const r = this.pipelineTask.result;
      if (r.final_word_count) return { final_word_count: r.final_word_count };
      return null;
    },

    get pipelineElapsedText() {
      const e = (Date.now() - this.pipelineStartTs) / 1000;
      return e < 60 ? e.toFixed(1) + 's' : Math.floor(e/60) + 'm' + Math.floor(e%60) + 's';
    },

    // ─── 任务管理：chapter_pipeline 任务的展开/操作 ───

    toggleTaskDetail(taskId) {
      if (this.expandedTaskIds.includes(taskId)) {
        this.expandedTaskIds = this.expandedTaskIds.filter(id => id !== taskId);
      } else {
        this.expandedTaskIds = [...this.expandedTaskIds, taskId];
      }
    },

    openPipelinePanelForTask(t) {
      // 拿一个 task 对象塞到 pipelineTask + 打开面板
      this.pipelineTask = t;
      this.pipelineStartTs = Date.now() - Math.floor((t.duration_s || 0) * 1000);
      this.showPipelineProgress = true;
      // 若任务还在跑，启轮询
      if (['pending','running'].includes(t.status)) {
        if (this.pipelinePollHandle) clearInterval(this.pipelinePollHandle);
        this.pipelinePollHandle = setInterval(() => this._pollPipelineTask(), 2000);
      }
    },

    getStageLabel(stageId) {
      const m = this.PIPELINE_STAGES_META.find(s => s.id === stageId);
      return m ? m.label : stageId;
    },

    // ─── AI 生成 ───
    async generateText() {
      if (!this.generatePrompt || !this.currentChapter) return;
      this.generating = true;
      this.generatedText = null;
      try {
        const res = await fetch('/api/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_id: this.currentChapter.id,
            prompt: this.generatePrompt,
            mode: this.generateMode,
          }),
        });
        const data = await res.json();
        this.generatedText = data.generated_text;
      } catch (e) { alert('生成失败: ' + e.message); }
      finally { this.generating = false; }
    },

    insertGenerated() {
      if (this.generatedText && this.currentChapter) {
        this.currentChapter.content += '\n\n' + this.generatedText;
        this.onContentChange();
        this.generatedText = null;
        this.showGenerateModal = false;
        this.generatePrompt = '';
        // AI 生成内容自动保存，防止丢失
        this.saveChapter(true);
      }
    },

    pipelineSetupSetupModal() {
      // 同步当前章节：
      // 1. 优先用 currentChapter（用户在侧边栏选中的章节）
      // 2. 否则默认下一章：找到最小未生成的章节序号
      if (this.currentChapter) {
        this.pipelineSetupChapter = this.currentChapter.order + 1;
      } else {
        const orders = this.chapters.map(ch => ch.order + 1).sort((a, b) => a - b);
        let nextChapter = 1;
        for (const n of orders) {
          if (n === nextChapter) nextChapter++;
          else break;
        }
        this.pipelineSetupChapter = nextChapter;
      }
      this.pipelineSetupGuide = '';
      this.showPipelineSetupModal = true;
    },

    // ─── 一键生成设置浮层 ───
    startPipelineFromSetup() {
      const targetChapter = this.pipelineSetupChapter;
      if (!targetChapter || targetChapter < 1) {
        alert('请输入有效的章节序号');
        return;
      }
      // 关闭设置浮层
      this.showPipelineSetupModal = false;

      // 检查目标章节是否已存在且有内容
      const target = this.chapters.find(ch => ch.order + 1 === targetChapter);
      const hasExistingContent = target && (target.content || '').trim().length > 0;

      if (hasExistingContent) {
        // 已有正文：弹出二次确认模态框，暂存引导
        this.currentChapter = target;
        this._pendingPipelineGuide = this.pipelineSetupGuide;
        this.showRegenerateConfirmModal = true;
        this.pipelineSetupGuide = '';
        return;
      }

      // 第一次生成 / 空章节：直接跑流水线
      if (target) {
        this.currentChapter = target;
        // 延迟一帧再启动pipeline，确保currentChapter已更新
        this.$nextTick(() => {
          this.runChapterPipeline(this.pipelineSetupGuide);
        });
      } else {
        // 章节不存在，创建新章节
        this.createChapterWithGuide(targetChapter, this.pipelineSetupGuide);
      }
      // 重置设置
      this.pipelineSetupGuide = '';
    },

    // 确认覆盖已有章节，启动流水线
    confirmRegenerateExisting() {
      this.showRegenerateConfirmModal = false;
      const guide = this._pendingPipelineGuide;
      this._pendingPipelineGuide = '';
      this.$nextTick(() => {
        this.runChapterPipeline(guide);
      });
    },

    // 取消覆盖
    cancelRegenerateExisting() {
      this.showRegenerateConfirmModal = false;
      this._pendingPipelineGuide = '';
    },

    async createChapterWithGuide(chapterNum, guide) {
      try {
        const res = await fetch('/api/projects/' + this.currentProject.id + '/chapters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: '第' + chapterNum + '章',
            order: chapterNum - 1,
          }),
        });
        if (!res.ok) throw new Error('创建章节失败');
        const ch = await res.json();
        this.chapters.push(ch);
        this.currentChapter = ch;
        await this.$nextTick();
        this.runChapterPipeline(guide);
      } catch (e) {
        alert('创建章节失败: ' + e.message);
      }
    },

    // ─── 批量生成 ───
    openBatchGenerateModal() {
      // 同步当前章节：
      // 1. 优先用 currentChapter.order 作为起点（"从当前章节之后开始"）
      // 2. 否则默认从最后一章之后开始
      let start;
      if (this.currentChapter) {
        start = this.currentChapter.order;  // batchGenerateStart 语义是"从第几章之后开始"
      } else {
        start = this.chapters.length > 0
          ? Math.max(...this.chapters.map(ch => ch.order + 1))
          : 0;
      }
      this.batchGenerateStart = start;
      this.batchGenerateCount = 5;
      this.batchGenerateGuide = '';
      this.showBatchGenerateModal = true;
    },

    async startBatchGenerate() {
      if (this.batchGenerating) return;
      if (!this.currentProject) { alert('请先选择项目'); return; }
      if (this.batchGenerateCount < 1) { alert('生成数量至少为 1'); return; }

      // 二次确认
      const startFrom = this.batchGenerateStart + 1;
      const endAt = this.batchGenerateStart + this.batchGenerateCount;
      if (!confirm(`确认批量生成第 ${startFrom} 章到第 ${endAt} 章（共 ${this.batchGenerateCount} 章）？\n\n每章将执行完整的 9 步生成流水线，可能需要较长时间。`)) {
        return;
      }

      this.batchGenerating = true;
      this.showBatchGenerateModal = false;

      try {
        const res = await fetch('/api/chapters/batch-generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            start_chapter: this.batchGenerateStart,
            count: this.batchGenerateCount,
            guide: this.batchGenerateGuide || '',
          }),
        });
        const data = await res.json();
        if (!res.ok || !data.task_id) {
          alert('批量生成提交失败：' + (data.detail || JSON.stringify(data)));
          this.batchGenerating = false;
          return;
        }

        // 启动轮询
        this.batchTask = { id: data.task_id, status: 'pending', result: { batch: true, chapters_status: {} } };
        // 持久化 batch task_id 到 localStorage（页面刷新后可恢复）
        try {
          localStorage.setItem('cozywriter.batchTask', JSON.stringify({
            id: data.task_id,
            project_id: this.currentProject.id,
            start_chapter: this.batchGenerateStart,
            count: this.batchGenerateCount,
            started_at: Date.now(),
          }));
        } catch (e) { /* localStorage may be disabled */ }
        this.startBatchPolling();

      } catch (e) {
        alert('批量生成提交失败：' + e.message);
        this.batchGenerating = false;
      }
    },

    startBatchPolling() {
      if (this.batchPollHandle) clearInterval(this.batchPollHandle);
      this.batchPollHandle = setInterval(async () => {
        try {
          const res = await fetch('/api/tasks/' + this.batchTask.id);
          const data = await res.json();
          this.batchTask = data;

          if (['completed', 'failed', 'cancelled'].includes(data.status)) {
            clearInterval(this.batchPollHandle);
            this.batchPollHandle = null;
            this.batchGenerating = false;
            // 任务终结：清掉 localStorage
            try { localStorage.removeItem('cozywriter.batchTask'); } catch (e) {}

            if (this.currentProject) {
              await this.loadChapters(this.currentProject.id);
            }

            if (data.status === 'completed') {
              const r = data.result || {};
              const failed = r.failed_chapters || [];
              if (failed.length > 0) {
                alert(`批量生成完成，但第 ${failed.join(', ')} 章生成失败。`);
              } else {
                alert(`批量生成完成！共生成 ${r.completed_chapters || '?'} 章。`);
              }
            } else if (data.status === 'failed') {
              alert('批量生成失败：' + (data.error || '未知错误'));
            }
          }
        } catch (e) {
          console.error('Batch poll error:', e);
        }
      }, 2000);
    },

    cancelBatchGenerate() {
      if (this.batchPollHandle) {
        clearInterval(this.batchPollHandle);
        this.batchPollHandle = null;
      }
      this.batchGenerating = false;
      this.batchTask = null;
      try { localStorage.removeItem('cozywriter.batchTask'); } catch (e) {}
    },

    get batchProgressInfo() {
      const r = (this.batchTask && this.batchTask.result) || {};
      if (!r.batch) return null;
      return {
        total: r.total_chapters || 0,
        completed: r.completed_chapters || 0,
        currentIndex: r.current_chapter_index || 0,
        currentOrder: r.current_chapter_order || 0,
        chaptersStatus: r.chapters_status || {},
        pipelineStages: r.current_pipeline_stages || {},
      };
    },

    // 伏笔筛选：按状态过滤（全部 / 待开始 / 进行中 / 已回收 / 已废弃）
    get filteredForeshadowings() {
      const f = this.foreshadowingFilter;
      if (f === 'all' || !f) return this.foreshadowings;
      return this.foreshadowings.filter(item => item.status === f);
    },

    get batchPipelineStagesView() {
      const info = this.batchProgressInfo;
      if (!info) return [];
      const meta = this.PIPELINE_STAGES_META;
      return meta.map(m => {
        const s = info.pipelineStages[m.id] || {};
        return {
          id: m.id,
          label: s.label || m.label,
          status: s.status || 'pending',
          duration_ms: s.duration_ms,
        };
      });
    },

    // ─── 修订功能 ───
    confirmRevise() {
      if (!this.currentChapter || !this.currentChapter.content) {
        alert('当前章节没有正文内容，无法修订');
        return;
      }
      this.showReviseConfirmModal = true;
    },

    async runRevise() {
      this.showReviseConfirmModal = false;
      try {
        const res = await fetch('/api/chapters/revise', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_id: this.currentChapter.id,
          }),
        });
        const data = await res.json();
        if (!res.ok) {
          alert('修订失败：' + (data.detail || JSON.stringify(data)));
          return;
        }
        if (data.task_id) {
          // 打开任务管理面板并刷新
          this.showTaskManager = true;
          await this.refreshAllTasks();
          // 启动轮询
          if (this._taskPollHandle) clearInterval(this._taskPollHandle);
          this._taskPollHandle = setInterval(() => {
            if (this.showTaskManager) this.refreshAllTasks();
          }, 3000);
        }
      } catch (e) {
        alert('修订请求失败: ' + e.message);
      }
    },

    // ─── 字数调整（独立功能，只动字数）───
    openWordAdjustModal() {
      if (!this.currentChapter || !this.currentChapter.content) {
        alert('当前章节没有正文内容，无法调整字数');
        return;
      }
      // 初始化自定义输入框为项目默认值
      this.wordAdjustUseCustom = false;
      this.wordAdjustCustomMin = this.currentProject.word_count_min || null;
      this.wordAdjustCustomTarget = this.currentProject.target_word_count || null;
      this.wordAdjustCustomMax = this.currentProject.word_count_max || null;
      this.recalcWordAdjustPlan();
      this.wordAdjustTaskId = null;
      this.wordAdjustSubmitting = false;
      this.showWordAdjustModal = true;
    },

    // 用当前 useCustom + min/target/max 重算 plan
    recalcWordAdjustPlan() {
      if (!this.currentChapter) return;
      const currentChars = this.currentChapter.word_count || 0;
      let minW, maxW;
      if (this.wordAdjustUseCustom) {
        // 自定义模式：使用手输值（fallback 到项目默认）
        minW = Number(this.wordAdjustCustomMin) || this.currentProject.word_count_min || 0;
        maxW = Number(this.wordAdjustCustomMax) || this.currentProject.word_count_max || 0;
      } else {
        minW = this.currentProject.word_count_min || 0;
        maxW = this.currentProject.word_count_max || 0;
      }
      if (minW > maxW) [minW, maxW] = [maxW, minW];
      let plan;
      if (currentChars > maxW) {
        plan = { action: 'compress', delta: currentChars - maxW, min: minW, max: maxW };
      } else if (currentChars < minW) {
        plan = { action: 'expand', delta: minW - currentChars, min: minW, max: maxW };
      } else {
        plan = { action: 'none', delta: 0, min: minW, max: maxW };
      }
      this.wordAdjustPlan = plan;
    },

    // 按目标字数的 ±百分比 重新计算 min/target/max，自动启用自定义
    applyWordAdjustPctPreset(pct) {
      if (!pct || pct <= 0 || pct >= 100) {
        alert('百分比必须在 1-99 之间');
        return;
      }
      // 基准值：先看输入框里的 target，再看项目的 target
      const baseTarget = Number(this.wordAdjustCustomTarget)
        || this.currentProject.target_word_count
        || 3000;
      const delta = Math.round(baseTarget * pct / 100);
      const newMin = Math.max(0, baseTarget - delta);
      const newMax = baseTarget + delta;
      // 启用自定义模式 + 写入输入框
      this.wordAdjustUseCustom = true;
      this.wordAdjustCustomMin = newMin;
      this.wordAdjustCustomTarget = baseTarget;
      this.wordAdjustCustomMax = newMax;
      this.wordAdjustPctInput = pct;
      this.recalcWordAdjustPlan();
    },

    closeWordAdjustModal() {
      if (this.wordAdjustSubmitting) {
        alert('调整进行中，请等待完成');
        return;
      }
      this.showWordAdjustModal = false;
      this.wordAdjustPlan = null;
    },

    async runWordAdjust() {
      if (!this.wordAdjustPlan || this.wordAdjustPlan.action === 'none') return;
      if (this.wordAdjustSubmitting) return;
      this.wordAdjustSubmitting = true;
      try {
        // 收集自定义上下限
        const body = {
          project_id: this.currentProject.id,
          chapter_id: this.currentChapter.id,
        };
        if (this.wordAdjustUseCustom) {
          if (this.wordAdjustCustomMin != null && this.wordAdjustCustomMin !== '')
            body.min_words = Number(this.wordAdjustCustomMin);
          if (this.wordAdjustCustomMax != null && this.wordAdjustCustomMax !== '')
            body.max_words = Number(this.wordAdjustCustomMax);
          if (this.wordAdjustCustomTarget != null && this.wordAdjustCustomTarget !== '')
            body.target_words = Number(this.wordAdjustCustomTarget);
        }
        const res = await fetch('/api/chapters/adjust-word-count', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok || !data.task_id) {
          alert('字数调整提交失败：' + (data.detail || JSON.stringify(data)));
          this.wordAdjustSubmitting = false;
          return;
        }
        this.wordAdjustTaskId = data.task_id;
        // 打开任务管理面板
        this.showTaskManager = true;
        await this.refreshAllTasks();
        // 启动轮询
        if (this._taskPollHandle) clearInterval(this._taskPollHandle);
        this._taskPollHandle = setInterval(() => {
          this._pollWordAdjust();
          if (this.showTaskManager) this.refreshAllTasks();
        }, 2000);
        // 立即拉一次
        this._pollWordAdjust();
      } catch (e) {
        alert('字数调整请求失败: ' + e.message);
        this.wordAdjustSubmitting = false;
      }
    },

    async _pollWordAdjust() {
      if (!this.wordAdjustTaskId) return;
      try {
        const res = await fetch('/api/tasks/' + this.wordAdjustTaskId);
        if (!res.ok) return;
        const task = await res.json();
        if (['completed', 'failed', 'cancelled'].includes(task.status)) {
          clearInterval(this._taskPollHandle);
          this._taskPollHandle = null;
          this.wordAdjustSubmitting = false;
          if (task.status === 'completed') {
            const r = task.result || {};
            const rangeTag = r.is_custom_range ? '（自定义）' : '（项目默认）';
            if (r.skipped) {
              alert(`当前字数（${r.current_chars}）已在区间 ${r.min_chars}~${r.max_chars} 内${rangeTag}，无需调整。`);
            } else {
              const sign = r.delta >= 0 ? '+' : '';
              alert(
                `字数调整完成！\n\n` +
                `调整前：${r.current_chars} 字\n` +
                `调整后：${r.new_chars} 字（${sign}${r.delta} 字）\n` +
                `目标区间：${r.min_chars} ~ ${r.max_chars} 字${rangeTag}\n` +
                `旧版已存入废纸篓（v${r.version_num}）`
              );
            }
            // 关闭弹窗 + 重新加载章节
            this.showWordAdjustModal = false;
            this.wordAdjustTaskId = null;
            await this.selectChapter(this.currentChapter);
          } else if (task.status === 'failed') {
            alert('字数调整失败：' + (task.error || '未知错误'));
            this.wordAdjustTaskId = null;
          }
        }
      } catch (e) {
        console.warn('[WordAdjust] poll failed:', e);
      }
    },

    // ─── 导出功能 ───
    openExportModal() {
      this.exportChapterIds = this.chapters.map(c => c.id);
      this.exportRechapter = false;
      this.exportWordsPerChapter = 3000;
      this.exportFormat = 'txt';
      this.exportSaveIndividual = false;
      this.showExportModal = true;
    },
    
    toggleExportChapter(chapterId) {
      const idx = this.exportChapterIds.indexOf(chapterId);
      if (idx === -1) {
        this.exportChapterIds.push(chapterId);
      } else {
        this.exportChapterIds.splice(idx, 1);
      }
    },
    
    selectAllExportChapters() {
      this.exportChapterIds = this.chapters.map(c => c.id);
    },
    
    invertExportChapters() {
      this.exportChapterIds = this.chapters
        .filter(c => !this.exportChapterIds.includes(c.id))
        .map(c => c.id);
    },
    
    async doExport() {
      if (this.exportChapterIds.length === 0) {
        alert('请至少选择一个章节');
        return;
      }
      
      try {
        const res = await fetch('/api/export/chapters', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_ids: this.exportChapterIds,
            rechapter: this.exportRechapter,
            words_per_chapter: this.exportWordsPerChapter,
            format: this.exportFormat,
            save_individual: this.exportSaveIndividual,
          }),
        });
        
        if (!res.ok) {
          const err = await res.json();
          alert('导出失败: ' + (err.detail || '未知错误'));
          return;
        }
        
        // 获取文件名
        const disposition = res.headers.get('Content-Disposition');
        let filename = 'export.txt';
        if (disposition) {
          // RFC 5987: filename*=UTF-8''encoded_name
          const rfc5987 = disposition.match(/filename\*=UTF-8''(.+)/i);
          if (rfc5987) {
            filename = decodeURIComponent(rfc5987[1]);
          } else {
            const match = disposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
          }
        }
        
        // 下载文件
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        this.showExportModal = false;
        alert('导出成功！');
      } catch (e) {
        alert('导出失败: ' + e.message);
      }
    },

    // ─── 章节细纲（写作面板 / 大纲面板共用） ───
    async loadChapterOutlines(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/chapter-outlines`);
        this.chapterOutlines = await res.json();
        this.chapterOutlinesMap = {};
        for (const o of this.chapterOutlines) {
          this.chapterOutlinesMap[o.chapter_id] = o;
        }
      } catch (e) { console.error(e); }
    },

    getChapterTrackClass(chapter) {
      const o = this.chapterOutlinesMap[chapter.id];
      const total = this.currentProject.total_chapters;
      if (!total || !o) return 'track-unplanned';
      const progress = (chapter.order + 1) / total;
      if (o.status === 'revised') return 'track-done';
      if (o.status === 'written') return 'track-written';
      if (progress > 0.8) return 'track-late';
      return 'track-planned';
    },

    // ─── 灵感 ───
    async loadInspirations(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/inspirations`);
        this.inspirations = await res.json();
        const tagSet = new Set();
        for (const i of this.inspirations) {
          for (const t of (i.tags || [])) tagSet.add(t);
        }
        this.allInspirationTags = [...tagSet];
      } catch (e) { console.error(e); }
    },

    async saveInspiration() {
      if (!this.currentProject || !this.newInspiration.content) return;
      const tags = (this.newInspiration.tagInput || '').split(',').map(t => t.trim()).filter(Boolean);
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/inspirations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ content: this.newInspiration.content, source: this.newInspiration.source || '', tags }),
        });
        const insp = await res.json();
        this.inspirations.unshift(insp);
        this.newInspiration = { content: '', source: '', tagInput: '' };
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    async deleteInspiration(inspId) {
      if (!confirm('确定删除灵感？')) return;
      try {
        await fetch(`/api/projects/${this.currentProject.id}/inspirations/${inspId}`, { method: 'DELETE' });
        this.inspirations = this.inspirations.filter(i => i.id !== inspId);
      } catch (e) { alert('删除失败: ' + e.message); }
    },

    // ─── 创意问卷 ───
    async loadQuestionnaires() {
      try {
        const res = await fetch('/api/questions');
        this.qQuestions = await res.json();
      } catch (e) { console.error(e); }
      try {
        const res = await fetch('/api/questionnaires');
        this.allQuestionnaires = await res.json();
      } catch (e) { console.error(e); }
    },

    async createNewQuestionnaire() {
      try {
        const res = await fetch('/api/questionnaires', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: '新问卷' }),
        });
        const q = await res.json();
        this.allQuestionnaires.unshift(q);
        this.openQuestionnaire(q);
      } catch (e) { alert('创建失败: ' + e.message); }
    },

    openQuestionnaire(q) {
      this.activeQuestionnaire = q;
      this.qStep = 0;
      this.qAnswers = { ...(q.answers || {}) };
      this.activePanel = 'questionnaire';
      this.currentProject = null;
    },

    answerQuestion(questionId, value) {
      this.qAnswers[questionId] = value;
    },

    nextQuestion() {
      if (this.qStep < this.qQuestions.length - 1) this.qStep++;
    },

    async submitQuestionnaire() {
      try {
        await fetch(`/api/questionnaires/${this.activeQuestionnaire.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ answers: this.qAnswers, status: 'draft' }),
        });
        this.qStep = this.qQuestions.length;
      } catch (e) { alert('保存失败: ' + e.message); }
    },

    async buildProjectFromQuestionnaire() {
      try {
        const res = await fetch(`/api/questionnaires/${this.activeQuestionnaire.id}/build-project`, { method: 'POST' });
        const data = await res.json();
        alert('项目《' + data.project_title + '》创建成功！');
        this.activeQuestionnaire = null;
        this.activePanel = 'writing';
        await this.loadProjects();
        const p = this.projects.find(proj => proj.id === data.project_id);
        if (p) await this.openProject(p);
      } catch (e) { alert('创建项目失败: ' + e.message); }
    },

    startQuestionnaire() {
      this.loadQuestionnaires().then(() => this.createNewQuestionnaire());
    },
  };

}

// Alpine.data() 注册（比 x-data="app()" 字符串求值更可靠）
if (window.Alpine) {
  window.Alpine.data('cozywriterApp', app);
} else {
  document.addEventListener('alpine:init', () => {
    window.Alpine.data('cozywriterApp', app);
  });
}
