document.addEventListener('alpine:init', () => {
Alpine.data('novelEditor', () => ({
    project: null,
    projectId: null,
    chapters: [],
    currentChapter: null,
    activePanel: 'writing',
    writingTab: 'content',
    loading: false,
    chapterSwitching: false,
    chapterDirty: false,
    prepInfoLoading: false,
    fingerprintLoading: false,
    postProcessing: null,
    postProcessingLoading: false,
    bootstrapData: null,
    bootstrapDataLoading: false,

    // ─── AI 补全 banner / wizard（问卷或直接创建项目后的设定生成进度） ───
    bootstrapBanner: {
        visible: false,
        projectId: null,
        kind: '',           // 'in_flight' | 'awaiting_commit' | 'partial_failed' | 'aborted' | 'cancelled'
        runId: null,
        message: '',
        committing: false,
    },
    bootstrapWizard: {
        visible: false,
        projectId: null,
        runId: null,
        status: 'running',
        stages: [],
        pollHandle: null,
        tickHandle: null,
        errorMsg: '',
        startedAt: null,
        completedAt: null,
        rerunAllBusy: false,
        committing: false,
    },
    _bannerDismissed: new Set(),
    _bannerPollHandle: null,

    characters: [],
    themes: [],
    foreshadowings: [],
    characterArcs: [],
    characterRelations: [],
    plotPoints: [],
    consistencyResult: null,
    consistencyReport: null,
    inspirations: [],

    showPipelineSetup: false,
    showBatchGenerate: false,
    showExportModal: false,
    exportFormat: 'txt',
    exportRechapter: false,
    exportWordsPerChapter: 3000,
    exportSaveIndividual: false,
    showTextReplaceModal: false,
    showTaskManager: false,
    showPipelineProgress: false,
    pipelineTask: null,
    pipelineTaskId: null,
    pipelinePollHandle: null,
    pipelineStartTs: 0,
    showRegenerateConfirm: false,

    // ─── 任务管理 ───
    allTasks: [],
    allTasksLoading: false,
    _taskPollHandle: null,

    // ─── 大纲 / 世界观面板：重新生成 ───
    rerunStageBusy: {},
    showExtendOutlineModal: false,
    extendOutlineOriginalTotal: 0,
    extendOutlineGenerated: 0,
    extendOutlineExtendBy: 0,
    extendOutlineNewTotal: 0,
    extendOutlineArchitecture: true,
    extendOutlineBusy: false,

    // 9 步流水线元数据（与后端 llm.chapter_pipeline.PIPELINE_STAGES_META 对齐）
    PIPELINE_STAGES_META: [
        { id: '1_prep', label: '准备上下文' },
        { id: '2_outline_gen', label: '生成章节细纲' },
        { id: '3_outline_review', label: '细纲评审' },
        { id: '4_text_gen', label: '生成正文' },
        { id: '5_word_adjust', label: '字数调整' },
        { id: '6_review', label: '正文评审' },
        { id: '7_revise', label: '自动修订' },
        { id: '8_save', label: '保存到数据库' },
        { id: '9_post', label: '后处理（弧光/伏笔/一致性）' },
    ],

    showWordAdjustModal: false,
    wordAdjustPlan: null,
    wordAdjustTaskId: null,
    wordAdjustSubmitting: false,
    wordAdjustUseCustom: false,
    wordAdjustCustomMin: null,
    wordAdjustCustomTarget: null,
    wordAdjustCustomMax: null,
    wordAdjustPctInput: 10,

    showReviseConfirmModal: false,
    showReplaceCharacterModal: false,
    showDeleteCharacterModal: false,
    showRenameCharacterModal: false,

    showGenerateModal: false,
    generating: false,
    generatedText: null,
    generateMode: 'continue',
    generatePrompt: '',
    generateWordCount: '3000',

    batchGenerating: false,
    batchTask: null,
    batchPollHandle: null,
    batchGenerateStart: 0,
    batchGenerateCount: 5,
    batchGenerateGuide: '',

    tokenUsage: null,
    tokenUsageLoading: false,

    previewReview: null,
    chapterVersions: [],
    previewChapter: null,
    reviewHistory: [],

    outlineSubPanel: 'overview',
    chapterOutlines: [],
    chapterOutlinesMap: {},
    chapterPrepInfo: null,

    reviewSubPanel: 'new',
    activeReviewSession: null,
    reviewResult: null,

    fullReviewTaskRunning: false,
    fullReviewProgress: 0,
    fullReviewResult: null,
    fullReviewHistory: [],

    currentLlmLabel: '',
    ragEnabled: null,
    expandedTaskIds: [],

    get projectId() {
        const store = Alpine.store('app');
        return store.currentRoute.params.id;
    },

    init() {
        const id = Alpine.store('app').currentRoute.params.id;
        console.log('[NovelEditor] 打开项目', id);
        this.loadProject(id);
        this.loadChapters(id);
        this.loadCharacters(id);
        this.loadThemes(id);
        this.loadForeshadowings(id);
        this.loadPlotPoints(id);
        this.loadBootstrapData(id);
        this.loadTokenUsage(id);
        this._loadCurrentLlm();
        this._maybeShowBootstrapBanner(id);
        this._startBannerPolling(id);
        this._rehydrateBatchTask();
        this.refreshAllTasks();
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

    async loadChapters(id) {
        try {
            const res = await fetch(`/api/projects/${id}/chapters`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.chapters = await res.json();
            if (this.chapters.length > 0 && !this.currentChapter) {
                await this.selectChapter(this.chapters[0]);
            }
        } catch (e) {
            console.error('加载章节失败:', e);
            Alpine.store('app').toast('加载章节失败: ' + e.message, 'error');
        }
    },

    async selectChapter(chapter) {
        if (this.chapterSwitching) return;
        this.chapterSwitching = true;
        try {
            this.currentChapter = chapter;
            this.chapterDirty = false;
            this._saveLastView();
            await this.loadChapterOutlines(chapter.id);
            await this.loadPrepInfo(chapter.id);
            if (this.writingTab === 'fingerprint') {
                await this.loadFingerprint(chapter.id);
            }
        } catch (e) {
            console.error('加载章节失败:', e);
        } finally {
            this.chapterSwitching = false;
        }
    },

    async createChapter() {
        if (!this.project) return;
        const title = prompt('请输入章节标题:');
        if (!title) return;
        const order = this.chapters.length;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title, order, project_id: this.project.id }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const chapter = await res.json();
            this.chapters.push(chapter);
            this.chapters.sort((a, b) => a.order - b.order);
            await this.selectChapter(chapter);
            Alpine.store('app').toast('章节创建成功', 'success');
        } catch (e) {
            console.error('创建章节失败:', e);
            Alpine.store('app').toast('创建失败: ' + e.message, 'error');
        }
    },

    async saveChapter() {
        if (!this.currentChapter || !this.chapterDirty) return;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters/${this.currentChapter.id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    title: this.currentChapter.title,
                    content: this.currentChapter.content,
                    order: this.currentChapter.order,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.chapterDirty = false;
            const updated = await res.json();
            const idx = this.chapters.findIndex(c => c.id === updated.id);
            if (idx >= 0) this.chapters[idx] = updated;
            Alpine.store('app').toast('保存成功', 'success');
        } catch (e) {
            console.error('保存章节失败:', e);
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        }
    },

    onContentChange() {
        this.chapterDirty = true;
        if (this.currentChapter) {
            this.currentChapter.word_count = this._countWords(this.currentChapter.content);
        }
    },

    async loadChapterOutlines(chapterId) {
        try {
            const res = await fetch(`/api/projects/${this.projectId}/chapters/${chapterId}/outline`);
            if (!res.ok) return;
            const data = await res.json();
            this.chapterOutlinesMap[chapterId] = data;
        } catch (e) {
            console.warn('加载章节大纲失败:', e);
        }
    },

    async loadPrepInfo(chapterId) {
        this.prepInfoLoading = true;
        this.chapterPrepInfo = null;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters/${chapterId}/prep-info`);
            if (!res.ok) return;
            this.chapterPrepInfo = await res.json();
        } catch (e) {
            console.warn('加载 prep-info 失败:', e);
        } finally {
            this.prepInfoLoading = false;
        }
    },

    async loadFingerprint(chapterId) {
        this.fingerprintLoading = true;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters/${chapterId}/fingerprint`);
            if (!res.ok) return;
            this.currentChapter.fingerprint = await res.json();
        } catch (e) {
            console.warn('加载 fingerprint 失败:', e);
        } finally {
            this.fingerprintLoading = false;
        }
    },

    async loadPostProcessing(chapterId) {
        this.postProcessingLoading = true;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters/${chapterId}/post-processing`);
            if (!res.ok) return;
            const data = await res.json();
            this.postProcessing = data.post_processing || {};
        } catch (e) {
            console.warn('加载后处理结果失败:', e);
        } finally {
            this.postProcessingLoading = false;
        }
    },

    async loadCharacters(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/characters`);
            if (!res.ok) return;
            this.characters = await res.json();
        } catch (e) {
            console.warn('加载角色列表失败:', e);
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

    async loadForeshadowings(projectId) {
        try {
            const res = await fetch(`/api/projects/${projectId}/foreshadowings`);
            if (!res.ok) return;
            this.foreshadowings = await res.json();
        } catch (e) {
            console.warn('加载伏笔失败:', e);
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

    async loadBootstrapData(projectId) {
        this.bootstrapDataLoading = true;
        try {
            const res = await fetch(`/api/workflow/project/${projectId}/bootstrap-data`);
            if (!res.ok) return;
            this.bootstrapData = await res.json();
        } catch (e) {
            console.warn('加载 bootstrap 数据失败:', e);
        } finally {
            this.bootstrapDataLoading = false;
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
                this.ragEnabled = data.rag_enabled;
            }
        } catch (e) {
            console.warn('加载当前 LLM 失败:', e);
        }
    },

    _countWords(text) {
        if (!text) return 0;
        const chinese = (text.match(/[\u4e00-\u9fff]/g) || []).length;
        const english = (text.match(/[a-zA-Z]+/g) || []).length;
        return chinese + english;
    },

    _saveLastView() {
        try {
            const payload = {
                projectId: this.project?.id,
                chapterId: this.currentChapter?.id,
                panel: this.activePanel,
                writingTab: this.writingTab,
            };
            localStorage.setItem('cozywriter.lastView', JSON.stringify(payload));
        } catch (_) {}
    },

    setPanel(panel) {
        this.activePanel = panel;
        this._saveLastView();
    },

    setWritingTab(tab) {
        this.writingTab = tab;
        this._saveLastView();
    },

    get totalChapters() {
        return this.project?.total_chapters || 0;
    },

    get generatedChapterCount() {
        return this.chapters.length;
    },

    get chapterProgressPercent() {
        if (!this.totalChapters) return 0;
        return Math.round((this.chapters.length / this.totalChapters) * 100);
    },

    get wordCountStatus() {
        if (!this.currentChapter) return '';
        const wc = this.currentChapter.word_count || 0;
        const min = this.project?.word_count_min || 0;
        const max = this.project?.word_count_max || 99999;
        const target = this.project?.target_word_count || 0;
        if (wc < min) return `偏少 (${wc}/${target})`;
        if (wc > max) return `超标 (${wc}/${target})`;
        return `达标 ${wc}`;
    },

    getWordCountStyle(chapter) {
        if (!chapter) return {};
        const wc = chapter.word_count || 0;
        const min = this.project?.word_count_min || 0;
        const max = this.project?.word_count_max || 99999;
        if (wc < min) return { color: '#ef4444' };
        if (wc > max) return { color: '#f59e0b' };
        return { color: '#10b981' };
    },

    get canRunPipeline() {
        return !!this.currentChapter
            && (!this.pipelineTask || !['pending', 'running'].includes(this.pipelineTask.status));
    },

    async pipelineSetupSetupModal() {
        this.showPipelineSetup = true;
    },

    async startPipelineGuide(guide) {
        this.showPipelineSetup = false;
        await this.runChapterPipeline(guide);
    },

    // ─── 9 步章节生成流水线 ───
    async runChapterPipeline(guide) {
        if (!this.currentChapter) {
            Alpine.store('app').toast('请先选择一个章节', 'warning');
            return;
        }
        if (this.pipelinePollHandle) {
            Alpine.store('app').toast('已有流水线正在运行，请等待完成', 'warning');
            return;
        }
        try {
            console.log('[Pipeline] 启动单章生成', { chapter: this.currentChapter.id, guide });
            const res = await fetch('/api/chapters/generate-pipeline', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: this.project.id,
                    chapter_id: this.currentChapter.id,
                    auto_revise: true,
                    revision_threshold: 6.5,
                    guide: guide || '',
                }),
            });
            const data = await res.json();
            if (!res.ok || !data.task_id) {
                console.error('[Pipeline] 提交失败', data);
                Alpine.store('app').toast('流水线提交失败：' + (data.detail || JSON.stringify(data)), 'error');
                return;
            }
            this.pipelineTaskId = data.task_id;
            this.pipelineTask = { id: data.task_id, status: 'pending', result: { stages: {} } };
            this.pipelineStartTs = Date.now();
            this.showPipelineProgress = true;
            this.pipelinePollHandle = setInterval(() => this._pollPipelineTask(), 2000);
            this._pollPipelineTask();
            this.refreshAllTasks();
        } catch (e) {
            console.error('[Pipeline] 启动失败', e);
            Alpine.store('app').toast('启动失败: ' + e.message, 'error');
        }
    },

    async _pollPipelineTask() {
        const taskId = this.pipelineTaskId || (this.pipelineTask && this.pipelineTask.id);
        if (!taskId) return;
        try {
            const res = await fetch(`/api/tasks/${taskId}`);
            if (!res.ok) return;
            const task = await res.json();
            this.pipelineTask = task;
            const stages = (task.result && task.result.stages) || {};
            const running = Object.keys(stages).find((k) => stages[k].status === 'running');
            if (running) {
                console.log(`[Pipeline] ${taskId} stage ${running} (${(task.result || {}).progress_pct || 0}%)`);
            }
            this.refreshAllTasks();
            if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                clearInterval(this.pipelinePollHandle);
                this.pipelinePollHandle = null;
                console.log(`[Pipeline] ${taskId} 结束: ${task.status}`);
                const resultStatus = (task.result || {}).status;
                if (task.status === 'completed' && resultStatus !== 'failed') {
                    await this.loadChapters(this.project.id);
                    const ch = this.chapters.find((c) => c.id === (this.currentChapter && this.currentChapter.id));
                    if (ch) await this.selectChapter(ch);
                    if (this.currentChapter) await this.loadPostProcessing(this.currentChapter.id);
                    Alpine.store('app').toast(`生成完成（${(task.result || {}).final_word_count || 0} 字）`, 'success');
                } else if (task.status === 'completed' && resultStatus === 'failed') {
                    Alpine.store('app').toast('生成失败: ' + ((task.result || {}).error || '未知错误'), 'error');
                } else if (task.status === 'failed') {
                    Alpine.store('app').toast('生成失败: ' + (task.error || 'unknown'), 'error');
                }
            }
        } catch (e) {
            console.warn('[Pipeline] 轮询失败:', e);
        }
    },

    closePipelinePanel(navigateToChapter) {
        const taskDone = !this.pipelineTask
            || ['completed', 'failed', 'cancelled'].includes(this.pipelineTask.status);
        if (!taskDone && this.pipelinePollHandle) {
            if (!confirm('流水线还在运行中，确认关闭此面板？（不会停止后台任务）')) return;
        }
        if (this.pipelinePollHandle) {
            clearInterval(this.pipelinePollHandle);
            this.pipelinePollHandle = null;
        }
        this.showPipelineProgress = false;
        if (navigateToChapter && this.project) this.loadChapters(this.project.id);
    },

    openPipelinePanelForTask(t) {
        this.pipelineTask = t;
        this.pipelineTaskId = t.id;
        this.pipelineStartTs = Date.now() - Math.floor((t.duration_s || 0) * 1000);
        this.showPipelineProgress = true;
        if (['pending', 'running'].includes(t.status)) {
            if (this.pipelinePollHandle) clearInterval(this.pipelinePollHandle);
            this.pipelinePollHandle = setInterval(() => this._pollPipelineTask(), 2000);
        }
    },

    get pipelineStagesView() {
        const backendStages = (this.pipelineTask && this.pipelineTask.result && this.pipelineTask.result.stages) || {};
        const now = Date.now();
        return this.PIPELINE_STAGES_META.map((m) => {
            const s = backendStages[m.id] || {};
            const startedAtMs = s.started_at ? Math.floor(s.started_at * 1000) : null;
            let elapsed = 0;
            let pct = 0;
            if (s.status === 'running') {
                if (startedAtMs) {
                    elapsed = (now - startedAtMs) / 1000;
                    pct = Math.min(95, (elapsed / 90) * 100);
                } else {
                    elapsed = (now - this.pipelineStartTs) / 1000;
                    pct = 30;
                }
            } else if (s.duration_ms != null) {
                elapsed = s.duration_ms / 1000;
                pct = 100;
            }
            return {
                id: m.id,
                label: s.label || m.label,
                status: s.status || 'pending',
                duration_ms: s.duration_ms,
                elapsed_display: Number.isFinite(elapsed) ? elapsed.toFixed(1) : '0.0',
                elapsed_pct: pct,
                error: s.error || null,
                score: s.score,
            };
        });
    },

    get pipelineProgressPct() {
        return (this.pipelineTask && this.pipelineTask.result && this.pipelineTask.result.progress_pct) || 0;
    },

    get pipelineStatus() {
        const t = this.pipelineTask;
        if (!t) return 'pending';
        if (t.status === 'completed' && t.result && t.result.status === 'failed') return 'failed';
        return t.status;
    },

    get pipelineFinalResult() {
        const r = this.pipelineTask && this.pipelineTask.result;
        if (!r) return null;
        return {
            final_word_count: r.final_word_count,
            error: r.error,
        };
    },

    get pipelineElapsedText() {
        if (!this.pipelineStartTs) return '';
        const e = (Date.now() - this.pipelineStartTs) / 1000;
        return e < 60 ? e.toFixed(1) + 's' : Math.floor(e / 60) + 'm' + Math.floor(e % 60) + 's';
    },

    getStageLabel(stageId) {
        const m = this.PIPELINE_STAGES_META.find((s) => s.id === stageId);
        return m ? m.label : stageId;
    },

    pipelineStageIcon(status) {
        return {
            pending: '○',
            running: '⏳',
            completed: '✅',
            failed: '❌',
            skipped: '⏭️',
        }[status] || '○';
    },

    // ─── 批量生成 ───
    async openBatchGenerateModal() {
        // batchGenerateStart 为 1-based「起始章节号」：
        //   有当前章节 → 当前章节序号 + 1（下一章）
        //   无当前章节 → 已有章节数 + 1
        let start;
        if (this.currentChapter) {
            start = this.currentChapter.order + 2;
        } else {
            start = this.chapters.length > 0
                ? Math.max(...this.chapters.map((ch) => ch.order + 1)) + 1
                : 1;
        }
        this.batchGenerateStart = start;
        this.batchGenerateCount = 5;
        this.batchGenerateGuide = '';
        this.showBatchGenerate = true;
    },

    get batchStartDisplay() {
        return Math.max(1, parseInt(this.batchGenerateStart) || 1);
    },

    get batchEndDisplay() {
        return this.batchStartDisplay + Math.max(1, parseInt(this.batchGenerateCount) || 1) - 1;
    },

    async startBatchGenerate() {
        if (this.batchGenerating) return;
        const count = Math.max(1, parseInt(this.batchGenerateCount) || 1);
        // API 的 start_chapter 是 0-based「从这一章之后开始」，故减 1
        const apiStart = Math.max(0, this.batchStartDisplay - 1);
        const startFrom = this.batchStartDisplay;
        const endAt = this.batchEndDisplay;
        if (!confirm(`确认批量生成第 ${startFrom} 章到第 ${endAt} 章（共 ${count} 章）？\n\n每章将执行完整的 9 步生成流水线，可能需要较长时间。`)) return;
        try {
            console.log('[Batch] 提交批量生成', { start: apiStart, count, guide: this.batchGenerateGuide });
            const res = await fetch('/api/chapters/batch-generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: this.project.id,
                    start_chapter: apiStart,
                    count,
                    guide: this.batchGenerateGuide || '',
                }),
            });
            const data = await res.json();
            if (!res.ok || !data.task_id) {
                Alpine.store('app').toast('批量生成提交失败：' + (data.detail || JSON.stringify(data)), 'error');
                return;
            }
            this.batchTask = {
                id: data.task_id,
                status: 'pending',
                result: { batch: true, total_chapters: count, completed_chapters: 0, chapters_status: {}, current_pipeline_stages: {} },
            };
            this.batchGenerating = true;
            this.showBatchGenerate = false;
            try {
                localStorage.setItem('cozywriter.batchTask', JSON.stringify({
                    id: data.task_id, project_id: this.project.id,
                    start_chapter: this.batchGenerateStart, count,
                    started_at: Date.now(),
                }));
            } catch (_) { /* ignore */ }
            this.startBatchPolling();
            this.refreshAllTasks();
        } catch (e) {
            console.error('[Batch] 提交失败', e);
            Alpine.store('app').toast('批量生成失败: ' + e.message, 'error');
        }
    },

    startBatchPolling() {
        if (this.batchPollHandle) clearInterval(this.batchPollHandle);
        this.batchPollHandle = setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks/${this.batchTask.id}`);
                if (!res.ok) return;
                const task = await res.json();
                this.batchTask = task;
                const r = task.result || {};
                if (r.batch) {
                    console.log(`[Batch] ${task.status} 第${r.current_chapter_order || '?'}章 (${r.completed_chapters || 0}/${r.total_chapters || 0})`);
                }
                if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                    clearInterval(this.batchPollHandle);
                    this.batchPollHandle = null;
                    this.batchGenerating = false;
                    try { localStorage.removeItem('cozywriter.batchTask'); } catch (_) { /* ignore */ }
                    if (this.project) await this.loadChapters(this.project.id);
                    if (task.status === 'completed') {
                        const failed = r.failed_chapters || [];
                        if (failed.length > 0) {
                            Alpine.store('app').toast(`批量生成完成，但第 ${failed.join(', ')} 章失败`, 'warning');
                        } else {
                            Alpine.store('app').toast(`批量生成完成！共 ${r.completed_chapters || r.total_chapters || 0} 章`, 'success');
                        }
                    } else if (task.status === 'failed') {
                        Alpine.store('app').toast('批量生成失败：' + (task.error || '未知错误'), 'error');
                    }
                    this.refreshAllTasks();
                }
            } catch (e) {
                console.warn('[Batch] 轮询失败:', e);
            }
        }, 2000);
    },

    async _rehydrateBatchTask() {
        try {
            const raw = localStorage.getItem('cozywriter.batchTask');
            if (!raw) return;
            const saved = JSON.parse(raw);
            if (!saved || !saved.id) { localStorage.removeItem('cozywriter.batchTask'); return; }
            const res = await fetch(`/api/tasks/${saved.id}`);
            if (!res.ok) { localStorage.removeItem('cozywriter.batchTask'); return; }
            const data = await res.json();
            if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                localStorage.removeItem('cozywriter.batchTask');
                return;
            }
            console.log('[Batch] 恢复批量任务:', saved.id);
            this.batchTask = data;
            this.batchGenerating = true;
            this.startBatchPolling();
        } catch (e) {
            console.warn('[Batch] 恢复失败:', e);
            try { localStorage.removeItem('cozywriter.batchTask'); } catch (_) { /* ignore */ }
        }
    },

    cancelBatchGenerate() {
        if (this.batchPollHandle) { clearInterval(this.batchPollHandle); this.batchPollHandle = null; }
        this.batchGenerating = false;
        this.batchTask = null;
        try { localStorage.removeItem('cozywriter.batchTask'); } catch (_) { /* ignore */ }
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
            progressPct: r.current_pipeline_progress_pct || 0,
        };
    },

    get batchPipelineStagesView() {
        const info = this.batchProgressInfo;
        if (!info) return [];
        return this.PIPELINE_STAGES_META.map((m) => {
            const s = info.pipelineStages[m.id] || {};
            return {
                id: m.id,
                label: s.label || m.label,
                status: s.status || 'pending',
                duration_ms: s.duration_ms,
            };
        });
    },

    async openExportModal() {
        this.showExportModal = true;
    },

    async exportChapters() {
        if (!this.chapters || this.chapters.length === 0) {
            Alpine.store('app').toast('没有可导出的章节', 'warning');
            return;
        }
        try {
            const res = await fetch('/api/export/chapters', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: this.projectId,
                    chapter_ids: this.chapters.map(c => c.id),
                    rechapter: this.exportRechapter,
                    words_per_chapter: this.exportWordsPerChapter,
                    format: this.exportFormat,
                    save_individual: this.exportSaveIndividual,
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const blob = await res.blob();
            // 优先用后端 Content-Disposition 里的文件名（中文已 RFC5987 编码）
            let filename = this.exportFormat === 'markdown' ? '导出.md' : '导出.txt';
            const disposition = res.headers.get('Content-Disposition') || '';
            const m = /filename\*=UTF-8''([^;]+)/.exec(disposition);
            if (m) filename = decodeURIComponent(m[1]);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            this.showExportModal = false;
            Alpine.store('app').toast('导出成功', 'success');
        } catch (e) {
            console.error('导出失败:', e);
            Alpine.store('app').toast('导出失败: ' + e.message, 'error');
        }
    },

    async openTextReplaceModal() {
        this.showTextReplaceModal = true;
    },

    async openTaskManager() {
        console.log('[TaskManager] 打开任务管理');
        this.showTaskManager = true;
        await this.refreshAllTasks();
        if (this._taskPollHandle) clearInterval(this._taskPollHandle);
        this._taskPollHandle = setInterval(() => {
            if (this.showTaskManager) this.refreshAllTasks();
        }, 3000);
    },

    async refreshAllTasks() {
        this.allTasksLoading = true;
        try {
            const res = await fetch('/api/tasks/all');
            if (!res.ok) {
                // 后端无 /all 时回退到项目任务
                const all = [];
                if (this.project) {
                    const r2 = await fetch(`/api/tasks/project/${this.project.id}`);
                    if (r2.ok) all.push(...(await r2.json()));
                }
                this.allTasks = all;
                return;
            }
            this.allTasks = await res.json();
        } catch (e) {
            console.warn('[TaskManager] 刷新任务失败:', e);
        } finally {
            this.allTasksLoading = false;
        }
    },

    async terminateAllTasks() {
        if (!confirm('确定终止所有正在运行的任务？\n这会打断 LLM 调用，可能导致部分 stage 不完整。')) return;
        try {
            const res = await fetch('/api/tasks/terminate-all', { method: 'POST' });
            if (res.ok) {
                const data = await res.json();
                Alpine.store('app').toast(`已终止 ${data.terminated} 个任务，跳过 ${data.skipped} 个`, 'success');
                await this.refreshAllTasks();
            } else {
                Alpine.store('app').toast('终止失败: HTTP ' + res.status, 'error');
            }
        } catch (e) {
            Alpine.store('app').toast('终止失败: ' + e.message, 'error');
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
                Alpine.store('app').toast('终止失败: ' + (err.detail || res.status), 'error');
            }
        } catch (e) {
            Alpine.store('app').toast('终止失败: ' + e.message, 'error');
        }
    },

    async rerunOneBootstrapTask(task, forceAll = false) {
        if (!task.run_id) {
            Alpine.store('app').toast('该任务没有关联的 workflow run，无法重跑。', 'warning');
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
                const polledTask = await this._pollTask(data.task_id, {
                    onProgress: () => this.refreshAllTasks(),
                });
                if (polledTask.status === 'completed' && polledTask.result) {
                    const success = (polledTask.result.rerun_stages || []).length;
                    const still = (polledTask.result.still_failed || []).length;
                    Alpine.store('app').toast(`重跑完成：成功 ${success} 个 stage，仍失败 ${still} 个。`, still ? 'warning' : 'success');
                } else {
                    Alpine.store('app').toast('重跑失败: ' + (polledTask.error || 'unknown'), 'error');
                }
            } else if (data.status === 'ok') {
                const success = (data.rerun_stages || []).length;
                const still = (data.still_failed || []).length;
                Alpine.store('app').toast(`重跑完成：成功 ${success} 个 stage，仍失败 ${still} 个。`, still ? 'warning' : 'success');
            } else {
                Alpine.store('app').toast('重跑失败: ' + (data.error || data.detail || 'unknown'), 'error');
            }
        } catch (e) {
            Alpine.store('app').toast('重跑失败: ' + e.message, 'error');
        } finally {
            await this.refreshAllTasks();
        }
    },

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
            Alpine.store('app').toast(forceAll ? '没有可重跑的 bootstrap 项目。' : '没有需要重跑的失败项。', 'warning');
            return;
        }
        const label = forceAll ? `${uniqueRuns.length} 个项目（包括已成功的 stage 也会重新生成）` : `${uniqueRuns.length} 个失败项目`;
        if (!confirm(`确定对 ${label}按顺序重新生成吗？`)) return;

        let totalSuccess = 0;
        let totalStillFailed = 0;
        for (const t of uniqueRuns) {
            try {
                const res = await fetch(`/api/workflow/run/${t.run_id}/rerun-all?force_all=${forceAll}`, {
                    method: 'POST',
                });
                const data = await res.json();
                if (data.status === 'submitted') {
                    const task = await this._pollTask(data.task_id, {
                        onProgress: () => this.refreshAllTasks(),
                    });
                    if (task.status === 'completed' && task.result) {
                        totalSuccess += (task.result.rerun_stages || []).length;
                        totalStillFailed += (task.result.still_failed || []).length;
                    } else {
                        totalStillFailed += 1;
                    }
                } else if (data.status === 'ok') {
                    totalSuccess += (data.rerun_stages || []).length;
                    totalStillFailed += (data.still_failed || []).length;
                } else {
                    totalStillFailed += 1;
                }
            } catch (e) {
                console.error('[rerunAllBootstrapTasks] failed:', e);
                totalStillFailed += 1;
            }
        }
        Alpine.store('app').toast(`重跑完成：成功 ${totalSuccess} 个 stage，仍失败 ${totalStillFailed} 个。`, totalStillFailed ? 'warning' : 'success');
        await this.refreshAllTasks();
    },

    get activeTaskCount() {
        return this.allTasks.filter((t) => ['pending', 'running'].includes(t.status)).length;
    },

    get hasFailedBootstrapTasks() {
        return this.allTasks.some(
            (t) => t.task_type === 'bootstrap' && ['failed', 'cancelled'].includes(t.status) && t.run_id
        );
    },

    get hasBootstrapTasks() {
        return this.allTasks.some((t) => t.task_type === 'bootstrap' && t.run_id);
    },

    taskTypeLabel(type) {
        return {
            bootstrap: '引导补全',
            chapter_pipeline: '单章流水线',
            batch_pipeline: '批量生成',
            chapter_revise: '章节修订',
            word_adjust: '字数调整',
            extend_outline: '大纲扩写',
            review: '评审',
            full_review: '全文评审',
            generate: 'AI 生成',
        }[type] || type;
    },

    taskStatusLabel(status) {
        return {
            pending: '等待',
            running: '运行中',
            completed: '完成',
            failed: '失败',
            cancelled: '已取消',
        }[status] || status;
    },

    toggleTaskDetail(taskId) {
        if (this.expandedTaskIds.includes(taskId)) {
            this.expandedTaskIds = this.expandedTaskIds.filter((id) => id !== taskId);
        } else {
            this.expandedTaskIds = [...this.expandedTaskIds, taskId];
        }
    },

    resetTaskPolling() {
        if (this._taskPollHandle) {
            clearInterval(this._taskPollHandle);
            this._taskPollHandle = null;
        }
    },

    async loadChapterVersions() {
        if (!this.currentChapter) return;
        try {
            const res = await fetch(`/api/projects/${this.project.id}/chapters/${this.currentChapter.id}/versions`);
            if (!res.ok) return;
            this.chapterVersions = await res.json();
        } catch (e) {
            console.warn('加载章节版本失败:', e);
        }
    },

    async _rollbackToVersion(versionNum) {
        if (!this.currentChapter) return;
        if (!confirm(`确定回滚到版本 ${versionNum}？当前内容将被覆盖。`)) return;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/chapters/${this.currentChapter.id}/rollback/${versionNum}`, {
                method: 'POST',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const updated = await res.json();
            this.currentChapter = updated;
            this.chapterDirty = false;
            Alpine.store('app').toast('回滚成功', 'success');
        } catch (e) {
            console.error('回滚失败:', e);
            Alpine.store('app').toast('回滚失败: ' + e.message, 'error');
        }
    },

    formatDate(dt) {
        if (!dt) return '';
        return new Date(dt).toLocaleString('zh-CN');
    },

    _countChineseChars(text) {
        if (!text) return 0;
        return (text.match(/[\u4e00-\u9fff]/g) || []).length;
    },

    backToHome() {
        Alpine.store('app').navigate('/');
    },

    goToSettings() {
        Alpine.store('app').navigate(`/project/${this.project.id}/settings`);
    },

    destroy() {
        if (this.pipelinePollHandle) clearInterval(this.pipelinePollHandle);
        if (this._taskPollHandle) clearInterval(this._taskPollHandle);
        if (this.batchPollHandle) clearInterval(this.batchPollHandle);
        this._stopBannerPolling();
        this._stopBootstrapPolling();
    },

    // ─── 项目首页 AI 补全 banner ───

    dismissBootstrapBanner() {
        this.bootstrapBanner.visible = false;
        if (this.bootstrapBanner.projectId) {
            this._bannerDismissed.add(this.bootstrapBanner.projectId);
        }
    },

    _startBannerPolling(projectId) {
        this._stopBannerPolling();
        this._bannerPollHandle = setInterval(async () => {
            const store = Alpine.store('app');
            if (store.currentRoute.name === 'novel_editor' && store.currentRoute.params.id === projectId) {
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

    async _maybeShowBootstrapBanner(projectId) {
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

            // 1) 已 committed → 完全完成，不显示
            if (status === 'committed') {
                this.bootstrapBanner.visible = false;
                return;
            }

            // 2) pending / running → 任务在进行中
            if (status === 'pending' || status === 'running') {
                const total = stages.length;
                const done = stages.filter((s) =>
                    ['ok', 'user_filled', 'skipped'].includes(s.status)
                ).length;
                this.bootstrapBanner = {
                    ...this.bootstrapBanner,
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
                    ...this.bootstrapBanner,
                    visible: true,
                    projectId,
                    runId: data.run_id,
                    kind: 'awaiting_commit',
                    message: 'AI 补全已完成，等待你确认写入数据库。',
                };
                return;
            }

            // 4) failed / partial → 部分失败（无实际失败 stage 时降级为待提交）
            if (status === 'failed' || status === 'partial') {
                const failedCount = stages.filter((s) => s.status === 'failed').length;
                if (failedCount === 0) {
                    this.bootstrapBanner = {
                        ...this.bootstrapBanner,
                        visible: true,
                        projectId,
                        runId: data.run_id,
                        kind: 'awaiting_commit',
                        message: 'AI 补全已完成，等待你确认写入数据库。',
                    };
                    return;
                }
                this.bootstrapBanner = {
                    ...this.bootstrapBanner,
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
                const errMsgs = Object.values(data.stage_results || {})
                    .map((s) => (typeof s === 'object' ? (s.error || '') : ''))
                    .join(' ');
                const isAborted = /服务重启|重启|Restart|aborted|orphan/i.test(errMsgs);
                this.bootstrapBanner = {
                    ...this.bootstrapBanner,
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
            ...this.bootstrapWizard,
            visible: true,
            projectId,
            runId,
            status: 'running',
            stages: [],
            errorMsg: '',
            startedAt: Date.now(),
            completedAt: null,
            rerunAllBusy: false,
            committing: false,
        };
        await this._pollBootstrapStatus();
        this._stopBootstrapPolling();
        this.bootstrapWizard.pollHandle = setInterval(
            () => this._pollBootstrapStatus(),
            5000
        );
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
                wiz.status = 'failed';
                wiz.errorMsg = '有 stage 执行失败';
                this._stopBootstrapPolling();
            } else if (allDone && (data.status === 'completed' || data.status === 'partial' || failedCount === 0)) {
                // 后端已自动 commit（auto_commit=true），前端保险起见也自动调一次 commit
                wiz.status = 'committing';
                wiz.completedAt = Date.now();
                this._stopBootstrapPolling();
                this.commitBootstrap(true).then(() => {
                    wiz.status = 'committed';
                }).catch((e) => {
                    console.error('[Bootstrap auto-commit] failed:', e);
                    wiz.status = 'completed';
                });
            }
        } catch (e) {
            console.error('[Bootstrap poll] failed:', e);
        }
    },

    _tickBootstrapElapsed() {
        const wiz = this.bootstrapWizard;
        if (!wiz.visible || !wiz.stages) return;
        const hasRunning = wiz.stages.some(
            (s) => s.status === 'running' && s.started_at && !s.completed_at
        );
        if (!hasRunning) return;
        const now = Date.now();
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

    bootstrapMissingCount() {
        const wiz = this.bootstrapWizard;
        if (!wiz || !wiz.stages) return 0;
        return wiz.stages.filter(
            (s) => !['ok', 'user_filled', 'skipped'].includes(s.status)
        ).length;
    },

    async rerunBootstrapAllStages(forceAll = false) {
        const wiz = this.bootstrapWizard;
        if (!wiz.runId) return;
        const missingCount = this.bootstrapMissingCount();
        if (!forceAll && missingCount === 0) {
            Alpine.store('app').toast('当前没有未完成的 stage，无需重跑。', 'warning');
            return;
        }
        const msg = forceAll
            ? `确定【重跑所有项】吗？\n将覆盖全部已成功的 stage（用户手填的项会保留）。\n生成所有 stage 预计耗时较长。`
            : `确定重新生成 ${missingCount} 个【缺失项】吗？\n（按依赖顺序串行重跑：已成功的不会重复跑）`;
        if (!confirm(msg)) return;

        wiz.rerunAllBusy = true;
        try {
            const res = await fetch(`/api/workflow/run/${wiz.runId}/rerun-all?force_all=${forceAll}`, {
                method: 'POST',
            });
            const data = await res.json();
            if (data.status !== 'submitted') {
                Alpine.store('app').toast('重跑失败: ' + (data.error || JSON.stringify(data)), 'error');
                return;
            }
            const task = await this._pollTask(data.task_id, {
                onProgress: () => this._pollBootstrapStatus(),
            });
            if (task.status === 'completed') {
                const stages = wiz.stages || [];
                let success = 0, stillFailed = 0, skipped = 0;
                for (const s of stages) {
                    if (s.status === 'ok') success++;
                    else if (s.status === 'failed' || s.status === 'cancelled') stillFailed++;
                    else if (s.status === 'skipped') skipped++;
                }
                const runStatus = (task.result && task.result.run_status) || '';
                const statusNote = runStatus === 'completed' ? '本次全部完成。'
                    : runStatus === 'partial' ? '本次部分完成：仍有 stage 失败。'
                        : runStatus === 'failed' ? '本次总体失败。'
                            : '';
                Alpine.store('app').toast(`重跑完成：成功 ${success} 个，仍失败 ${stillFailed} 个，跳过 ${skipped} 个。${statusNote}`, stillFailed > 0 ? 'warning' : 'success');
                await this._pollBootstrapStatus();
            } else if (task.status === 'failed') {
                Alpine.store('app').toast('重跑失败: ' + (task.error || 'unknown'), 'error');
            } else {
                Alpine.store('app').toast('重跑被取消: ' + (task.error || 'cancelled'), 'warning');
            }
        } catch (e) {
            Alpine.store('app').toast('重跑失败: ' + e.message, 'error');
        } finally {
            wiz.rerunAllBusy = false;
        }
    },

    async commitBootstrap(auto = false, projectId = null, runId = null) {
        const wiz = this.bootstrapWizard;
        const targetRunId = runId || wiz.runId;
        const targetProjectId = projectId || wiz.projectId;
        if (!targetRunId) return;

        if (!auto) {
            if (wiz.committing || this.bootstrapBanner.committing) return;
            wiz.committing = true;
            this.bootstrapBanner.committing = true;
        }

        try {
            const res = await fetch(`/api/workflow/run/${targetRunId}/commit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            const data = await res.json();
            if (data.status === 'committed' || data.status === 'already_committed') {
                wiz.status = 'committed';
                wiz.completedAt = Date.now();
                wiz.projectId = targetProjectId;
                wiz.runId = targetRunId;
                this._stopBootstrapPolling();
                await this._reloadAllProjectData(targetProjectId);
                if (!auto) {
                    const summary = data.summary || {};
                    Alpine.store('app').toast(
                        `✅ 设定已写入：主题 ${summary.themes || 0} 条 / 世界观 ${summary.world_entries || 0} 条 / 角色 ${summary.characters || 0} 个 / 伏笔 ${summary.foreshadowings || 0} 条`,
                        'success', 6000
                    );
                }
                this.bootstrapBanner.visible = false;
            } else {
                if (auto) {
                    throw new Error(data.error || data.detail || 'commit failed');
                }
                Alpine.store('app').toast('提交失败: ' + (data.error || data.detail || 'unknown'), 'error');
            }
        } finally {
            wiz.committing = false;
            this.bootstrapBanner.committing = false;
        }
    },

    async _reloadAllProjectData(projectId) {
        await this.loadProject(projectId);
        await this.loadChapters(projectId);
        this.loadCharacters(projectId);
        this.loadThemes(projectId);
        this.loadForeshadowings(projectId);
        this.loadPlotPoints(projectId);
        this.loadBootstrapData(projectId);
    },

    closeBootstrapWizard() {
        this._stopBootstrapPolling();
        this.bootstrapWizard.visible = false;
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

    formatStageElapsed(stage) {
        if (!stage) return '';
        const startSec = Number(stage.started_at);
        if (!Number.isFinite(startSec) || startSec <= 0 || startSec < 1000000000) {
            return '';
        }
        const startMs = startSec * 1000;
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
            return '';
        }
        if (!Number.isFinite(elapsedMs) || elapsedMs < 0 || elapsedMs > 30 * 24 * 3600 * 1000) {
            return '';
        }
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

    // ─── 设定文档（世界观/背景、大纲）辅助 ───

    effectiveTotalChapters() {
        if (this.project && this.project.total_chapters) return this.project.total_chapters;
        const base = this.bootstrapData && this.bootstrapData.base;
        if (base && base.total_chapters) return base.total_chapters;
        return 0;
    },

    get worldCategories() {
        const w = this.bootstrapData && this.bootstrapData.world;
        const byCat = (w && w.entries_by_category) || {};
        return Object.entries(byCat).map(([category, entries]) => ({ category, entries }));
    },

    get hasWorldData() {
        return this.worldCategories.length > 0;
    },

    get preambleText() {
        const meta = (this.bootstrapData && this.bootstrapData.project_meta) || {};
        return meta.premise || (this.project && this.project.premise) || '';
    },

    get chapterOneLineOutlines() {
        const o = this.bootstrapData && this.bootstrapData.outline;
        return (o && Array.isArray(o.chapter_outlines)) ? o.chapter_outlines : [];
    },

    bootstrapAiOutlineSummary() {
        const o = this.bootstrapData && this.bootstrapData.outline;
        if (!o) return '';
        const parts = [];
        if (o.outline_text) parts.push(`概要 ${o.outline_text.length} 字`);
        if (Array.isArray(o.plot_lines) && o.plot_lines.length) parts.push(`${o.plot_lines.length} 条剧情线`);
        const acts = (o.structure && o.structure.acts) || [];
        if (acts.length) parts.push(`${acts.length} 幕结构`);
        if (o.pacing_notes) parts.push('节奏规划');
        return parts.join(' · ');
    },

    bootstrapAiTheme() {
        const t = this.bootstrapData && this.bootstrapData.theme;
        return (t && (t.theme || t.tone)) ? t : null;
    },

    bootstrapAiForeshadowings() {
        const f = this.bootstrapData && this.bootstrapData.foreshadowings;
        if (!f || !f.by_period) return null;
        const total = f.total || 0;
        return total > 0 ? f : null;
    },

    async _refreshBootstrapData() {
        if (!this.project) return;
        try {
            const res = await fetch(`/api/workflow/project/${this.project.id}/bootstrap-data`);
            if (res.ok) this.bootstrapData = await res.json();
        } catch (e) {
            console.warn('[refreshBootstrapData] failed:', e);
        }
    },

    // ─── 从面板重跑 bootstrap stage（世界观/大纲等）───

    rerunStageBtnTitle(stageId) {
        return '点击用 LLM 重新生成该部分设定（会覆盖现有内容）';
    },

    async rerunBootstrapStageFromPanel(stageId) {
        if (!this.project) {
            Alpine.store('app').toast('请先打开一个项目', 'warning');
            return;
        }
        const stageLabel = {
            'stage_1_base': '基础外推',
            'stage_2a_theme': '主旨/基调',
            'stage_2b_style': '文风/节奏',
            'stage_2c_world': '世界观/背景',
            'stage_3a_protagonist': '主角',
            'stage_3b_antagonist': '反派',
            'stage_3c_supporting': '配角',
            'stage_3d_arcs': '角色弧光',
            'stage_4a_outline': '项目大纲',
            'stage_4a_chapter_outlines': '每章一句话大纲',
            'stage_4b_foreshadow': '伏笔',
        }[stageId] || stageId;

        let chapterRange = '';
        if (stageId === 'stage_4a_outline' || stageId === 'stage_4a_chapter_outlines') {
            const total = this.project.total_chapters || 0;
            if (total > 0) chapterRange = `\n预计重新生成第 1 章到第 ${total} 章，共计 ${total} 章。`;
        }
        if (!confirm(`确定重新生成「${stageLabel}」吗？将覆盖之前的结果。${chapterRange}`)) return;

        const stagesToRerun = stageId === 'stage_4a_outline'
            ? ['stage_4a_outline', 'stage_4a_chapter_outlines']
            : [stageId];

        for (const sid of stagesToRerun) {
            this.rerunStageBusy[sid] = true;
            try {
                const lr = await fetch(`/api/workflow/project/${this.project.id}/latest`);
                if (!lr.ok) {
                    Alpine.store('app').toast('未找到 bootstrap 运行记录，请先完成设定生成。', 'warning');
                    return;
                }
                const runData = await lr.json();
                const runId = runData.run_id;
                console.log(`[RerunStage] ${sid} @ run ${runId}`);
                const res = await fetch(`/api/workflow/run/${runId}/rerun`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stage_id: sid }),
                });
                const data = await res.json();
                if (data.status !== 'submitted') {
                    Alpine.store('app').toast('重跑失败: ' + (data.error || JSON.stringify(data)), 'error');
                    return;
                }
                const task = await this._pollTask(data.task_id, { onProgress: () => this.refreshAllTasks() });
                if (task.status === 'completed') {
                    await fetch(`/api/workflow/run/${runId}/commit`, { method: 'POST' });
                } else {
                    Alpine.store('app').toast('重跑失败: ' + (task.error || 'unknown'), 'error');
                    return;
                }
            } catch (e) {
                Alpine.store('app').toast('重跑失败: ' + e.message, 'error');
                return;
            } finally {
                this.rerunStageBusy[sid] = false;
            }
        }

        await this._refreshBootstrapData();
        await this.loadProject(this.project.id);
        await this.loadChapters(this.project.id);
        this.loadCharacters(this.project.id);
        this.loadThemes(this.project.id);
        this.loadForeshadowings(this.project.id);
        Alpine.store('app').toast(`✅ ${stageLabel} 已重新生成`, 'success');
    },

    async rerunAllCharacters() {
        if (!this.project) {
            Alpine.store('app').toast('请先打开一个项目', 'warning');
            return;
        }
        if (!confirm('确定重新生成全部角色吗？将覆盖之前的主角、反派、配角和角色弧光。')) return;
        const stagesToRerun = ['stage_3a_protagonist', 'stage_3b_antagonist', 'stage_3c_supporting', 'stage_3d_arcs'];
        let runId = null;
        for (const sid of stagesToRerun) {
            this.rerunStageBusy[sid] = true;
            try {
                const lr = await fetch(`/api/workflow/project/${this.project.id}/latest`);
                if (!lr.ok) {
                    Alpine.store('app').toast('未找到 bootstrap 运行记录。', 'warning');
                    return;
                }
                const runData = await lr.json();
                runId = runData.run_id;
                const res = await fetch(`/api/workflow/run/${runId}/rerun`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ stage_id: sid }),
                });
                const data = await res.json();
                if (data.status !== 'submitted') {
                    Alpine.store('app').toast('重跑失败: ' + (data.error || JSON.stringify(data)), 'error');
                    return;
                }
                const task = await this._pollTask(data.task_id, { onProgress: () => this.refreshAllTasks() });
                if (task.status !== 'completed') {
                    Alpine.store('app').toast('重跑失败: ' + (task.error || 'unknown'), 'error');
                    return;
                }
            } catch (e) {
                Alpine.store('app').toast('重跑失败: ' + e.message, 'error');
                return;
            } finally {
                this.rerunStageBusy[sid] = false;
            }
        }
        if (runId) {
            await fetch(`/api/workflow/run/${runId}/commit`, { method: 'POST' });
        }
        await this._refreshBootstrapData();
        await this.loadProject(this.project.id);
        this.loadCharacters(this.project.id);
        Alpine.store('app').toast('✅ 全部角色已重新生成', 'success');
        if (confirm('⚠️ 角色已更新！\n\n大纲中的角色名可能与新角色不一致。\n\n是否立即重新生成大纲以保持剧情一致性？')) {
            await this.rerunBootstrapStageFromPanel('stage_4a_outline');
        }
    },

    // ─── 扩写 / 缩减大纲 ───

    openExtendOutlineModal() {
        if (!this.project) return;
        this.extendOutlineOriginalTotal = this.project.total_chapters || 0;
        this.extendOutlineGenerated = this.chapterOneLineOutlines.length;
        this.extendOutlineExtendBy = 100;
        this.extendOutlineNewTotal = this.extendOutlineGenerated + 100;
        this.extendOutlineArchitecture = true;
        this.extendOutlineBusy = false;
        this.showExtendOutlineModal = true;
    },

    extendOutlineBtnTitle() {
        return '基于已有大纲扩写更多章节，或缩减小说篇幅';
    },

    onExtendOutlineChange(which, rawValue) {
        const v = parseInt(rawValue, 10);
        if (isNaN(v)) return;
        if (which === 'extendBy') {
            this.extendOutlineExtendBy = v;
            this.extendOutlineNewTotal = this.extendOutlineGenerated + v;
        } else if (which === 'newTotal') {
            this.extendOutlineNewTotal = Math.max(0, v);
            this.extendOutlineExtendBy = this.extendOutlineNewTotal - this.extendOutlineGenerated;
        }
    },

    get canSubmitExtendOutline() {
        if (this.extendOutlineBusy) return false;
        if (this.extendOutlineExtendBy === 0) return false;
        if (this.extendOutlineNewTotal < 0) return false;
        return true;
    },

    async confirmExtendOutline() {
        if (!this.project) return;
        const newTotal = this.extendOutlineNewTotal;
        const generated = this.extendOutlineGenerated;
        const diff = this.extendOutlineExtendBy;
        if (newTotal < 0) { Alpine.store('app').toast('新目标章节总数不能 < 0', 'warning'); return; }
        if (diff === 0) { this.showExtendOutlineModal = false; return; }
        const isExpand = diff > 0;
        const confirmMsg = isExpand
            ? `确定把项目「${this.project.title}」的大纲从 ${generated} 章扩到 ${newTotal} 章吗？\n\n• 已有章节：不会修改\n• 新增章节：${diff} 章\n• 架构层（分卷/剧情线/四幕）：${this.extendOutlineArchitecture ? '同步扩写' : '保留原架构'}`
            : `确定把项目「${this.project.title}」的大纲从 ${generated} 章缩减到 ${newTotal} 章吗？\n\n• 尾部删除 ${Math.abs(diff)} 章\n• 保留的章节（1-${newTotal}）不会修改\n• 警告：已生成的对应章节细纲/伏笔也会被清理`;
        if (!confirm(confirmMsg)) return;

        this.extendOutlineBusy = true;
        this.showExtendOutlineModal = false;
        try {
            console.log('[ExtendOutline] 提交', { newTotal, isExpand });
            const res = await fetch(
                `/api/workflow/project/${this.project.id}/extend-outline?target_chapters=${newTotal}&extend_architecture=${this.extendOutlineArchitecture}`,
                { method: 'POST' }
            );
            const data = await res.json();
            if (data.status === 'ok' && !data.task_id) {
                await this._afterExtendOutline(data, isExpand);
                return;
            }
            if (data.status === 'submitted' && data.task_id) {
                Alpine.store('app').toast(`大纲${isExpand ? '扩写' : '缩减'}任务已提交`, 'info');
                this.showTaskManager = true;
                await this.refreshAllTasks();
                const task = await this._pollTask(data.task_id, {
                    onProgress: () => this.refreshAllTasks(),
                });
                if (task.status === 'completed' && task.result) {
                    await this._afterExtendOutline(task.result, isExpand);
                } else if (task.status === 'failed') {
                    Alpine.store('app').toast('操作失败: ' + (task.error || 'unknown'), 'error');
                }
                return;
            }
            Alpine.store('app').toast('操作失败: ' + (data.error || JSON.stringify(data)), 'error');
        } catch (e) {
            console.error('[confirmExtendOutline] failed:', e);
            Alpine.store('app').toast('操作失败: ' + e.message, 'error');
        } finally {
            this.extendOutlineBusy = false;
        }
    },

    async _afterExtendOutline(data, isExpand) {
        if (!this.project) return;
        if (data.status !== 'ok') {
            Alpine.store('app').toast('操作失败: ' + (data.error || JSON.stringify(data)), 'error');
            return;
        }
        const action = isExpand ? '扩写' : '缩减';
        let msg;
        if (isExpand) {
            msg = `✅ 大纲${action}完成！原 ${data.old_total} 章 → 新 ${data.new_total} 章，新增 ${data.added_chapters || 0} 章`;
        } else {
            msg = `✅ 大纲${action}完成！原 ${data.old_total} 章 → 新 ${data.new_total} 章，删除尾部 ${data.removed_chapters || 0} 章`;
        }
        Alpine.store('app').toast(msg, 'success', 6000);
        await this.loadProject(this.project.id);
        await this._refreshBootstrapData();
        await this.loadChapters(this.project.id);
        console.log(`[ExtendOutline] ${action} 完成: ${data.old_total} → ${data.new_total}`);
    },

    // ─── 字数调整（独立功能，只动字数）───

    openWordAdjustModal() {
        if (!this.currentChapter || !this.currentChapter.content) {
            Alpine.store('app').toast('当前章节没有正文内容，无法调整字数', 'warning');
            return;
        }
        this.wordAdjustUseCustom = false;
        this.wordAdjustCustomMin = this.project.word_count_min || null;
        this.wordAdjustCustomTarget = this.project.target_word_count || null;
        this.wordAdjustCustomMax = this.project.word_count_max || null;
        this.wordAdjustPctInput = 10;
        this.recalcWordAdjustPlan();
        this.wordAdjustTaskId = null;
        this.wordAdjustSubmitting = false;
        this.showWordAdjustModal = true;
    },

    recalcWordAdjustPlan() {
        if (!this.currentChapter) return;
        const currentChars = this.currentChapter.word_count || 0;
        let minW, maxW;
        if (this.wordAdjustUseCustom) {
            minW = Number(this.wordAdjustCustomMin) || this.project.word_count_min || 0;
            maxW = Number(this.wordAdjustCustomMax) || this.project.word_count_max || 0;
        } else {
            minW = this.project.word_count_min || 0;
            maxW = this.project.word_count_max || 0;
        }
        if (minW > maxW) [minW, maxW] = [maxW, minW];
        // 兜底：项目未设上下限时避免把上限当 0
        if (maxW <= 0) maxW = Math.max(currentChars, this.project.target_word_count || 3000);
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

    applyWordAdjustPctPreset(pct) {
        if (!pct || pct <= 0 || pct >= 100) {
            Alpine.store('app').toast('百分比必须在 1-99 之间', 'warning');
            return;
        }
        const baseTarget = Number(this.wordAdjustCustomTarget)
            || this.project.target_word_count || 3000;
        const delta = Math.round(baseTarget * pct / 100);
        this.wordAdjustUseCustom = true;
        this.wordAdjustCustomMin = Math.max(0, baseTarget - delta);
        this.wordAdjustCustomTarget = baseTarget;
        this.wordAdjustCustomMax = baseTarget + delta;
        this.wordAdjustPctInput = pct;
        this.recalcWordAdjustPlan();
    },

    closeWordAdjustModal() {
        if (this.wordAdjustSubmitting) {
            Alpine.store('app').toast('调整进行中，请等待完成', 'warning');
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
            const body = { project_id: this.project.id, chapter_id: this.currentChapter.id };
            if (this.wordAdjustUseCustom) {
                if (this.wordAdjustCustomMin != null && this.wordAdjustCustomMin !== '') body.min_words = Number(this.wordAdjustCustomMin);
                if (this.wordAdjustCustomMax != null && this.wordAdjustCustomMax !== '') body.max_words = Number(this.wordAdjustCustomMax);
                if (this.wordAdjustCustomTarget != null && this.wordAdjustCustomTarget !== '') body.target_words = Number(this.wordAdjustCustomTarget);
            }
            console.log('[WordAdjust] 提交', body, this.wordAdjustPlan);
            const res = await fetch('/api/chapters/adjust-word-count', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const data = await res.json();
            if (!res.ok || !data.task_id) {
                Alpine.store('app').toast('字数调整提交失败：' + (data.detail || JSON.stringify(data)), 'error');
                this.wordAdjustSubmitting = false;
                return;
            }
            this.wordAdjustTaskId = data.task_id;
            this.showWordAdjustModal = false;
            this.showTaskManager = true;
            await this.refreshAllTasks();
            if (this._taskPollHandle) clearInterval(this._taskPollHandle);
            this._taskPollHandle = setInterval(() => {
                this._pollWordAdjust();
                if (this.showTaskManager) this.refreshAllTasks();
            }, 2000);
            this._pollWordAdjust();
        } catch (e) {
            Alpine.store('app').toast('字数调整请求失败: ' + e.message, 'error');
            this.wordAdjustSubmitting = false;
        }
    },

    async _pollWordAdjust() {
        if (!this.wordAdjustTaskId) return;
        try {
            const res = await fetch(`/api/tasks/${this.wordAdjustTaskId}`);
            if (!res.ok) return;
            const task = await res.json();
            if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                if (this._taskPollHandle) clearInterval(this._taskPollHandle);
                this._taskPollHandle = null;
                this.wordAdjustSubmitting = false;
                if (task.status === 'completed') {
                    const r = task.result || {};
                    const rangeTag = r.is_custom_range ? '（自定义）' : '（项目默认）';
                    if (r.skipped) {
                        Alpine.store('app').toast(`当前字数（${r.current_chars}）已在区间 ${r.min_chars}~${r.max_chars} 内${rangeTag}，无需调整。`, 'info', 6000);
                    } else {
                        const sign = r.delta >= 0 ? '+' : '';
                        Alpine.store('app').toast(`字数调整完成：${r.current_chars} → ${r.new_chars} 字（${sign}${r.delta}）`, 'success', 6000);
                    }
                    this.wordAdjustTaskId = null;
                    await this.loadChapters(this.project.id);
                    if (this.currentChapter) {
                        const ch = this.chapters.find((c) => c.id === this.currentChapter.id);
                        if (ch) await this.selectChapter(ch);
                    }
                } else if (task.status === 'failed') {
                    Alpine.store('app').toast('字数调整失败：' + (task.error || '未知错误'), 'error');
                    this.wordAdjustTaskId = null;
                }
            }
        } catch (e) {
            console.warn('[WordAdjust] 轮询失败:', e);
        }
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('novel_editor', `
<div class="page novel-editor-page">
  <template x-if="loading">
    <div class="page-loading"><div class="spinner"></div><p>加载项目中...</p></div>
  </template>

  <template x-if="!loading && project">
    <div class="editor-layout">
      <!-- 顶部信息栏 -->
      <header class="editor-header">
        <div class="header-left">
          <button class="btn-icon" @click="backToHome()" title="返回项目列表">←</button>
          <h2 x-text="project.title"></h2>
          <span class="project-id-badge" x-show="project.id" x-text="'#' + project.id"></span>
          <span class="llm-badge" x-show="currentLlmLabel">🤖 <span x-text="currentLlmLabel"></span></span>
          <span class="llm-badge" x-show="ragEnabled === false"
                title="RAG 未启用：可在「全局设置 → RAG 向量」选择本地 CPU 模型或在线 Embedding API">⚠️ RAG 未启用</span>
        </div>
        <div class="header-right">
          <button class="btn-secondary" @click="openTaskManager()" title="任务管理">📋 任务</button>
          <button class="btn-secondary" @click="openExportModal()">📤 导出</button>
          <button class="btn-secondary" @click="openTextReplaceModal()">🔄 替换</button>
          <button class="btn-secondary" @click="goToSettings()">⚙️ 设置</button>
        </div>
      </header>

      <!-- 写作台之前的 AI 补全 banner -->
      <template x-if="bootstrapBanner.visible">
        <div class="ai-bootstrap-banner" :class="'banner-' + bootstrapBanner.kind">
          <span class="banner-icon" x-text="{
            in_flight: '⏳',
            awaiting_commit: '✅',
            partial_failed: '⚠️',
            aborted: '🔌',
            cancelled: '⛔'
          }[bootstrapBanner.kind] || '🤖'"></span>
          <div class="banner-text">
            <strong x-text="{
              in_flight: 'AI 补全进行中：',
              awaiting_commit: 'AI 补全完成：',
              partial_failed: 'AI 补全部分失败：',
              aborted: '服务重启导致中断：',
              cancelled: 'AI 补全被取消：'
            }[bootstrapBanner.kind] || 'AI 补全：'"></strong>
            <span x-text="bootstrapBanner.message"></span>
          </div>
          <button class="btn-small"
                  :disabled="bootstrapBanner.committing"
                  @click="bootstrapBanner.kind === 'awaiting_commit' ? commitBootstrap(false, bootstrapBanner.projectId, bootstrapBanner.runId) : openBootstrapWizard(bootstrapBanner.projectId, bootstrapBanner.runId)"
                  x-text="{
                    in_flight: '查看进度',
                    awaiting_commit: bootstrapBanner.committing ? '提交中...' : '提交入库',
                    partial_failed: '查看/重跑',
                    aborted: '重新启动',
                    cancelled: '查看详情'
                  }[bootstrapBanner.kind] || '查看'"></button>
          <button class="btn-small btn-dismiss" @click="dismissBootstrapBanner()">×</button>
        </div>
      </template>

      <div class="editor-body">
        <!-- 左侧边栏：章节 + 工具 -->
        <aside class="editor-sidebar">
          <div class="sidebar-section">
            <div class="sidebar-header">
              <span>📚 章节</span>
              <button class="btn-icon" @click="createChapter()" title="新建章节">➕</button>
            </div>
            <ul class="chapter-list">
              <template x-if="chapters.length === 0">
                <li class="empty-hint">暂无章节</li>
              </template>
              <template x-for="ch in chapters" :key="ch.id">
                <li :class="{ active: currentChapter && currentChapter.id === ch.id }" @click="selectChapter(ch)">
                  <span x-text="(ch.order + 1) + '. ' + ch.title"></span>
                  <span class="word-count" :style="getWordCountStyle(ch)" x-text="ch.word_count + '字'"></span>
                </li>
              </template>
            </ul>
          </div>

          <div class="sidebar-section">
            <div class="sidebar-header"><span>🛠 工具</span></div>
            <div class="tool-buttons">
              <button @click="setPanel('writing')" :class="{ active: activePanel === 'writing' }">✍️ 写作</button>
              <button @click="setPanel('outline-plan'); outlineSubPanel = 'overview'" :class="{ active: activePanel === 'outline-plan' }">📋 大纲</button>
              <button @click="setPanel('worldbuilding')" :class="{ active: activePanel === 'worldbuilding' }">🌍 世界观/背景</button>
              <button @click="setPanel('character')" :class="{ active: activePanel === 'character' }">👥 角色</button>
              <button @click="setPanel('theme')" :class="{ active: activePanel === 'theme' }">🎯 主题/伏笔</button>
              <button @click="setPanel('plot')" :class="{ active: activePanel === 'plot' }">📊 剧情追踪</button>
              <button @click="pipelineSetupSetupModal()" :disabled="!canRunPipeline">🚀 单章生成</button>
              <button @click="openBatchGenerateModal()" :disabled="batchGenerating">📦 批量生成</button>
            </div>
          </div>

          <!-- 章节进度 -->
          <div class="sidebar-section">
            <div class="sidebar-header"><span>📈 章节进度</span></div>
            <div class="word-progress">
              <div class="wp-bar">
                <div class="wp-fill" :style="'width: ' + chapterProgressPercent + '%'"></div>
              </div>
              <div class="wp-text">
                <span x-text="generatedChapterCount + ' / ' + totalChapters + ' 章'"></span>
                <span x-text="chapterProgressPercent + '%'"></span>
              </div>
            </div>
          </div>
        </aside>

        <!-- 中间：主编辑区 -->
        <main class="editor-main">
          <!-- 写作面板 -->
          <div x-show="activePanel === 'writing'" class="writing-desk">
            <template x-if="!currentChapter">
              <div class="empty-state"><p>📝 请从左侧选择或创建一个章节开始写作</p></div>
            </template>

            <template x-if="currentChapter">
              <div class="writing-desk-inner">
                <!-- 章节信息栏 + 页签 -->
                <div class="chapter-header-bar">
                  <div class="chapter-info-left">
                    <span class="chapter-num" x-text="'第' + (currentChapter.order + 1) + '章'"></span>
                    <input type="text" class="chapter-title-input" x-model="currentChapter.title" @change="saveChapter()">
                    <span class="chapter-meta" x-text="'字数: ' + (currentChapter.word_count || 0)"></span>
                    <span class="chapter-meta" x-text="wordCountStatus"></span>
                  </div>
                  <div class="writing-tabs">
                    <button :class="{ active: writingTab === 'content' }" @click="setWritingTab('content')">正文</button>
                    <button :class="{ active: writingTab === 'outline' }" @click="setWritingTab('outline')">细纲</button>
                    <button :class="{ active: writingTab === 'review' }" @click="setWritingTab('review')">评审报告</button>
                    <button :class="{ active: writingTab === 'versions' }" @click="setWritingTab('versions'); loadChapterVersions()">📦 版本</button>
                    <button :class="{ active: writingTab === 'fingerprint' }" @click="setWritingTab('fingerprint'); loadFingerprint(currentChapter.id)">🔍 LLM指纹</button>
                    <button :class="{ active: writingTab === 'status' }" @click="setWritingTab('status'); loadPostProcessing(currentChapter.id)">🔄 状态变化</button>
                  </div>
                </div>

                <!-- 正文编辑 -->
                <div x-show="writingTab === 'content'" class="writing-tab-content">
                  <template x-if="chapterSwitching">
                    <div class="loading-hint">⏳ 正在加载章节...</div>
                  </template>
                  <template x-if="!chapterSwitching">
                    <div>
                      <!-- 章节准备信息（已发生事件 + RAG 相似） -->
                      <details class="prep-info-card" x-show="currentChapter && currentChapter.id">
                        <summary>📚 已发生事件 + RAG 相似过去章节
                          <span x-show="prepInfoLoading">⏳ 计算中...</span>
                          <span x-show="!prepInfoLoading && chapterPrepInfo && chapterPrepInfo.max_dedup_similarity > 0">(最高相似度 <span x-text="(chapterPrepInfo?.max_dedup_similarity || 0).toFixed(2)"></span>)</span>
                        </summary>
                        <div class="prep-info-body">
                          <template x-if="prepInfoLoading"><p class="loading-hint">正在检索 RAG 相似事件...</p></template>
                          <template x-if="!prepInfoLoading">
                            <div>
                              <h5>⚠️ 已发生事件（不得重复）</h5>
                              <div class="empty-hint" x-show="!chapterPrepInfo || (chapterPrepInfo.previous_events || []).length === 0">暂无（首章）</div>
                              <ul>
                                <template x-for="ev in (chapterPrepInfo?.previous_events || [])" :key="'pe-' + ev.chapter">
                                  <li><strong>第<span x-text="ev.chapter"></span>章《<span x-text="ev.title"></span>》</strong>: <span x-text="ev.signature"></span></li>
                                </template>
                              </ul>
                              <h5>🔍 RAG 相似过去事件</h5>
                              <div class="empty-hint" x-show="!chapterPrepInfo || (chapterPrepInfo.dedup_matches || []).length === 0">RAG 未命中相似事件</div>
                              <ul>
                                <template x-for="m in (chapterPrepInfo?.dedup_matches || [])" :key="'dm-' + m.chapter">
                                  <li :style="{ color: m.similarity >= 0.65 ? '#d9534f' : '#666' }">
                                    第<span x-text="m.chapter"></span>章《<span x-text="m.title"></span>》(相似度 <span x-text="m.similarity?.toFixed(2)"></span>): <span x-text="m.signature"></span>
                                  </li>
                                </template>
                              </ul>
                            </div>
                          </template>
                        </div>
                      </details>

                      <textarea class="content-editor" x-model="currentChapter.content" @input="onContentChange()" placeholder="开始写作..."></textarea>
                      <div class="writing-actions">
                        <button class="btn-primary" @click="saveChapter()" :disabled="!chapterDirty">💾 保存</button>
                        <button class="btn-secondary" @click="pipelineSetupSetupModal()" :disabled="!canRunPipeline">🚀 AI 生成</button>
                        <button class="btn-secondary" @click="openWordAdjustModal()"
                                :disabled="!currentChapter || !currentChapter.content"
                                title="只调整字数（缩写或扩写），不动剧情结构">📐 调整字数</button>
                      </div>
                    </div>
                  </template>
                </div>

                <!-- 细纲 -->
                <div x-show="writingTab === 'outline'" class="writing-tab-content writing-outline-panel">
                  <template x-if="chapterOutlinesMap[currentChapter.id]">
                    <div class="outline-detail">
                      <div class="outline-meta-grid">
                        <div class="omg-item"><span>位置</span><strong x-text="chapterOutlinesMap[currentChapter.id].chapter_position || '-'"></strong></div>
                        <div class="omg-item"><span>节拍</span><strong x-text="chapterOutlinesMap[currentChapter.id].pacing || '-'"></strong></div>
                        <div class="omg-item"><span>字数目标</span><strong x-text="(chapterOutlinesMap[currentChapter.id].target_word_count || 0) + ' 字'"></strong></div>
                        <div class="omg-item"><span>状态</span><strong x-text="chapterOutlinesMap[currentChapter.id].status || '-'"></strong></div>
                      </div>
                      <div class="outline-section"><h4>核心内容</h4><div class="outline-text" x-text="chapterOutlinesMap[currentChapter.id].key_content || '暂无'"></div></div>
                      <div class="outline-section"><h4>剧情推进</h4><div class="outline-text" x-text="chapterOutlinesMap[currentChapter.id].plot_advance || '暂无'"></div></div>
                      <template x-if="(chapterOutlinesMap[currentChapter.id].conflicts || []).length > 0">
                        <div class="outline-section"><h4>冲突/矛盾</h4><ul><template x-for="(c, i) in chapterOutlinesMap[currentChapter.id].conflicts" :key="i"><li x-text="c"></li></template></ul></div>
                      </template>
                      <template x-if="(chapterOutlinesMap[currentChapter.id].highlights || []).length > 0">
                        <div class="outline-section"><h4>高光时刻</h4><ul><template x-for="(h, i) in chapterOutlinesMap[currentChapter.id].highlights" :key="i"><li x-text="h"></li></template></ul></div>
                      </template>
                    </div>
                  </template>
                  <template x-if="!chapterOutlinesMap[currentChapter.id]">
                    <div class="empty-state"><p>本章暂无细纲</p></div>
                  </template>
                </div>

                <!-- 评审报告 -->
                <div x-show="writingTab === 'review'" class="writing-tab-content writing-review-panel">
                  <template x-if="!previewReview">
                    <div class="empty-state"><p>暂无评审报告</p></div>
                  </template>
                  <template x-if="previewReview">
                    <div class="review-report">
                      <div class="review-score">综合评分: <strong x-text="previewReview.overall_score?.toFixed(1) || '-'"></strong> / 100</div>
                      <template x-if="previewReview.summary">
                        <div class="review-section"><h4>总结</h4><p x-text="previewReview.summary"></p></div>
                      </template>
                      <template x-if="previewReview.issues">
                        <div class="review-section"><h4>问题</h4><p x-text="previewReview.issues"></p></div>
                      </template>
                    </div>
                  </template>
                </div>

                <!-- 章节版本 -->
                <div x-show="writingTab === 'versions'" class="writing-tab-content">
                  <div class="empty-state" x-show="!chapterVersions || chapterVersions.length === 0"><p>暂无历史版本</p></div>
                  <div x-show="chapterVersions && chapterVersions.length > 0" style="max-height: 600px; overflow-y: auto;">
                    <table class="data-table">
                      <thead><tr><th>版本</th><th>时间</th><th>字数</th><th>操作</th></tr></thead>
                      <tbody>
                        <template x-for="v in chapterVersions" :key="v.version_num">
                          <tr>
                            <td x-text="'v' + v.version_num"></td>
                            <td x-text="formatDate(v.created_at)"></td>
                            <td x-text="v.word_count || '-'"></td>
                            <td><button class="btn-small" @click="_rollbackToVersion(v.version_num)">↩ 回滚</button></td>
                          </tr>
                        </template>
                      </tbody>
                    </table>
                  </div>
                </div>

                <!-- LLM 指纹 -->
                <div x-show="writingTab === 'fingerprint'" class="writing-tab-content writing-fingerprint-panel">
                  <template x-if="fingerprintLoading"><p class="loading-hint">⏳ 加载中...</p></template>
                  <template x-if="!fingerprintLoading && !currentChapter.fingerprint">
                    <div class="empty-state"><p>暂无 LLM 指纹数据</p></div>
                  </template>
                  <template x-if="!fingerprintLoading && currentChapter.fingerprint">
                    <div class="fingerprint-report">
                      <pre x-text="JSON.stringify(currentChapter.fingerprint, null, 2)"></pre>
                    </div>
                  </template>
                </div>

                <!-- 本章状态变化（后处理：弧光 / 关系 / 伏笔） -->
                <div x-show="writingTab === 'status'" class="writing-tab-content writing-status-panel">
                  <template x-if="postProcessingLoading"><p class="loading-hint">⏳ 加载中...</p></template>
                  <template x-if="!postProcessingLoading">
                    <div class="post-processing-report">
                      <div class="empty-hint" x-show="!postProcessing || (
                        (postProcessing.arc_updates || []).length === 0 &&
                        (postProcessing.relation_updates || []).length === 0 &&
                        (postProcessing.foreshadow_updates || []).length === 0 &&
                        (postProcessing.new_characters || []).length === 0
                      )">暂无状态变化（本章可能未跑后处理）</div>

                      <div x-show="(postProcessing?.arc_updates || []).length > 0">
                        <h5>🎭 角色弧光</h5>
                        <ul>
                          <template x-for="a in (postProcessing?.arc_updates || [])" :key="'arc-' + a.character_name">
                            <li><strong x-text="a.character_name"></strong>：<span x-text="a.current_state || a.new_state || ''"></span></li>
                          </template>
                        </ul>
                      </div>

                      <div x-show="(postProcessing?.relation_updates || []).length > 0">
                        <h5>🔗 角色关系</h5>
                        <ul>
                          <template x-for="(r, ri) in (postProcessing?.relation_updates || [])" :key="'rel-' + ri">
                            <li><span x-text="r.from"></span> → <span x-text="r.to"></span>：<span x-text="r.new_type || r.type || ''"></span>
                              <span x-show="r.description">（<span x-text="r.description"></span>）</span></li>
                          </template>
                        </ul>
                      </div>

                      <div x-show="(postProcessing?.foreshadow_updates || []).length > 0">
                        <h5>🪶 伏笔</h5>
                        <ul>
                          <template x-for="(f, fi) in (postProcessing?.foreshadow_updates || [])" :key="'fs-' + fi">
                            <li><strong x-text="f.title || f.name || ''"></strong>：<span x-text="f.new_status || f.status || f.evidence || ''"></span></li>
                          </template>
                        </ul>
                      </div>

                      <div x-show="(postProcessing?.new_characters || []).length > 0">
                        <h5>🆕 新角色</h5>
                        <ul>
                          <template x-for="(c, ci) in (postProcessing?.new_characters || [])" :key="'newc-' + ci">
                            <li><strong x-text="c.name"></strong>（<span x-text="c.role || ''"></span>）</li>
                          </template>
                        </ul>
                      </div>

                      <div x-show="(postProcessing?.notifications || []).length > 0">
                        <h5>🔔 提示</h5>
                        <ul>
                          <template x-for="(n, ni) in (postProcessing?.notifications || [])" :key="'note-' + ni">
                            <li><span x-text="n.title || n.type || ''"></span>：<span x-text="n.message || ''"></span></li>
                          </template>
                        </ul>
                      </div>
                    </div>
                  </template>
                </div>
              </div>
            </template>
          </div>

          <!-- ═══ 项目大纲面板（总纲 + 每章一句话大纲） ═══ -->
          <div x-show="activePanel === 'outline-plan'" class="panel-section">
            <div class="panel-page-header">
              <h2>📋 大纲与细纲</h2>
              <div class="panel-header-actions">
                <button class="btn-secondary" @click="rerunBootstrapStageFromPanel('stage_4a_outline')"
                        :disabled="!project || rerunStageBusy['stage_4a_outline']"
                        :title="rerunStageBtnTitle('stage_4a_outline')">
                  <span x-show="!rerunStageBusy['stage_4a_outline']">🔄 重新生成大纲</span>
                  <span x-show="rerunStageBusy['stage_4a_outline']">⏳ 生成中...</span>
                </button>
                <button class="btn-secondary" @click="openExtendOutlineModal()"
                        :disabled="!project || extendOutlineBusy"
                        :title="extendOutlineBtnTitle()">
                  <span x-show="!extendOutlineBusy">📈 扩写大纲</span>
                  <span x-show="extendOutlineBusy">⏳ 扩写中...</span>
                </button>
              </div>
            </div>

            <div class="outline-meta">
              <div class="meta-item">
                <span>预设总章节</span>
                <strong x-text="effectiveTotalChapters() ? effectiveTotalChapters() + ' 章' : '未设定'"></strong>
              </div>
              <div class="meta-item">
                <span>章节字数目标</span>
                <strong x-text="(project?.target_word_count || 0) + ' 字'"></strong>
              </div>
              <div class="meta-item">
                <span>字数范围</span>
                <strong x-text="(project?.word_count_min || 0) + '～' + (project?.word_count_max || 0) + ' 字'"></strong>
              </div>
              <div class="meta-item">
                <span>已规划章节</span>
                <strong x-text="chapterOneLineOutlines.length"></strong>
              </div>
            </div>

            <template x-if="bootstrapData && bootstrapData.outline && (bootstrapData.outline.outline_text || (bootstrapData.outline.plot_lines || []).length)">
              <div class="ai-preview-block">
                <div class="ai-preview-header">
                  <span>🤖 AI 生成大纲</span>
                  <span class="ai-preview-hint" x-text="bootstrapAiOutlineSummary()"></span>
                </div>
                <template x-if="bootstrapData.outline.outline_text">
                  <div class="outline-summary">
                    <h4>📖 总纲 / 概要</h4>
                    <p x-text="bootstrapData.outline.outline_text"></p>
                  </div>
                </template>
                <template x-if="(bootstrapData.outline.plot_lines || []).length > 0">
                  <div class="outline-plotlines">
                    <h4>📋 剧情线</h4>
                    <template x-for="(pl, idx) in bootstrapData.outline.plot_lines" :key="'pl-' + idx">
                      <div class="plotline-card">
                        <div class="pl-header">
                          <strong x-text="pl.title || '未命名剧情线'"></strong>
                          <span class="pl-range" x-text="'第' + (pl.from_chapter || '?') + '章 → 第' + (pl.to_chapter || '?') + '章'"></span>
                        </div>
                        <div class="pl-desc" x-text="pl.description || '暂无描述'"></div>
                      </div>
                    </template>
                  </div>
                </template>
                <template x-if="bootstrapData.outline.structure && (bootstrapData.outline.structure.acts || []).length > 0">
                  <div class="outline-structure">
                    <h4>🎭 结构</h4>
                    <div class="act-list">
                      <template x-for="(act, idx) in bootstrapData.outline.structure.acts" :key="'act-' + idx">
                        <div class="act-card">
                          <div class="act-name" x-text="act.name || '未命名'"></div>
                          <div class="act-range" x-text="'第' + (act.from_chapter || '?') + '章 → 第' + (act.to_chapter || '?') + '章'"></div>
                        </div>
                      </template>
                    </div>
                  </div>
                </template>
                <template x-if="bootstrapData.outline.pacing_notes">
                  <div class="outline-pacing">
                    <h4>⏱️ 节奏规划</h4>
                    <p x-text="bootstrapData.outline.pacing_notes"></p>
                  </div>
                </template>

                <template x-if="chapterOneLineOutlines.length > 0">
                  <div class="outline-chapter-list">
                    <h4>📑 每章一句话大纲
                      <span class="outline-count" x-text="'（共 ' + chapterOneLineOutlines.length + ' 章）'"></span>
                    </h4>
                    <div class="chapter-outline-grid">
                      <template x-for="(co, idx) in chapterOneLineOutlines" :key="'co-' + (co.chapter_num || idx)">
                        <div class="chapter-outline-mini">
                          <div class="com-head">
                            <span class="com-num" x-text="'第' + (co.chapter_num || (idx + 1)) + '章'"></span>
                            <span class="com-vol" x-show="co.volume_num" x-text="'第' + co.volume_num + '卷'"></span>
                            <span class="com-pos" x-show="co.chapter_position" x-text="co.chapter_position"></span>
                          </div>
                          <div class="com-title" x-text="co.title || '未命名'"></div>
                          <div class="com-content" x-text="co.key_content || '（暂无核心内容）'"></div>
                          <template x-if="co.plot_advance">
                            <div class="com-advance">➡️ <span x-text="co.plot_advance"></span></div>
                          </template>
                        </div>
                      </template>
                    </div>
                  </div>
                </template>
              </div>
            </template>
            <template x-if="!bootstrapData || !bootstrapData.outline || (!bootstrapData.outline.outline_text && (bootstrapData.outline.plot_lines || []).length === 0)">
              <p class="empty-hint">暂无 AI 生成的大纲（项目未跑过引导补全，或阶段失败）。可点右上角「🔄 重新生成大纲」。</p>
            </template>
          </div>

          <!-- ═══ 世界观 / 背景面板 ═══ -->
          <div x-show="activePanel === 'worldbuilding'" class="panel-section">
            <div class="panel-page-header">
              <h2>🌍 世界观 / 背景</h2>
              <div class="panel-header-actions">
                <button class="btn-secondary" @click="rerunBootstrapStageFromPanel('stage_2c_world')"
                        :disabled="!project || rerunStageBusy['stage_2c_world']"
                        :title="rerunStageBtnTitle('stage_2c_world')">
                  <span x-show="!rerunStageBusy['stage_2c_world']">🔄 重新生成世界观</span>
                  <span x-show="rerunStageBusy['stage_2c_world']">⏳ 生成中...</span>
                </button>
              </div>
            </div>

            <template x-if="preambleText">
              <div class="outline-summary world-premise">
                <h4>📝 小说背景</h4>
                <p x-text="preambleText"></p>
              </div>
            </template>

            <template x-if="hasWorldData">
              <div>
                <template x-for="cat in worldCategories" :key="cat.category">
                  <div class="world-category">
                    <h4 x-text="cat.category"></h4>
                    <template x-for="(entry, idx) in cat.entries" :key="idx">
                      <div class="world-entry">
                        <strong x-text="entry.title"></strong>
                        <p x-text="entry.content"></p>
                        <template x-if="entry.tags && entry.tags.length">
                          <div class="world-tags">
                            <template x-for="tag in entry.tags" :key="tag">
                              <span class="tag" x-text="'#' + tag"></span>
                            </template>
                          </div>
                        </template>
                      </div>
                    </template>
                  </div>
                </template>
              </div>
            </template>
            <template x-if="!hasWorldData && !preambleText">
              <p class="empty-hint">暂无世界观 / 背景信息。可点右上角「🔄 重新生成世界观」。</p>
            </template>
          </div>

          <!-- 角色面板 -->
          <div x-show="activePanel === 'character'" class="panel-section">
            <h3>👥 角色列表（共 <span x-text="characters.length"></span> 个）</h3>
            <template x-if="characters.length === 0"><p class="empty-hint">暂无角色</p></template>
            <div class="card-grid">
              <template x-for="c in characters" :key="c.id">
                <div class="info-card">
                  <h4 x-text="c.name"></h4>
                  <span class="tag" x-text="c.role"></span>
                  <p x-text="c.description || '暂无描述'"></p>
                </div>
              </template>
            </div>
          </div>

          <!-- 主题/伏笔面板 -->
          <div x-show="activePanel === 'theme'" class="panel-section">
            <h3>🎯 主题（<span x-text="themes.length"></span>）/ 🪝 伏笔（<span x-text="foreshadowings.length"></span>）</h3>
            <div class="sub-section">
              <h4>主题</h4>
              <template x-if="themes.length === 0"><p class="empty-hint">暂无主题</p></template>
              <div class="card-list">
                <template x-for="t in themes" :key="t.id">
                  <div class="info-card"><h4 x-text="t.name || t.title || '-'"></h4><p x-text="t.description || t.content || ''"></p></div>
                </template>
              </div>
            </div>
            <div class="sub-section">
              <h4>伏笔</h4>
              <template x-if="foreshadowings.length === 0"><p class="empty-hint">暂无伏笔</p></template>
              <div class="card-list">
                <template x-for="f in foreshadowings" :key="f.id">
                  <div class="info-card">
                    <h4 x-text="f.title || f.name || '-'"></h4>
                    <span class="tag" x-text="f.status || 'active'"></span>
                    <p x-text="f.description || f.content || ''"></p>
                  </div>
                </template>
              </div>
            </div>
          </div>

          <!-- 剧情追踪面板 -->
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
        </main>
      </div>

      <!-- 底部状态栏 -->
      <footer class="editor-footer">
        <span>📚 章节：<strong x-text="generatedChapterCount + ' / ' + totalChapters"></strong></span>
        <template x-if="tokenUsage">
          <span>📊 Token：输入 <strong x-text="tokenUsage.input_tokens || tokenUsage.prompt_tokens || 0"></strong> / 输出 <strong x-text="tokenUsage.output_tokens || tokenUsage.completion_tokens || 0"></strong></span>
        </template>
        <span x-show="batchGenerating">⏳ 批量生成中...</span>
        <span x-show="pipelineTask && ['pending','running'].includes(pipelineTask.status)">⏳ 单章生成中...</span>
      </footer>

      <!-- ═══ Pipeline 单章生成弹窗 ═══ -->
      <template x-if="showPipelineSetup">
        <div class="modal-overlay" @click.self="showPipelineSetup = false">
          <div class="modal">
            <button class="modal-close-x" @click="showPipelineSetup = false">×</button>
            <h2>🚀 单章生成</h2>
            <p>将为当前章节《<strong x-text="currentChapter?.title"></strong>》启动生成流水线</p>
            <label>生成引导（可选）
              <textarea x-model="generatePrompt" rows="4" placeholder="描述本章希望的方向、情节..."></textarea>
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showPipelineSetup = false">取消</button>
              <button class="btn-primary" @click="startPipelineGuide(generatePrompt)">🚀 开始生成</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ Pipeline 进度弹窗（9 步） ═══ -->
      <template x-if="showPipelineProgress">
        <div class="modal-overlay">
          <div class="modal modal-wide pipeline-modal">
            <button class="modal-close-x" @click="closePipelinePanel(false)">×</button>
            <h2>⏳ 生成进度</h2>
            <div class="pipeline-head">
              <span class="pipeline-task-id">任务：<code x-text="pipelineTaskId || (pipelineTask && pipelineTask.id) || '-'"></code></span>
              <span class="status-pill" :class="'status-' + pipelineStatus" x-text="taskStatusLabel(pipelineStatus)"></span>
              <span class="pipeline-elapsed" x-text="'已用时 ' + pipelineElapsedText"></span>
            </div>
            <div class="pipeline-progress">
              <div class="progress-bar">
                <div class="progress-fill" :style="'width: ' + pipelineProgressPct + '%'"></div>
              </div>
              <span x-text="pipelineProgressPct + '%'"></span>
            </div>
            <div class="pipeline-stages">
              <template x-for="st in pipelineStagesView" :key="st.id">
                <div class="pipeline-stage" :class="'stage-' + st.status">
                  <div class="ps-main">
                    <div class="ps-head">
                      <span class="ps-icon" x-text="pipelineStageIcon(st.status)"></span>
                      <span class="ps-label" x-text="st.label"></span>
                      <span class="ps-score" x-show="st.score" x-text="'(' + (st.score ? st.score.toFixed(1) : '-') + '/100)'"></span>
                      <span class="ps-time" x-show="st.duration_ms != null || st.status === 'running'"
                            x-text="st.elapsed_display + 's'"></span>
                    </div>
                    <div class="stage-bar"><div class="stage-bar-fill" :style="'width: ' + st.elapsed_pct + '%'"></div></div>
                    <div class="ps-error" x-show="st.error" x-text="st.error"></div>
                  </div>
                </div>
              </template>
            </div>
            <template x-if="pipelineStatus === 'completed'">
              <div class="pipeline-result">✅ 生成完成，本章最终 <strong x-text="(pipelineFinalResult && pipelineFinalResult.final_word_count) || 0"></strong> 字</div>
            </template>
            <template x-if="pipelineStatus === 'failed'">
              <div class="pipeline-result pipeline-failed">❌ 失败：<span x-text="(pipelineFinalResult && pipelineFinalResult.error) || (pipelineTask && pipelineTask.error) || '未知错误'"></span></div>
            </template>
            <div class="form-footer">
              <button class="btn-secondary" @click="closePipelinePanel(true)">关闭</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 批量生成弹窗 ═══ -->
      <template x-if="showBatchGenerate">
        <div class="modal-overlay" @click.self="showBatchGenerate = false">
          <div class="modal">
            <button class="modal-close-x" @click="showBatchGenerate = false">×</button>
            <h2>📦 批量生成</h2>
            <label>起始章节
              <input type="number" x-model.number="batchGenerateStart" min="1" placeholder="1">
              <span class="field-hint">从「第 <span x-text="batchStartDisplay"></span> 章」开始生成（默认 = 当前章节序号 +1）</span>
            </label>
            <label>生成数量（章）
              <input type="number" x-model.number="batchGenerateCount" min="1" max="100" placeholder="5">
              <span class="field-hint">将生成第 <span x-text="batchStartDisplay"></span> ~ <span x-text="batchEndDisplay"></span> 章</span>
            </label>
            <label>生成引导（可选）
              <textarea x-model="batchGenerateGuide" rows="3" placeholder="描述整体方向..."></textarea>
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showBatchGenerate = false">取消</button>
              <button class="btn-primary" @click="startBatchGenerate()">🚀 开始批量生成</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 批量生成进度（浮动，右下角） ═══ -->
      <template x-if="batchGenerating && batchTask">
        <div class="batch-progress-panel">
          <header>
            <span>📦 批量生成中</span>
            <div>
              <button class="btn-tiny" @click="openTaskManager()">任务</button>
              <button class="btn-tiny" @click="cancelBatchGenerate()">隐藏</button>
            </div>
          </header>
          <template x-if="batchProgressInfo">
            <div class="bpp-body">
              <div class="bpp-summary">
                <span>总体进度</span>
                <strong x-text="batchProgressInfo.completed + ' / ' + batchProgressInfo.total + ' 章'"></strong>
              </div>
              <div class="progress-bar"><div class="progress-fill" :style="'width: ' + (batchProgressInfo.total ? Math.round(batchProgressInfo.completed / batchProgressInfo.total * 100) : 0) + '%'"></div></div>
              <div class="bpp-current">当前：第 <span x-text="batchProgressInfo.currentOrder || '?'"></span> 章</div>
              <div class="pipeline-stages">
                <template x-for="st in batchPipelineStagesView" :key="'bp-' + st.id">
                  <div class="pipeline-stage" :class="'stage-' + st.status">
                    <span class="ps-icon" x-text="pipelineStageIcon(st.status)"></span>
                    <span class="ps-label" x-text="st.label"></span>
                    <span class="ps-time" x-show="st.duration_ms != null" x-text="(st.duration_ms/1000).toFixed(1) + 's'"></span>
                  </div>
                </template>
              </div>
            </div>
          </template>
        </div>
      </template>

      <!-- ═══ 任务管理弹窗 ═══ -->
      <template x-if="showTaskManager">
        <div class="modal-overlay" @click.self="showTaskManager = false">
          <div class="modal modal-wide modal-scrollable">
            <button class="modal-close-x" @click="showTaskManager = false">×</button>
            <h2>📋 任务管理</h2>
            <div class="task-manager-toolbar">
              <span>共 <strong x-text="allTasks.length"></strong> 个任务（运行中 <strong x-text="activeTaskCount"></strong>）</span>
              <div>
                <button class="btn-small" @click="refreshAllTasks()" :disabled="allTasksLoading">🔄 刷新</button>
                <button class="btn-small btn-rerun" x-show="hasFailedBootstrapTasks" @click="rerunAllBootstrapTasks(false)">🔄 重跑失败项</button>
                <button class="btn-small" x-show="hasBootstrapTasks" @click="rerunAllBootstrapTasks(true)">🔁 重跑全部设定</button>
                <button class="btn-small btn-danger" @click="terminateAllTasks()">⛔ 终止全部</button>
              </div>
            </div>
            <template x-if="allTasks.length === 0">
              <p class="empty-hint">暂无任务</p>
            </template>
            <div class="task-list">
              <template x-for="t in allTasks" :key="t.id">
                <div class="task-item">
                  <div class="task-info">
                    <div class="task-desc">
                      <span class="task-type-tag" x-text="taskTypeLabel(t.task_type)"></span>
                      <span x-text="t.description || t.id"></span>
                    </div>
                    <div class="task-meta">
                      <span class="task-type" x-text="t.task_type"></span>
                      <code x-text="t.id"></code>
                      <span x-show="t.duration_s">用时 <span x-text="t.duration_s + 's'"></span></span>
                    </div>
                    <template x-if="t.result && t.result.stages">
                      <div class="task-pipeline-detail">
                        <template x-for="sid in Object.keys(t.result.stages)" :key="'ts-' + t.id + '-' + sid">
                          <div class="tpd-row">
                            <span x-text="pipelineStageIcon(t.result.stages[sid].status)"></span>
                            <span class="tpd-label" x-text="t.result.stages[sid].label || getStageLabel(sid)"></span>
                            <span class="tpd-time" x-show="t.result.stages[sid].duration_ms != null" x-text="(t.result.stages[sid].duration_ms/1000).toFixed(1) + 's'"></span>
                            <span class="tpd-err" x-show="t.result.stages[sid].error" x-text="t.result.stages[sid].error"></span>
                          </div>
                        </template>
                      </div>
                    </template>
                  </div>
                  <div class="task-status">
                    <span class="status-pill" :class="'status-' + t.status" x-text="taskStatusLabel(t.status)"></span>
                    <button class="btn-small btn-rerun"
                            x-show="t.task_type === 'bootstrap' && ['failed','cancelled'].includes(t.status) && t.run_id"
                            @click="rerunOneBootstrapTask(t)">🔄 重新生成</button>
                    <button class="btn-small"
                            x-show="t.task_type === 'chapter_pipeline'"
                            @click="openPipelinePanelForTask(t)">📊 查看进度</button>
                    <button class="btn-small" x-show="['pending','running'].includes(t.status)"
                            @click="terminateOneTask(t.id)">⛔ 终止</button>
                  </div>
                </div>
              </template>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 字数调整弹窗 ═══ -->
      <template x-if="showWordAdjustModal">
        <div class="modal-overlay" @click.self="closeWordAdjustModal()">
          <div class="modal">
            <button class="modal-close-x" @click="closeWordAdjustModal()">×</button>
            <h2>📐 调整字数</h2>
            <p>当前章节《<strong x-text="currentChapter && currentChapter.title"></strong>》当前 <strong x-text="(currentChapter && currentChapter.word_count) || 0"></strong> 字</p>

            <template x-if="wordAdjustPlan">
              <div class="word-adjust-plan">
                <div class="wap-row">
                  <span>项目区间</span>
                  <strong x-text="(project?.word_count_min || 0) + ' ~ ' + (project?.word_count_max || 0) + ' 字'"></strong>
                </div>
                <div class="wap-row">
                  <span>判定</span>
                  <strong :class="'wap-' + wordAdjustPlan.action" x-text="{
                    compress: '字数超出上限，需缩写 ' + wordAdjustPlan.delta + ' 字',
                    expand: '字数不足下限，需扩写 ' + wordAdjustPlan.delta + ' 字',
                    none: '已在目标区间内，无需调整'
                  }[wordAdjustPlan.action]"></strong>
                </div>
              </div>
            </template>

            <label class="wap-toggle">
              <input type="checkbox" x-model="wordAdjustUseCustom" @change="recalcWordAdjustPlan()">
              使用自定义字数区间
            </label>

            <template x-if="wordAdjustUseCustom">
              <div class="form-row">
                <label>下限
                  <input type="number" x-model.number="wordAdjustCustomMin" @change="recalcWordAdjustPlan()">
                </label>
                <label>目标
                  <input type="number" x-model.number="wordAdjustCustomTarget" @change="recalcWordAdjustPlan()">
                </label>
                <label>上限
                  <input type="number" x-model.number="wordAdjustCustomMax" @change="recalcWordAdjustPlan()">
                </label>
              </div>
            </template>

            <div class="wap-presets">
              <span>按目标字数 ±：</span>
              <button class="btn-small" @click="applyWordAdjustPctPreset(5)">5%</button>
              <button class="btn-small" @click="applyWordAdjustPctPreset(10)">10%</button>
              <button class="btn-small" @click="applyWordAdjustPctPreset(20)">20%</button>
              <input type="number" class="wap-pct-input" x-model.number="wordAdjustPctInput" min="1" max="99">
              <button class="btn-small" @click="applyWordAdjustPctPreset(wordAdjustPctInput)">应用</button>
            </div>

            <div class="form-footer">
              <button class="btn-secondary" @click="closeWordAdjustModal()">取消</button>
              <button class="btn-primary"
                      :disabled="!wordAdjustPlan || wordAdjustPlan.action === 'none' || wordAdjustSubmitting"
                      @click="runWordAdjust()">
                <span x-show="!wordAdjustSubmitting">📐 开始调整</span>
                <span x-show="wordAdjustSubmitting">⏳ 提交中...</span>
              </button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 扩写大纲弹窗 ═══ -->
      <template x-if="showExtendOutlineModal">
        <div class="modal-overlay" @click.self="showExtendOutlineModal = false">
          <div class="modal">
            <button class="modal-close-x" @click="showExtendOutlineModal = false">×</button>
            <h2>📈 扩写 / 缩减大纲</h2>
            <p>已生成一句话大纲 <strong x-text="extendOutlineGenerated"></strong> 章，当前预设总章节 <strong x-text="extendOutlineOriginalTotal"></strong> 章</p>
            <div class="wap-row">
              <span>计划扩写（负数=缩减）</span>
              <input type="number" :value="extendOutlineExtendBy" @change="onExtendOutlineChange('extendBy', $event.target.value)">
            </div>
            <div class="wap-row">
              <span>新目标总章节</span>
              <input type="number" :value="extendOutlineNewTotal" @change="onExtendOutlineChange('newTotal', $event.target.value)">
            </div>
            <label class="wap-toggle">
              <input type="checkbox" x-model="extendOutlineArchitecture">
              同步扩写架构层（分卷 / 剧情线 / 四幕）
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showExtendOutlineModal = false">取消</button>
              <button class="btn-primary" :disabled="!canSubmitExtendOutline" @click="confirmExtendOutline()">确认</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 导出弹窗 ═══ -->
      <template x-if="showExportModal">
        <div class="modal-overlay" @click.self="showExportModal = false">
          <div class="modal">
            <button class="modal-close-x" @click="showExportModal = false">×</button>
            <h2>📤 导出项目</h2>
            <p>导出《<strong x-text="project.title"></strong>》的全部章节内容</p>
            <label>格式
              <select x-model="exportFormat">
                <option value="txt">TXT</option>
                <option value="markdown">Markdown</option>
              </select>
            </label>
            <label>
              <input type="checkbox" x-model="exportRechapter"> 重新分章
            </label>
            <label x-show="exportRechapter">每章字数
              <input type="number" x-model.number="exportWordsPerChapter" min="500" step="500">
            </label>
            <label>
              <input type="checkbox" x-model="exportSaveIndividual"> 每章独立保存（打包 zip）
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showExportModal = false">取消</button>
              <button class="btn-primary" @click="exportChapters()">📥 导出</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 文本替换弹窗 ═══ -->
      <template x-if="showTextReplaceModal">
        <div class="modal-overlay" @click.self="showTextReplaceModal = false">
          <div class="modal">
            <button class="modal-close-x" @click="showTextReplaceModal = false">×</button>
            <h2>🔄 全文替换</h2>
            <label>查找
              <input type="text" x-model="generatePrompt" placeholder="要查找的文本">
            </label>
            <label>替换为
              <input type="text" x-model="generateWordCount" placeholder="替换为的文本">
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showTextReplaceModal = false">取消</button>
              <button class="btn-primary" @click="showTextReplaceModal = false">执行替换</button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </template>

  <!-- ═══ 引导补全 Wizard（覆盖整个工作区） ═══ -->
  <template x-if="bootstrapWizard.visible">
    <div class="wizard-overlay">
      <div class="wizard-container">
        <header class="wizard-header">
          <h2>🤖 AI 正在为你的项目补全设定...</h2>
          <button class="btn-small" @click="closeBootstrapWizard()">×</button>
        </header>

        <div class="wizard-progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="'width: ' + bootstrapProgressPct() + '%'"></div>
          </div>
          <div class="progress-text">
            <span x-text="bootstrapProgressPct() + '% · ' + bootstrapDurationText()"></span>
            <span class="status-pill" :class="'status-' + bootstrapWizard.status"
                  x-text="{
                      running: '执行中',
                      committing: '写入中',
                      completed: '已完成，待提交',
                      committed: '已写入数据库',
                      failed: '部分失败'
                    }[bootstrapWizard.status] || bootstrapWizard.status"></span>
          </div>
        </div>

        <div class="wizard-stages">
          <template x-for="stage in bootstrapWizard.stages" :key="stage.id">
            <div class="wizard-stage" :class="'stage-' + stage.status">
              <div class="stage-head">
                <span class="stage-icon">
                  <template x-if="stage.status === 'running'">
                    <img class="stage-icon-gif"
                         src="/static/images/laoding.gif"
                         alt="加载中" />
                  </template>
                  <template x-if="stage.status !== 'running'">
                    <span x-text="bootstrapStageIcon(stage.status)"></span>
                  </template>
                </span>
                <div class="stage-info">
                  <div class="stage-name">
                    <span x-text="stage.name"></span>
                    <span class="stage-elapsed" x-show="stage.elapsed_s !== undefined"
                          x-text="formatStageElapsed(stage)"></span>
                  </div>
                  <div class="stage-desc" x-text="stage.description"></div>
                  <div class="stage-meta">
                    <span class="meta-tag" x-show="stage.needs_llm">需要 LLM</span>
                    <span class="meta-tag" x-show="!stage.needs_llm">用户已填</span>
                    <template x-for="dep in stage.depends_on" :key="dep">
                      <span class="meta-dep" x-text="'依赖: ' + dep"></span>
                    </template>
                    <span class="meta-tag meta-error" x-show="stage.error" x-text="'❌ ' + stage.error"></span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>

        <footer class="wizard-footer">
          <template x-if="bootstrapWizard.status === 'committed'">
            <div class="footer-actions">
              <button class="btn-primary" @click="closeBootstrapWizard()">进入写作台 →</button>
            </div>
          </template>
          <template x-if="bootstrapWizard.status === 'committing'">
            <div class="footer-actions">
              <span style="color: var(--text-muted);">⏳ 正在自动写入数据库，请稍候...</span>
            </div>
          </template>
          <template x-if="bootstrapWizard.status === 'failed' || bootstrapWizard.status === 'partial'">
            <div class="footer-actions" style="flex-wrap:wrap;gap:8px;align-items:center">
              <span class="error-msg" style="flex:1;min-width:240px">
                ⚠️ 部分 stage 失败 / 未完成。可点「重跑缺失项」一键续跑。
              </span>
              <button class="btn-secondary"
                      @click="rerunBootstrapAllStages(false)"
                      :disabled="bootstrapWizard.rerunAllBusy || bootstrapMissingCount() === 0">
                <span x-show="!bootstrapWizard.rerunAllBusy">🔄 重跑缺失项(<span x-text="bootstrapMissingCount()"></span>)</span>
                <span x-show="bootstrapWizard.rerunAllBusy">⏳ 重跑中...</span>
              </button>
              <button class="btn-primary"
                      @click="rerunBootstrapAllStages(true)"
                      :disabled="bootstrapWizard.rerunAllBusy">
                <span x-show="!bootstrapWizard.rerunAllBusy">🔁 全部重跑</span>
                <span x-show="bootstrapWizard.rerunAllBusy">⏳ 重跑中...</span>
              </button>
            </div>
          </template>
          <template x-if="bootstrapWizard.status === 'running'">
            <span class="running-hint">⏳ 正在调用 LLM 完成补全，请稍候...</span>
          </template>
        </footer>
      </div>
    </div>
  </template>
</div>
`);