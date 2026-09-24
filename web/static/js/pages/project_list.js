// 在 alpine:init 中注册组件（Alpine 通过 defer 在本脚本之后加载）
document.addEventListener('alpine:init', () => {
Alpine.data('projectList', () => ({
    projects: [],
    loading: false,
    searchQuery: '',
    filterType: 'all',
    // 题材标签（从 /api/genres 加载，未加载完时回退到内置默认项）
    genreList: [],

    showCreateModal: false,
    createForm: {
        title: '',
        project_type: 'novel',
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
    },
    createSubmitting: false,

    init() {
        this.loadProjects();
        this.loadGenres();
    },

    async loadGenres() {
        try {
            const res = await fetch('/api/genres');
            if (res.ok) this.genreList = await res.json();
        } catch (e) {
            console.error('加载题材失败:', e);
        }
    },

    async loadProjects() {
        this.loading = true;
        try {
            const res = await fetch('/api/projects');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.projects = await res.json();
        } catch (e) {
            console.error('加载项目列表失败:', e);
            Alpine.store('app').toast('加载项目失败: ' + e.message, 'error');
        } finally {
            this.loading = false;
        }
    },

    get filteredProjects() {
        let list = this.projects;
        if (this.filterType !== 'all') {
            list = list.filter(p => (p.project_type || 'novel') === this.filterType);
        }
        if (this.searchQuery) {
            const q = this.searchQuery.toLowerCase();
            list = list.filter(p =>
                (p.title || '').toLowerCase().includes(q) ||
                (p.description || '').toLowerCase().includes(q) ||
                (p.genre || '').toLowerCase().includes(q)
            );
        }
        return list;
    },

    async deleteProject(project) {
        if (!confirm(`确定删除项目「${project.title}」？此操作不可撤销！`)) return;
        try {
            const res = await fetch(`/api/projects/${project.id}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.projects = this.projects.filter(p => p.id !== project.id);
            Alpine.store('app').toast('项目已删除', 'success');
        } catch (e) {
            console.error('删除项目失败:', e);
            Alpine.store('app').toast('删除失败: ' + e.message, 'error');
        }
    },

    openProject(p) {
        const type = p.project_type || 'novel';
        const path = type === 'script'
            ? `/project/${p.id}/script`
            : `/project/${p.id}/novel`;
        Alpine.store('app').navigate(path);
    },

    openCreateProjectModal() {
        this.createForm = {
            title: '',
            project_type: 'novel',
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
        this.showCreateModal = true;
    },

    closeCreateModal() {
        this.showCreateModal = false;
    },

    async submitCreateProject() {
        const f = this.createForm;
        if (!f.title.trim()) {
            Alpine.store('app').toast('请输入项目标题', 'warning');
            return;
        }
        if (!f.description.trim()) {
            Alpine.store('app').toast('请输入项目描述', 'warning');
            return;
        }
        if (f.genres.length === 0) {
            Alpine.store('app').toast('请选择至少一个题材', 'warning');
            return;
        }

        this.createSubmitting = true;
        try {
            const payload = {
                title: f.title.trim(),
                project_type: f.project_type,
                chapter_word_count: f.chapter_word_count,
                genre: f.genres,
                description: f.description.trim(),
                total_chapters: f.total_chapters,
                auto_commit: true,
            };

            const optionalFields = ['theme', 'tone', 'style', 'pacing', 'premise', 'protagonist', 'antagonist', 'supporting', 'notes'];
            for (const field of optionalFields) {
                if (f[field] && f[field].trim()) {
                    payload[field] = f[field].trim();
                }
            }

            const res = await fetch('/api/projects', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const err = await res.json().catch(() => ({}));
                throw new Error(err.detail || `HTTP ${res.status}`);
            }

            const data = await res.json();
            if (data.status === 'missing_required') {
                Alpine.store('app').toast('请填写所有必填字段', 'warning');
                return;
            }

            Alpine.store('app').toast('项目创建成功', 'success');
            this.showCreateModal = false;

            if (data.project_id) {
                const path = f.project_type === 'script'
                    ? `/project/${data.project_id}/script`
                    : `/project/${data.project_id}/novel`;
                Alpine.store('app').navigate(path);
            } else {
                await this.loadProjects();
            }
        } catch (e) {
            console.error('创建项目失败:', e);
            Alpine.store('app').toast('创建失败: ' + e.message, 'error');
        } finally {
            this.createSubmitting = false;
        }
    },

    addGenre(genre) {
        if (!this.createForm.genres.includes(genre)) {
            this.createForm.genres.push(genre);
        }
    },

    removeGenre(genre) {
        this.createForm.genres = this.createForm.genres.filter(g => g !== genre);
    },

    async regenerateSettings(projectId) {
        if (!confirm('确定重新生成该项目的全部设定吗？')) return;
        try {
            const res = await fetch(`/api/projects/${projectId}/regenerate-settings`, {
                method: 'POST',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('设定重新生成已启动', 'success');
        } catch (e) {
            console.error('重新生成设定失败:', e);
            Alpine.store('app').toast('操作失败: ' + e.message, 'error');
        }
    },

    formatDate(dt) {
        if (!dt) return '';
        const d = new Date(dt);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
    },

    formatDateTime(dt) {
        if (!dt) return '';
        const d = new Date(dt);
        const pad = n => String(n).padStart(2, '0');
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    },

    get projectTypes() {
        return [
            { value: 'novel', label: '小说', icon: '📖' },
            { value: 'script', label: '剧本', icon: '🎬' },
        ];
    },

    get genreOptions() {
        const remote = (this.genreList || []).map(g => g.name).filter(Boolean);
        const defaults = ['玄幻', '都市', '科幻', '武侠', '仙侠', '历史', '悬疑', '现实主义', '奇幻', '其他'];
        return [...new Set([...remote, ...defaults])];
    },

    openQuestionnaire() {
        Alpine.store('app').navigate('/questionnaire');
    },

    get toneOptions() {
        return ['热血', '治愈', '黑暗', '轻松', '史诗', '悬疑紧张', '浪漫', '幽默', '冷峻'];
    },

    get styleOptions() {
        return ['优美', '平实', '诗意', '幽默', '冷峻'];
    },

    get pacingOptions() {
        return ['快节奏', '中等节奏', '慢热型', '起伏型'];
    },

    get chapterWordOptions() {
        return [2, 3, 4, 5];
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('project_list', `
<div class="page project-list-page">
  <div class="page-header">
    <h1>📚 我的项目</h1>
    <div class="header-actions">
      <button class="btn-secondary" @click="openQuestionnaire()">🎯 创意问卷 / 创意池</button>
      <button class="btn-primary" @click="openCreateProjectModal()">➕ 创建项目</button>
    </div>
  </div>

  <!-- 搜索 / 筛选 -->
  <div class="list-toolbar">
    <input type="text" class="search-input" x-model="searchQuery" placeholder="🔍 搜索项目标题 / 描述 / 题材...">
    <select x-model="filterType" class="filter-select">
      <option value="all">全部类型</option>
      <template x-for="t in projectTypes" :key="t.value">
        <option :value="t.value" x-text="t.icon + ' ' + t.label"></option>
      </template>
    </select>
  </div>

  <!-- 加载中 -->
  <template x-if="loading">
    <div class="page-loading"><div class="spinner"></div><p>加载中...</p></div>
  </template>

  <!-- 空状态 -->
  <template x-if="!loading && filteredProjects.length === 0">
    <div class="empty-state">
      <p>📭 暂无项目，点击右上角「创建项目」开始创作</p>
    </div>
  </template>

  <!-- 项目卡片网格 -->
  <div class="project-grid" x-show="!loading && filteredProjects.length > 0">
    <template x-for="p in filteredProjects" :key="p.id">
      <div class="project-card" @click="openProject(p)">
        <div class="project-card-header">
          <h4 x-text="p.title"></h4>
          <span class="project-type-tag" x-text="(p.project_type === 'script' ? '🎬 剧本' : '📖 小说')"></span>
        </div>
        <p class="project-card-desc" x-text="p.description || '暂无描述'"></p>
        <div class="project-meta">
          <span x-show="p.genre">🏷️ <span x-text="Array.isArray(p.genre) ? p.genre.join('、') : (p.genre || '')"></span></span>
          <span>📖 <span x-text="(p.chapter_count || 0) + ' / ' + (p.total_chapters || '?') + ' 章'"></span></span>
          <span>📅 <span x-text="formatDate(p.created_at)"></span></span>
        </div>
        <div class="project-card-actions">
          <button class="btn-small" @click.stop="regenerateSettings(p.id)" title="重新生成设定">🔄</button>
          <button class="btn-small btn-danger" @click.stop="deleteProject(p)" title="删除项目">🗑️</button>
        </div>
      </div>
    </template>
  </div>

  <!-- ═══ 创建项目弹窗 ═══ -->
  <template x-if="showCreateModal">
    <div class="modal-overlay" @click.self="closeCreateModal()">
      <div class="modal modal-wide">
        <button class="modal-close-x" @click="closeCreateModal()" title="关闭">×</button>
        <h2>➕ 创建新项目</h2>
        <p class="modal-hint">仅标题/描述/题材必填，其余留空可由 AI 智能补全</p>
        <p class="modal-hint">想一步步梳理设定？
          <button type="button" class="link-btn" @click="closeCreateModal(); openQuestionnaire()">🎯 使用创意问卷</button>
        </p>

        <form @submit.prevent="submitCreateProject()">
          <!-- 项目类型切换 -->
          <fieldset class="form-section required">
            <legend>必填</legend>
            <div class="form-row">
              <label>
                <span class="req">*</span> 项目类型
                <div class="type-switcher">
                  <template x-for="t in projectTypes" :key="t.value">
                    <button type="button" class="type-btn" :class="{ active: createForm.project_type === t.value }" @click="createForm.project_type = t.value">
                      <span x-text="t.icon"></span> <span x-text="t.label"></span>
                    </button>
                  </template>
                </div>
              </label>
            </div>

            <div class="form-row">
              <label>
                <span class="req">*</span> 标题
                <input type="text" x-model="createForm.title" placeholder="例如：无名" required>
              </label>
              <label>
                <span class="req">*</span> 章节字数（千字）
                <select x-model.number="createForm.chapter_word_count" required>
                  <template x-for="n in chapterWordOptions" :key="n">
                    <option :value="n" x-text="n + ' 千字（约 ' + (n*1000) + ' 字/章）'"></option>
                  </template>
                </select>
              </label>
              <label>
                预计总章数
                <input type="number" x-model.number="createForm.total_chapters" min="1" max="10000" placeholder="100">
              </label>
            </div>

            <div class="form-row">
              <label>
                <span class="req">*</span> 题材（可多选，至少 1 个）
                <div class="genre-chips" x-show="createForm.genres.length > 0">
                  <template x-for="g in createForm.genres" :key="g">
                    <span class="genre-chip">
                      <span x-text="g"></span>
                      <button type="button" class="chip-x" @click="removeGenre(g)">×</button>
                    </span>
                  </template>
                </div>
                <div class="genre-picker">
                  <select @change="$event.target.value && (addGenre($event.target.value), $event.target.value='')">
                    <option value="">+ 添加题材...</option>
                    <template x-for="g in genreOptions" :key="g">
                      <option :value="g" x-text="g"></option>
                    </template>
                  </select>
                </div>
              </label>
            </div>

            <label>
              <span class="req">*</span> 创意信息（一句话描述故事）
              <textarea x-model="createForm.description" rows="3" placeholder="例如：一个少年寻找失踪妹妹的玄幻冒险故事..." required></textarea>
            </label>
          </fieldset>

          <fieldset class="form-section optional">
            <legend>选填（未填将由 AI 补全）</legend>
            <div class="form-row">
              <label>
                <span class="ai-tag">🤖</span> 核心主题
                <input type="text" x-model="createForm.theme" placeholder="如：救赎、成长、复仇...">
              </label>
              <label>
                <span class="ai-tag">🤖</span> 基调
                <select x-model="createForm.tone">
                  <option value="">-- AI 补全 --</option>
                  <template x-for="t in toneOptions" :key="t">
                    <option :value="t" x-text="t"></option>
                  </template>
                </select>
              </label>
            </div>
            <div class="form-row">
              <label>
                <span class="ai-tag">🤖</span> 文风
                <select x-model="createForm.style">
                  <option value="">-- AI 补全 --</option>
                  <template x-for="s in styleOptions" :key="s">
                    <option :value="s" x-text="s"></option>
                  </template>
                </select>
              </label>
              <label>
                <span class="ai-tag">🤖</span> 节奏
                <select x-model="createForm.pacing">
                  <option value="">-- AI 补全 --</option>
                  <template x-for="p in pacingOptions" :key="p">
                    <option :value="p" x-text="p"></option>
                  </template>
                </select>
              </label>
            </div>
            <label>
              <span class="ai-tag">🤖</span> 世界观 / 背景
              <textarea x-model="createForm.premise" rows="2" placeholder="时代 / 世界 / 社会规则 / 势力等..."></textarea>
            </label>
            <div class="form-row">
              <label>
                <span class="ai-tag">🤖</span> 主角设定
                <input type="text" x-model="createForm.protagonist" placeholder="主角姓名 / 特征...">
              </label>
              <label>
                <span class="ai-tag">🤖</span> 反派设定
                <input type="text" x-model="createForm.antagonist" placeholder="反派姓名 / 特征...">
              </label>
            </div>
            <label>
              <span class="ai-tag">🤖</span> 配角 / 备注
              <textarea x-model="createForm.supporting" rows="2" placeholder="配角群像、其他备注..."></textarea>
            </label>
          </fieldset>

          <div class="form-footer">
            <button type="button" class="btn-secondary" @click="closeCreateModal()">取消</button>
            <button type="submit" class="btn-primary" :disabled="createSubmitting">
              <span x-show="!createSubmitting">🎯 创建项目</span>
              <span x-show="createSubmitting">⏳ 创建中...</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  </template>
</div>
`);