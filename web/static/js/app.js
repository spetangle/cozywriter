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
      expandedStageId: null,                // 展开预览的 stage
      pollHandle: null,                     // 轮询句柄
      errorMsg: '',
      startedAt: null,
      completedAt: null,
    },
    // 创建项目表单（12 字段：4 必填 + 8 选填）
    newProjectForm: {
      // 4 必填
      title: '',
      chapter_word_count: 3,
      genre: '',
      description: '',
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

    // 一致性检查
    consistencyResult: null,
    consistencyReport: null,

    // 灵感收集
    inspirations: [],
    inspirationSubPanel: 'list',
    allInspirationTags: [],
    selectedTag: null,
    newInspiration: { content: '', source: '', tagInput: '' },

    // 创意问卷
    activeQuestionnaire: null,
    savedQuestionnaires: [],
    allQuestionnaires: [],
    qStep: 0,
    qAnswers: {},
    qQuestions: [],

    // 大纲/细纲
    outlineSubPanel: 'overview',
    projectOutline: { plot_lines: [], structure: { acts: [] }, pacing_notes: '', outline_text: '' },
    chapterOutlines: [],
    chapterOutlinesMap: {},
    expandedChapterId: null,
    showPlotlineForm: false,
    plotlineForm: { title: '', description: '', from_chapter: 1, to_chapter: 1 },

    // 评审
    reviewSubPanel: 'new',
    reviewHistory: [],
    activeReviewSession: null,
    reviewResult: null,

    // AI 生成
    showGenerateModal: false,
    generateMode: 'continue',
    generatePrompt: '',
    generateWordCount: '3000',
    generating: false,
    generatedText: null,

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
          // 检查是否有进行中的 workflow run，有则自动恢复 wizard
          await this._rehydrateBootstrapIfNeeded();
        } else {
          await this.refreshModelStatus();
        }
      } catch (e) {
        console.error('初始化检查失败:', e);
      }
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

    get activeTaskCount() {
      return this.allTasks.filter((t) => ['pending', 'running'].includes(t.status)).length;
    },

    get completedTaskCount() {
      return this.allTasks.filter((t) => ['completed', 'failed', 'cancelled'].includes(t.status)).length;
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
        description: '',
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
      this.showCreateProjectModal = true;
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
      if (!(f.genre || '').trim()) missing.push('genre');
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

      const payload = this._stripEmptyFields({
        ...f,
        auto_commit: autoCommit,
        async_mode: true,
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

        // 4) failed → 部分失败
        if (status === 'failed' || status === 'partial') {
          const failedCount = stages.filter((s) => s.status === 'failed').length;
          this.bootstrapBanner = {
            visible: true,
            projectId,
            runId: data.run_id,
            kind: 'partial_failed',
            message: `AI 补全部分失败（${failedCount} 个 stage）。可重跑失败项或继续。`,
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
        expandedStageId: null,
        pollHandle: null,
        errorMsg: '',
        startedAt: Date.now(),
        completedAt: null,
      };
      // 立即拉一次
      await this._pollBootstrapStatus();
      // 启动轮询（5s 一次，LLM 慢，给后端留够时间）
      this.bootstrapWizard.pollHandle = setInterval(
        () => this._pollBootstrapStatus(),
        5000
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
        if (data.status === 'committed') {
          wiz.status = 'committed';
          wiz.completedAt = Date.now();
          this._stopBootstrapPolling();
        } else if (data.status === 'failed') {
          wiz.status = 'failed';
          wiz.errorMsg = '有 stage 执行失败';
          this._stopBootstrapPolling();
        } else if (allDone && data.status === 'completed') {
          wiz.status = 'completed';
          wiz.completedAt = Date.now();
          this._stopBootstrapPolling();
        }
      } catch (e) {
        console.error('[Bootstrap poll] failed:', e);
      }
    },

    _stopBootstrapPolling() {
      const wiz = this.bootstrapWizard;
      if (wiz.pollHandle) {
        clearInterval(wiz.pollHandle);
        wiz.pollHandle = null;
      }
    },

    async rerunBootstrapStage(stageId) {
      const wiz = this.bootstrapWizard;
      if (!wiz.runId) return;
      if (!confirm(`确定重新生成 stage「${stageId}」吗？将覆盖之前的结果。`)) return;
      try {
        const res = await fetch(`/api/workflow/run/${wiz.runId}/rerun`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ stage_id: stageId }),
        });
        const data = await res.json();
        if (data.status === 'ok') {
          // 重新拉一次
          await this._pollBootstrapStatus();
        } else {
          alert('重跑失败: ' + (data.error || 'unknown'));
        }
      } catch (e) {
        alert('重跑失败: ' + e.message);
      }
    },

    async commitBootstrap() {
      const wiz = this.bootstrapWizard;
      if (!wiz.runId) return;
      try {
        const res = await fetch(`/api/workflow/run/${wiz.runId}/commit`, {
          method: 'POST',
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
        } else {
          alert('提交失败: ' + (data.error || 'unknown'));
        }
      } catch (e) {
        alert('提交失败: ' + e.message);
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
      await Promise.all([
        this.loadChapters(project.id),
        this.loadCharacters(project.id),
        this.loadThemes(project.id),
        this.loadForeshadowings(project.id),
        this.loadCharacterArcs(project.id),
        this.loadCharacterRelations(project.id),
        this.loadConsistencyReport(project.id),
        this.loadProjectOutline(project.id),
        this.loadChapterOutlines(project.id),
      ]);
      // 检查是否需要显示 AI 补全 banner
      this._maybeShowBootstrapBanner(project.id);
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
            word_count_min: parseInt(this.currentProject.word_count_min) || 2000,
            word_count_max: parseInt(this.currentProject.word_count_max) || 5000,
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

    selectChapter(chapter) {
      this.currentChapter = chapter;
      this.activePanel = 'writing';
    },

    async saveChapter() {
      if (!this.currentChapter) return;
      try {
        const res = await fetch(`/api/chapters/${this.currentChapter.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: this.currentChapter.title,
            content: this.currentChapter.content,
          }),
        });
        const ch = await res.json();
        this.currentChapter = ch;
        // 更新章节列表中的记录
        const idx = this.chapters.findIndex(c => c.id === ch.id);
        if (idx >= 0) this.chapters[idx] = ch;
        // 更新项目总字数
        const total = this.chapters.reduce((s, c) => s + (c.word_count || 0), 0);
        this.currentProject.word_count = total;
      } catch (e) { console.error('保存失败:', e); }
    },

    onContentChange() {
      const text = this.currentChapter?.content || '';
      const chinese = (text.match(/[一-鿿]/g) || []).length;
      const english = (text.match(/[a-zA-Z]+/g) || []).length;
      if (this.currentChapter) {
        this.currentChapter.word_count = chinese + english;
      }
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
        const res = await fetch(`/api/projects/${this.currentProject.id}/reviews`);
        this.reviewHistory = await res.json();
      } catch (e) { console.error(e); }
    },

    async startReview(chapter) {
      this.activeReviewSession = { chapter_id: chapter.id };
      this.reviewResult = null;
      try {
        const res = await fetch('/api/reviews', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            project_id: this.currentProject.id,
            chapter_id: chapter.id,
            session_type: 'chapter',
          }),
        });
        this.reviewResult = await res.json();
        await this.loadReviewHistory();
      } catch (e) { alert('评审失败: ' + e.message); this.activeReviewSession = null; }
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
      }
    },

    // ─── 大纲/细纲 ───
    async loadProjectOutline(projectId) {
      try {
        const res = await fetch(`/api/projects/${projectId}/outline`);
        const data = await res.json();
        if (data && data.id) {
          this.projectOutline = data;
        } else {
          this.projectOutline = { plot_lines: [], structure: { acts: [] }, pacing_notes: '', outline_text: '' };
        }
      } catch (e) { console.error(e); }
    },

    async saveProjectOutline() {
      if (!this.currentProject) return;
      try {
        await fetch(`/api/projects/${this.currentProject.id}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            plot_lines: this.projectOutline.plot_lines || [],
            structure: this.projectOutline.structure || { acts: [] },
            pacing_notes: this.projectOutline.pacing_notes || '',
            outline_text: this.projectOutline.outline_text || '',
          }),
        });
      } catch (e) { console.error('保存大纲失败:', e); }
    },

    async savePlotline() {
      const pl = {
        title: this.plotlineForm.title,
        description: this.plotlineForm.description,
        from_chapter: parseInt(this.plotlineForm.from_chapter) || 1,
        to_chapter: parseInt(this.plotlineForm.to_chapter) || 1,
        priority: 1,
      };
      if (!this.projectOutline.plot_lines) this.projectOutline.plot_lines = [];
      this.projectOutline.plot_lines.push(pl);
      this.showPlotlineForm = false;
      this.plotlineForm = { title: '', description: '', from_chapter: 1, to_chapter: 1 };
      await this.saveProjectOutline();
    },

    async addAct() {
      const acts = this.projectOutline.structure.acts || [];
      const name = prompt('请输入段落/幕名称（如：第一幕）:');
      if (!name) return;
      const fromCh = parseInt(prompt('起始章节:', '1')) || 1;
      const toCh = parseInt(prompt('结束章节:', String(this.currentProject.total_chapters || 10))) || 10;
      acts.push({ name, from_chapter: fromCh, to_chapter: toCh });
      this.projectOutline.structure.acts = acts;
      await this.saveProjectOutline();
    },

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

    async createChapterOutline(chapter) {
      try {
        const res = await fetch(`/api/projects/${this.currentProject.id}/chapters/${chapter.id}/outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chapter_id: chapter.id,
            target_word_count: this.currentProject.target_word_count || 3000,
            min_word_count: this.currentProject.word_count_min || 2000,
            max_word_count: this.currentProject.word_count_max || 5000,
          }),
        });
        const outline = await res.json();
        this.chapterOutlines.push(outline);
        this.chapterOutlinesMap[chapter.id] = outline;
        this.expandedChapterId = chapter.id;
      } catch (e) { alert('创建失败: ' + e.message); }
    },

    async saveChapterOutline(chapterId) {
      const outline = this.chapterOutlinesMap[chapterId];
      if (!outline) return;
      try {
        await fetch(`/api/projects/${this.currentProject.id}/chapters/${chapterId}/outline`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(outline),
        });
      } catch (e) { console.error('保存失败:', e); }
    },

    toggleChapterOutline(chapterId) {
      this.expandedChapterId = this.expandedChapterId === chapterId ? null : chapterId;
    },

    getChapterOutlineStatus(chapterId) {
      const o = this.chapterOutlinesMap[chapterId];
      if (!o) return 'none';
      const map = { planning: '规划中', written: '已写', revised: '已修订' };
      return map[o.status] || '规划中';
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