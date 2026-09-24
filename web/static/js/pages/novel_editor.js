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
    pipelinePollHandle: null,
    showRegenerateConfirm: false,

    showWordAdjustModal: false,
    wordAdjustPlan: null,
    wordAdjustTaskId: null,
    wordAdjustSubmitting: false,

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
    expandedTaskIds: [],

    get projectId() {
        const store = Alpine.store('app');
        return store.currentRoute.params.id;
    },

    init() {
        const id = Alpine.store('app').currentRoute.params.id;
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
        return !this.pipelineTask || !['pending', 'running'].includes(this.pipelineTask.status);
    },

    async pipelineSetupSetupModal() {
        this.showPipelineSetup = true;
    },

    async startPipelineGuide(guide) {
        if (!this.currentChapter) {
            Alpine.store('app').toast('请先选择一个章节', 'warning');
            return;
        }
        try {
            const res = await fetch(`/api/chapters/generate-pipeline`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: this.projectId,
                    chapter_id: this.currentChapter.id,
                    guide: guide || '',
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.pipelineTask = data;
            this.showPipelineProgress = true;
            this.showPipelineSetup = false;
            this._startPipelinePolling(data.task_id);
        } catch (e) {
            console.error('启动 pipeline 失败:', e);
            Alpine.store('app').toast('启动失败: ' + e.message, 'error');
        }
    },

    _startPipelinePolling(taskId) {
        if (this.pipelinePollHandle) clearInterval(this.pipelinePollHandle);
        this.pipelinePollHandle = setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks/${taskId}`);
                if (!res.ok) return;
                const task = await res.json();
                this.pipelineTask = task;
                if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                    clearInterval(this.pipelinePollHandle);
                    this.pipelinePollHandle = null;
                    if (task.status === 'completed') {
                        await this.loadChapters(this.project.id);
                        if (task.result?.chapter_id) {
                            const ch = this.chapters.find(c => c.id === task.result.chapter_id);
                            if (ch) await this.selectChapter(ch);
                        }
                        Alpine.store('app').toast('生成完成', 'success');
                    } else if (task.status === 'failed') {
                        Alpine.store('app').toast('生成失败: ' + (task.error || 'unknown'), 'error');
                    }
                }
            } catch (e) {
                console.warn('Pipeline 轮询失败:', e);
            }
        }, 2000);
    },

    async openBatchGenerateModal() {
        this.showBatchGenerate = true;
    },

    async startBatchGenerate(startChapter, count, guide) {
        try {
            const res = await fetch('/api/chapters/batch-generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    project_id: this.project.id,
                    start_chapter: startChapter,
                    count,
                    guide: guide || '',
                }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.batchTask = data;
            this.batchGenerating = true;
            this.showBatchGenerate = false;
            this._startBatchPolling(data.task_id);
        } catch (e) {
            console.error('批量生成失败:', e);
            Alpine.store('app').toast('批量生成失败: ' + e.message, 'error');
        }
    },

    _startBatchPolling(taskId) {
        const handle = setInterval(async () => {
            try {
                const res = await fetch(`/api/tasks/${taskId}`);
                if (!res.ok) return;
                const task = await res.json();
                this.batchTask = task;
                if (['completed', 'failed', 'cancelled'].includes(task.status)) {
                    clearInterval(handle);
                    this.batchGenerating = false;
                    if (task.status === 'completed') {
                        await this.loadChapters(this.project.id);
                        Alpine.store('app').toast('批量生成完成', 'success');
                    }
                }
            } catch (e) {
                console.warn('批量任务轮询失败:', e);
            }
        }, 2000);
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
        this.showTaskManager = true;
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
              <button @click="setPanel('outline')" :class="{ active: activePanel === 'outline' }">📋 细纲</button>
              <button @click="setPanel('character')" :class="{ active: activePanel === 'character' }">👥 角色</button>
              <button @click="setPanel('theme')" :class="{ active: activePanel === 'theme' }">🎯 主题/伏笔</button>
              <button @click="setPanel('plot')" :class="{ active: activePanel === 'plot' }">📊 剧情追踪</button>
              <button @click="pipelineSetupSetupModal()" :disabled="!canRunPipeline">🚀 单章生成</button>
              <button @click="openBatchGenerateModal()">📦 批量生成</button>
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
              </div>
            </template>
          </div>

          <!-- 细纲面板 -->
          <div x-show="activePanel === 'outline'" class="panel-section">
            <h3>📋 章节细纲</h3>
            <template x-if="!currentChapter"><p class="empty-hint">请先选择章节</p></template>
            <template x-if="currentChapter">
              <div class="outline-panel">
                <p>当前章节：<strong x-text="currentChapter.title"></strong></p>
                <template x-if="chapterOutlinesMap[currentChapter.id]">
                  <div class="outline-text" x-text="chapterOutlinesMap[currentChapter.id].key_content || '暂无核心内容'"></div>
                </template>
                <template x-if="!chapterOutlinesMap[currentChapter.id]"><p class="empty-hint">本章暂无细纲</p></template>
              </div>
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

      <!-- ═══ Pipeline 进度弹窗 ═══ -->
      <template x-if="showPipelineProgress && pipelineTask">
        <div class="modal-overlay">
          <div class="modal">
            <h2>⏳ 生成进度</h2>
            <p>任务 ID：<span x-text="pipelineTask.task_id"></span></p>
            <p>状态：<strong x-text="pipelineTask.status"></strong></p>
            <template x-if="pipelineTask.status === 'completed'">
              <div class="success-state"><p>✅ 生成完成</p></div>
            </template>
            <template x-if="pipelineTask.status === 'failed'">
              <div class="error-state"><p>❌ 失败：<span x-text="pipelineTask.error || '未知错误'"></span></p></div>
            </template>
            <div class="form-footer">
              <button class="btn-secondary" @click="showPipelineProgress = false">关闭</button>
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
            <label>起始章节序号
              <input type="number" x-model.number="generateWordCount" min="0" placeholder="0">
            </label>
            <label>生成数量
              <input type="number" x-model.number="generateWordCount" min="1" placeholder="3">
            </label>
            <label>生成引导（可选）
              <textarea x-model="generatePrompt" rows="3" placeholder="描述整体方向..."></textarea>
            </label>
            <div class="form-footer">
              <button class="btn-secondary" @click="showBatchGenerate = false">取消</button>
              <button class="btn-primary" @click="startBatchGenerate(0, 3, generatePrompt)">🚀 开始批量生成</button>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 任务管理弹窗 ═══ -->
      <template x-if="showTaskManager">
        <div class="modal-overlay" @click.self="showTaskManager = false">
          <div class="modal modal-wide">
            <button class="modal-close-x" @click="showTaskManager = false">×</button>
            <h2>📋 任务管理</h2>
            <template x-if="pipelineTask">
              <div class="task-item">
                <strong x-text="pipelineTask.task_id"></strong>
                <span class="tag" x-text="pipelineTask.status"></span>
              </div>
            </template>
            <template x-if="batchTask">
              <div class="task-item">
                <strong x-text="batchTask.task_id"></strong>
                <span class="tag" x-text="batchTask.status"></span>
              </div>
            </template>
            <template x-if="!pipelineTask && !batchTask">
              <p class="empty-hint">暂无运行中的任务</p>
            </template>
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