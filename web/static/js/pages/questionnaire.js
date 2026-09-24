// 创意问卷页面：分步问卷 wizard + 创意池（已保存草稿）+ 题材标签
document.addEventListener('alpine:init', () => {
Alpine.data('questionnaire', () => ({
    // ─── 视图模式 ───
    // 'pool'   : 创意池（已保存的问卷草稿列表）
    // 'wizard' : 分步问卷进行中
    view: 'pool',

    // ─── 创意池 ───
    savedQuestionnaires: [],
    poolLoading: false,
    selectedIds: [],
    selectAll: false,

    // ─── 题材 ───
    genreList: [],

    // ─── 分步问卷状态 ───
    q: {
        id: null,
        currentStep: 0,
        totalSteps: 0,
        currentQuestion: null,
        answers: {},
        customAnswer: '',
        isCompleted: false,
        aiCompletedAnswers: {},
        isAiCompleting: false,
        isGeneratingOptions: false,
        isNavigating: false,
        hasUnsavedChanges: false,
        lastFocus: null,
    },
    // 题材标签步骤的选中项
    selectedGenreTags: [],
    customGenreInput: '',
    // 多选步骤的选中项（step_multiselect）
    selectedMultiOptions: [],
    building: false,

    init() {
        this.loadGenres();
        this.loadPool();
    },

    // ═══════════ 题材 ═══════════

    async loadGenres() {
        try {
            const res = await fetch('/api/genres');
            if (res.ok) this.genreList = await res.json();
        } catch (e) {
            console.error('加载题材失败:', e);
        }
    },

    async addCustomGenre() {
        const name = (this.customGenreInput || '').trim();
        if (!name) return;
        // 已存在则直接选中
        const exist = this.genreList.find(g => g.name === name);
        if (exist) {
            if (!this.selectedGenreTags.includes(exist.name)) {
                this.selectedGenreTags.push(exist.name);
            }
            this.customGenreInput = '';
            return;
        }
        try {
            const res = await fetch('/api/genres', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name }),
            });
            if (res.ok) {
                const g = await res.json();
                this.genreList.push(g);
                this.selectedGenreTags.push(g.name);
                this.customGenreInput = '';
            } else {
                Alpine.store('app').toast('添加题材失败', 'error');
            }
        } catch (e) {
            Alpine.store('app').toast('添加题材失败: ' + e.message, 'error');
        }
    },

    toggleGenreTag(name) {
        const idx = this.selectedGenreTags.indexOf(name);
        if (idx >= 0) this.selectedGenreTags.splice(idx, 1);
        else this.selectedGenreTags.push(name);
        this.q.hasUnsavedChanges = true;
    },

    isGenreSelected(name) {
        return this.selectedGenreTags.includes(name);
    },

    // ═══════════ 创意池 ═══════════

    async loadPool() {
        this.poolLoading = true;
        try {
            const res = await fetch('/api/questionnaires');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const all = await res.json();
            this.savedQuestionnaires = all
                .filter(q => q.status !== 'completed' && !q.created_project_id)
                .sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0));
        } catch (e) {
            console.error('加载创意池失败:', e);
            this.savedQuestionnaires = [];
        } finally {
            this.poolLoading = false;
        }
    },

    backToPool() {
        this.view = 'pool';
        this.resetWizard();
        this.loadPool();
    },

    toggleSelection(id) {
        const idx = this.selectedIds.indexOf(id);
        if (idx > -1) this.selectedIds.splice(idx, 1);
        else this.selectedIds.push(id);
        this.syncSelectAll();
    },

    toggleSelectAll() {
        if (this.selectAll) {
            this.selectedIds = this.savedQuestionnaires.map(q => q.id);
        } else {
            this.selectedIds = [];
        }
    },

    syncSelectAll() {
        this.selectAll = this.savedQuestionnaires.length > 0 &&
            this.selectedIds.length === this.savedQuestionnaires.length;
    },

    clearSelection() {
        this.selectedIds = [];
        this.selectAll = false;
    },

    async deleteQuestionnaire(id) {
        if (!confirm('确定删除这个创意吗？删除后无法恢复。')) return;
        try {
            const res = await fetch(`/api/questionnaires/${id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await this.loadPool();
            this.clearSelection();
            Alpine.store('app').toast('创意已删除', 'success');
        } catch (e) {
            Alpine.store('app').toast('删除失败: ' + e.message, 'error');
        }
    },

    async batchDelete() {
        const count = this.selectedIds.length;
        if (count === 0) return;
        if (!confirm(`确定删除选中的 ${count} 个创意吗？删除后无法恢复。`)) return;
        try {
            const res = await fetch('/api/questionnaires/batch/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ids: this.selectedIds }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await this.loadPool();
            this.clearSelection();
            Alpine.store('app').toast(`已删除 ${count} 个创意`, 'success');
        } catch (e) {
            Alpine.store('app').toast('批量删除失败: ' + e.message, 'error');
        }
    },

    // ═══════════ 分步问卷 ═══════════

    resetWizard() {
        this.q = {
            id: null,
            currentStep: 0,
            totalSteps: 0,
            currentQuestion: null,
            answers: {},
            customAnswer: '',
            isCompleted: false,
            aiCompletedAnswers: {},
            isAiCompleting: false,
            isGeneratingOptions: false,
            isNavigating: false,
            hasUnsavedChanges: false,
            lastFocus: null,
        };
        this.selectedGenreTags = [];
        this.customGenreInput = '';
        this.selectedMultiOptions = [];
    },

    async startNew() {
        try {
            const res = await fetch('/api/questionnaires', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: '新问卷' }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            await this.enterWizard(data.id);
        } catch (e) {
            Alpine.store('app').toast('创建问卷失败: ' + e.message, 'error');
        }
    },

    async continueQuestionnaire(id) {
        await this.enterWizard(id);
    },

    async enterWizard(id) {
        if (this.genreList.length === 0) await this.loadGenres();
        this.resetWizard();
        this.q.id = id;
        this.view = 'wizard';
        await this.loadCurrentStep();
    },

    async loadCurrentStep() {
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/current-step`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.applyStepData(data);
        } catch (e) {
            console.error('加载步骤失败:', e);
            Alpine.store('app').toast('加载问卷步骤失败: ' + e.message, 'error');
        }
    },

    // 统一处理后端返回的 StepResponse
    applyStepData(data) {
        this.q.currentStep = data.current_step;
        this.q.totalSteps = data.total_steps;
        this.q.answers = data.answers || {};
        this.q.isCompleted = data.is_completed;
        this.q.customAnswer = '';
        this.q.currentQuestion = data.question ? JSON.parse(JSON.stringify(data.question)) : null;

        const type = this.q.currentQuestion?.type;
        const qid = this.q.currentQuestion?.id;

        // 回填题材标签步骤
        if (type === 'step_multiselect_tags') {
            const raw = this.q.answers[qid] || '';
            this.selectedGenreTags = raw ? String(raw).split(',').map(s => s.trim()).filter(Boolean) : [];
        } else {
            this.selectedGenreTags = [];
        }

        // 回填多选步骤
        if (type === 'step_multiselect') {
            const raw = this.q.answers[qid] || '';
            this.selectedMultiOptions = raw ? String(raw).split(',').map(s => s.trim()).filter(Boolean) : [];
        } else {
            this.selectedMultiOptions = [];
        }
    },

    selectOption(value) {
        if (!this.q.currentQuestion) return;
        this.q.answers[this.q.currentQuestion.id] = value;
        this.q.hasUnsavedChanges = true;
        this.q.lastFocus = 'option';
    },

    toggleMultiOption(value) {
        const idx = this.selectedMultiOptions.indexOf(value);
        if (idx >= 0) this.selectedMultiOptions.splice(idx, 1);
        else this.selectedMultiOptions.push(value);
        this.q.hasUnsavedChanges = true;
    },

    isMultiSelected(value) {
        return this.selectedMultiOptions.includes(value);
    },

    isOptionSelected(value) {
        return this.q.currentQuestion &&
            this.q.answers[this.q.currentQuestion.id] === value;
    },

    markUnsaved() {
        this.q.hasUnsavedChanges = true;
    },

    async nextStep() {
        const cq = this.q.currentQuestion;
        if (!cq) return;
        if (cq.type === 'step_summary') return;

        const qid = cq.id;
        let answer;
        let isCustom = false;

        if (cq.type === 'step_multiselect_tags') {
            answer = this.selectedGenreTags.join(',');
        } else if (cq.type === 'step_multiselect') {
            answer = this.selectedMultiOptions.join(',');
        } else {
            const custom = (this.q.customAnswer || '').trim();
            if (this.q.lastFocus === 'custom' && custom) {
                answer = custom;
                isCustom = true;
            } else {
                answer = this.q.answers[qid];
            }
        }

        if (!answer && cq.required) {
            Alpine.store('app').toast('请先选择或输入答案', 'warning');
            return;
        }

        this.q.isNavigating = true;
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/answer-step`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question_id: qid, answer: answer || '', is_custom: isCustom }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.applyStepData(data);
            this.q.lastFocus = null;
            this.q.hasUnsavedChanges = false;
        } catch (e) {
            Alpine.store('app').toast('提交答案失败: ' + e.message, 'error');
        } finally {
            this.q.isNavigating = false;
        }
    },

    async prevStep() {
        if (this.q.currentStep <= 0) return;
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/prev-step`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.applyStepData(data);
        } catch (e) {
            Alpine.store('app').toast('后退失败: ' + e.message, 'error');
        }
    },

    async skipToAi() {
        if (this.q.isAiCompleting) return;
        if (!confirm('确定让 AI 补全剩余设定吗？补全后将直接跳转到书名选择。')) return;

        this.q.isAiCompleting = true;
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/skip-to-ai`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.q.aiCompletedAnswers = data.ai_answers || {};
            await this.loadCurrentStep();
        } catch (e) {
            Alpine.store('app').toast('AI 补全失败: ' + e.message, 'error');
        } finally {
            this.q.isAiCompleting = false;
        }
    },

    async generateLlmOptions() {
        if (!this.q.currentQuestion || this.q.isGeneratingOptions) return;
        this.q.isGeneratingOptions = true;
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/generate-llm-options`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            if (data.llm_options && data.llm_options.length > 0 && this.q.currentQuestion) {
                this.q.currentQuestion.options = [...data.llm_options];
            }
        } catch (e) {
            Alpine.store('app').toast('AI 生成选项失败: ' + e.message, 'error');
        } finally {
            this.q.isGeneratingOptions = false;
        }
    },

    async saveProgress() {
        if (!this.q.id) return;
        try {
            const qid = this.q.currentQuestion?.id;
            let answer;

            if (qid && this.q.currentQuestion?.type === 'step_multiselect_tags') {
                answer = this.selectedGenreTags.join(',');
            } else if (qid && this.q.currentQuestion?.type === 'step_multiselect') {
                answer = this.selectedMultiOptions.join(',');
            } else if (qid && this.q.lastFocus === 'custom') {
                answer = (this.q.customAnswer || '').trim();
            } else if (qid) {
                answer = this.q.answers[qid];
            }

            if (qid && answer) {
                await fetch(`/api/questionnaires/${this.q.id}/answer-step`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        question_id: qid,
                        answer,
                        current_step: this.q.currentStep,
                    }),
                });
            }

            await fetch(`/api/questionnaires/${this.q.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ current_step: this.q.currentStep }),
            });

            this.q.hasUnsavedChanges = false;
            Alpine.store('app').toast('问卷进度已保存', 'success');
        } catch (e) {
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        }
    },

    async exitWizard() {
        if (this.q.hasUnsavedChanges) {
            const save = confirm('当前有未保存的问卷进度，是否保存后退出？\n\n点击「确定」：保存并退出\n点击「取消」：不保存，直接退出（草稿保留）');
            if (save) await this.saveProgress();
        }
        this.backToPool();
    },

    async buildProject() {
        if (!this.q.id || this.building) return;
        this.building = true;
        try {
            const res = await fetch(`/api/questionnaires/${this.q.id}/build-project`, {
                method: 'POST',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            Alpine.store('app').toast('项目创建成功', 'success');
            this.resetWizard();
            if (data.project_id) {
                Alpine.store('app').navigate(`/project/${data.project_id}/novel`);
            } else {
                Alpine.store('app').navigate('/');
            }
        } catch (e) {
            Alpine.store('app').toast('创建项目失败: ' + e.message, 'error');
        } finally {
            this.building = false;
        }
    },

    // ═══════════ 工具 ═══════════

    get stepPercent() {
        if (!this.q.totalSteps) return 0;
        return Math.round((this.q.currentStep / this.q.totalSteps) * 100);
    },

    get answeredCount() {
        return Object.keys(this.q.answers || {}).length;
    },

    poolSummary(q) {
        const a = q.answers || {};
        return a.theme || a.core_hook || a.novel_title || '暂无描述';
    },

    formatDateTime(dt) {
        if (!dt) return '';
        const d = new Date(dt);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('questionnaire', `
<div class="page questionnaire-page">

  <!-- ══════════ 创意池 ══════════ -->
  <template x-if="view === 'pool'">
    <div>
      <div class="page-header">
        <h1>🎯 创意池</h1>
        <button class="btn-primary" @click="startNew()">✨ 新建创意问卷</button>
      </div>

      <template x-if="poolLoading">
        <div class="page-loading"><div class="spinner"></div><p>加载中...</p></div>
      </template>

      <!-- 批量操作栏 -->
      <div class="creative-pool-batch-bar" x-show="!poolLoading && selectedIds.length > 0">
        <span>已选择 <strong x-text="selectedIds.length"></strong> 项</span>
        <div class="batch-actions">
          <button class="btn-small" @click="clearSelection()">取消选择</button>
          <button class="btn-small btn-danger" @click="batchDelete()">🗑️ 批量删除</button>
        </div>
      </div>

      <!-- 列表头 -->
      <div class="creative-pool-header" x-show="!poolLoading && savedQuestionnaires.length > 0">
        <label class="select-all-checkbox">
          <input type="checkbox" x-model="selectAll" @change="toggleSelectAll()"> 全选
        </label>
        <span class="creative-pool-count" x-text="'共 ' + savedQuestionnaires.length + ' 项'"></span>
      </div>

      <!-- 列表 -->
      <div class="creative-pool-scroll" x-show="!poolLoading && savedQuestionnaires.length > 0">
        <template x-for="item in savedQuestionnaires" :key="item.id">
          <div class="creative-pool-item" :class="{ selected: selectedIds.includes(item.id) }">
            <input type="checkbox" class="creative-pool-checkbox"
                   :checked="selectedIds.includes(item.id)"
                   @change="toggleSelection(item.id)">
            <div class="creative-pool-info">
              <div class="creative-pool-title-row">
                <h4 x-text="item.title || '未命名创意'"></h4>
                <span class="project-genre-tag" x-show="item.answers && item.answers.genre" x-text="item.answers.genre"></span>
              </div>
              <p class="creative-pool-desc" x-text="poolSummary(item)"></p>
              <div class="creative-pool-meta">
                <span>📊 <span x-text="'第 ' + (item.current_step + 1) + ' 步'"></span></span>
                <span>📝 <span x-text="'已回答 ' + Object.keys(item.answers || {}).length + ' 题'"></span></span>
                <span>📅 <span x-text="formatDateTime(item.updated_at)"></span></span>
              </div>
            </div>
            <div class="creative-pool-actions">
              <button class="btn-small btn-primary" @click="continueQuestionnaire(item.id)">📝 继续问卷</button>
              <button class="btn-small btn-danger" @click="deleteQuestionnaire(item.id)">🗑️ 删除</button>
            </div>
          </div>
        </template>
      </div>

      <!-- 空状态 -->
      <template x-if="!poolLoading && savedQuestionnaires.length === 0">
        <div class="empty">
          <p>📭 暂无创意草稿，点击右上角「新建创意问卷」开始</p>
        </div>
      </template>
    </div>
  </template>

  <!-- ══════════ 分步问卷 wizard ══════════ -->
  <template x-if="view === 'wizard'">
    <div class="step-q-page">
      <div class="page-header">
        <h1>🎯 创意问卷</h1>
        <div class="step-q-header-actions">
          <button class="btn-secondary" @click="saveProgress()">💾 保存进度</button>
          <button class="btn-danger step-q-exit-btn" @click="exitWizard()">✕ 退出问卷</button>
        </div>
      </div>

      <div class="step-q-container">
        <!-- 进度条 -->
        <div class="step-q-progress">
          <div class="step-q-progress-bar">
            <div class="step-q-progress-fill" :style="'width: ' + stepPercent + '%'"></div>
          </div>
          <div class="step-q-progress-text" x-text="'第 ' + (q.currentStep + 1) + ' / ' + q.totalSteps + ' 步'"></div>
        </div>

        <!-- 必填提示 -->
        <div class="step-q-required-hint"
             x-show="q.currentQuestion && q.currentQuestion.required && q.currentQuestion.type !== 'step_summary'">
          <span class="step-q-required-star">*</span> 必填项
        </div>

        <!-- ───── 汇总步骤 ───── -->
        <template x-if="q.currentQuestion && q.currentQuestion.type === 'step_summary'">
          <div class="step-q-summary">
            <div class="step-q-summary-header">
              <div class="step-q-summary-icon">📋</div>
              <h3>问卷信息汇总</h3>
              <p>请确认以下设定，确认无误后点击「创建小说项目」</p>
            </div>
            <div class="step-q-summary-content">
              <div class="step-q-summary-section">
                <h4>📖 基本信息</h4>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">小说名称</span>
                  <span class="step-q-summary-value" x-text="q.answers['novel_title'] || '未命名'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">题材</span>
                  <span class="step-q-summary-value" x-text="q.answers['genre'] || '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">核心主题</span>
                  <span class="step-q-summary-value" x-text="q.answers['theme'] || '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">核心看点</span>
                  <span class="step-q-summary-value" x-text="q.answers['core_hook'] || '未选择'"></span>
                </div>
              </div>
              <div class="step-q-summary-section">
                <h4>🎭 人物设定</h4>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">主角</span>
                  <span class="step-q-summary-value" x-text="q.answers['protagonist'] || '未设定'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">主角姓名</span>
                  <span class="step-q-summary-value" x-text="q.answers['protagonist_name'] || '未设定'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">反派</span>
                  <span class="step-q-summary-value" x-text="q.answers['antagonist'] || '未设定'"></span>
                </div>
              </div>
              <div class="step-q-summary-section">
                <h4>🌍 世界设定</h4>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">世界观</span>
                  <span class="step-q-summary-value" x-text="q.answers['world_setting'] || '未设定'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">社会结构</span>
                  <span class="step-q-summary-value" x-text="q.answers['society_structure'] || '未设定'"></span>
                </div>
              </div>
              <div class="step-q-summary-section">
                <h4>✍️ 写作风格</h4>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">基调</span>
                  <span class="step-q-summary-value" x-text="q.answers['tone'] || '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">每章字数</span>
                  <span class="step-q-summary-value" x-text="q.answers['chapter_word_count'] ? q.answers['chapter_word_count'] + '字' : '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">总章节数</span>
                  <span class="step-q-summary-value" x-text="q.answers['total_chapters'] ? q.answers['total_chapters'] + '章' : '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">文笔风格</span>
                  <span class="step-q-summary-value" x-text="q.answers['style'] || '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">节奏偏好</span>
                  <span class="step-q-summary-value" x-text="q.answers['pacing'] || '未选择'"></span>
                </div>
                <div class="step-q-summary-item">
                  <span class="step-q-summary-label">CP 设定</span>
                  <span class="step-q-summary-value" x-text="q.answers['romance_type'] || '未选择'"></span>
                </div>
              </div>
            </div>
            <div class="step-q-nav">
              <button class="btn-secondary step-q-nav-btn" @click="prevStep()">← 返回修改</button>
              <button class="btn-primary step-q-nav-btn" @click="buildProject()" :disabled="building">
                <span x-show="!building">🎯 创建小说项目</span>
                <span x-show="building">⏳ 创建中...</span>
              </button>
            </div>
          </div>
        </template>

        <!-- ───── 问卷进行中 ───── -->
        <template x-if="!q.isCompleted && q.currentQuestion && q.currentQuestion.type !== 'step_summary'">
          <div class="step-q-content">
            <div class="step-q-question">
              <span class="step-q-question-number" x-text="'Q' + (q.currentStep + 1)"></span>
              <h3 x-text="q.currentQuestion.question"></h3>
            </div>

            <!-- 题材标签多选 -->
            <div x-show="q.currentQuestion.type === 'step_multiselect_tags'" class="step-q-choice-container">
              <div class="genre-tags-grid">
                <template x-for="g in genreList" :key="g.id">
                  <button type="button" class="genre-tag-option"
                          :class="{ selected: isGenreSelected(g.name) }"
                          @click="toggleGenreTag(g.name)"
                          x-text="g.name"></button>
                </template>
              </div>
              <div class="genre-custom-row">
                <input type="text" x-model="customGenreInput"
                       placeholder="自定义新题材后回车"
                       @keydown.enter.prevent="addCustomGenre()">
                <button class="btn-small" @click="addCustomGenre()" title="添加题材">+</button>
              </div>
            </div>

            <!-- 普通多选 -->
            <div x-show="q.currentQuestion.type === 'step_multiselect'" class="step-q-choice-container">
              <div class="step-q-options">
                <template x-for="opt in (q.currentQuestion.options || [])" :key="opt.value">
                  <div class="step-q-option" :class="{ selected: isMultiSelected(opt.value) }"
                       @click="toggleMultiOption(opt.value)">
                    <span class="step-q-option-label" x-text="opt.label"></span>
                    <span class="step-q-option-desc" x-text="opt.description"></span>
                  </div>
                </template>
              </div>
              <div class="step-q-llm-options" x-show="q.currentQuestion.llm_enabled">
                <button class="btn-secondary btn-small step-q-llm-btn" @click="generateLlmOptions()" :disabled="q.isGeneratingOptions">
                  ✨ 换一批选项（AI）
                </button>
              </div>
              <div class="step-q-llm-loading" x-show="q.isGeneratingOptions">
                <span class="step-q-loading-spinner">⏳</span> AI 正在根据您的设定生成选项...
              </div>
            </div>

            <!-- 单选 -->
            <div x-show="q.currentQuestion.type === 'step_choice' || q.currentQuestion.type === 'text_input'" class="step-q-choice-container">
              <div class="step-q-options">
                <template x-for="opt in (q.currentQuestion.options || [])" :key="opt.value">
                  <div class="step-q-option" :class="{ selected: isOptionSelected(opt.value) }"
                       @click="selectOption(opt.value)">
                    <span class="step-q-option-label" x-text="opt.label"></span>
                    <span class="step-q-option-desc" x-text="opt.description"></span>
                  </div>
                </template>
              </div>
              <div class="step-q-llm-options" x-show="q.currentQuestion.llm_enabled">
                <button class="btn-secondary btn-small step-q-llm-btn" @click="generateLlmOptions()" :disabled="q.isGeneratingOptions">
                  ✨ 换一批选项（AI）
                </button>
              </div>
              <div class="step-q-llm-loading" x-show="q.isGeneratingOptions">
                <span class="step-q-loading-spinner">⏳</span> AI 正在根据您的设定生成选项...
              </div>
            </div>

            <!-- 自定义输入 -->
            <div class="step-q-custom" x-show="q.currentQuestion && q.currentQuestion.custom_input && q.currentQuestion.type !== 'step_multiselect_tags'">
              <label>自定义答案</label>
              <textarea x-show="q.currentQuestion.custom_input.type === 'textarea'"
                        x-model="q.customAnswer"
                        :placeholder="q.currentQuestion.custom_input.placeholder"
                        rows="2"
                        @focus="q.lastFocus = 'custom'"
                        @input="markUnsaved()"></textarea>
              <input x-show="q.currentQuestion.custom_input.type !== 'textarea'"
                     type="text"
                     x-model="q.customAnswer"
                     :placeholder="q.currentQuestion.custom_input.placeholder"
                     @focus="q.lastFocus = 'custom'"
                     @input="markUnsaved()"
                     @keydown.enter="nextStep()">
            </div>

            <!-- 导航按钮 -->
            <div class="step-q-nav">
              <button class="btn-secondary step-q-nav-btn" @click="prevStep()"
                      :disabled="q.currentStep <= 0 || q.isAiCompleting">
                ← 返回上一步
              </button>
              <button class="btn-primary step-q-nav-btn step-q-next-btn" @click="nextStep()"
                      :disabled="q.isNavigating || q.isAiCompleting">
                <span x-show="q.isNavigating">⏳ 正在处理...</span>
                <span x-show="!q.isNavigating">下一项 →</span>
              </button>
              <button class="btn-primary step-q-nav-btn step-q-ai-btn" @click="skipToAi()" :disabled="q.isAiCompleting">
                <span x-show="q.isAiCompleting">⏳ AI 正在补全...</span>
                <span x-show="!q.isAiCompleting">✨ AI 一键补全</span>
              </button>
            </div>
          </div>
        </template>

        <!-- ───── 问卷完成 ───── -->
        <template x-if="q.isCompleted">
          <div class="step-q-done">
            <div class="step-q-done-icon">🎉</div>
            <h3>问卷填写完毕！</h3>
            <template x-if="Object.keys(q.aiCompletedAnswers || {}).length > 0">
              <div class="step-q-ai-list">
                <p>AI 已为您补全了以下设定：</p>
                <ul>
                  <template x-for="(value, key) in q.aiCompletedAnswers" :key="key">
                    <li><strong x-text="key"></strong>: <span x-text="value"></span></li>
                  </template>
                </ul>
              </div>
            </template>
            <p>点击下方按钮，根据问卷创建小说项目</p>
            <button class="btn-primary" @click="buildProject()" :disabled="building">
              <span x-show="!building">🎯 创建小说项目</span>
              <span x-show="building">⏳ 创建中...</span>
            </button>
            <button class="btn-secondary" @click="backToPool()">返回创意池</button>
          </div>
        </template>
      </div>
    </div>
  </template>
</div>
`);
