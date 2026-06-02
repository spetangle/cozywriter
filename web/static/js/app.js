// CozyWriter Alpine.js 主应用

function app() {
  return {
    // ─── State ───
    showSetupWizard: false,
    setupStep: 2,
    selectedProvider: null,
    providerConfig: { apiKey: '', baseUrl: 'http://localhost:11434' },
    modelStatus: { model_name: '', downloaded: false, cache_size_mb: null },
    downloading: false,

    showSettings: false,
    showProjectSettings: false,
    settings: { defaultProvider: 'anthropic' },

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
        } else {
          await this.refreshModelStatus();
        }
      } catch (e) {
        console.error('初始化检查失败:', e);
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
      this.downloading = true;
      try {
        await fetch('/api/models/download', { method: 'POST' });
        await this.refreshModelStatus();
      } catch (e) { alert('下载失败: ' + e.message); }
      finally { this.downloading = false; }
    },

    finishSetup() {
      this.showSetupWizard = false;
      this.loadProjects();
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