document.addEventListener('alpine:init', () => {
Alpine.data('projectSettings', () => ({
    project: null,
    projectId: null,
    loading: false,
    saving: false,
    tokenUsage: null,
    tokenUsageLoading: false,
    recentUsage: [],
    recentUsageLoading: false,
    providers: [],
    characters: [],
    themes: [],
    bootstrapStatus: null,
    bootstrapLoading: false,
    isRegeneratingSettings: false,
    selectedProvider: null,
    settingsChapterWordCount: 0,

    get projectId() {
        return Alpine.store('app').currentRoute.params.id;
    },

    init() {
        const id = Alpine.store('app').currentRoute.params.id;
        this.loadProject(id);
        this.loadTokenUsage(id);
        this.loadRecentUsage(id);
        this.loadBootstrapStatus(id);
        this.loadCharacters(id);
        this.loadThemes(id);
    },

    async loadProject(id) {
        this.loading = true;
        try {
            const res = await fetch(`/api/projects/${id}`);
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.project = await res.json();
            this.settingsChapterWordCount = Math.round((this.project.target_word_count || 0) / 1000);
        } catch (e) {
            console.error('加载项目失败:', e);
            Alpine.store('app').toast('加载项目失败: ' + e.message, 'error');
        } finally {
            this.loading = false;
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

    async loadRecentUsage(projectId) {
        this.recentUsageLoading = true;
        try {
            const res = await fetch(`/api/token-usage/project/${projectId}/recent?limit=20`);
            if (!res.ok) return;
            this.recentUsage = await res.json();
        } catch (e) {
            console.warn('加载最近用量失败:', e);
        } finally {
            this.recentUsageLoading = false;
        }
    },

    async loadBootstrapStatus(projectId) {
        this.bootstrapLoading = true;
        try {
            const res = await fetch(`/api/projects/${projectId}/bootstrap-status`);
            if (!res.ok) return;
            this.bootstrapStatus = await res.json();
        } catch (e) {
            console.warn('加载 bootstrap 状态失败:', e);
        } finally {
            this.bootstrapLoading = false;
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

    async updateProject(field, value) {
        this.saving = true;
        try {
            const payload = { [field]: value };
            const res = await fetch(`/api/projects/${this.projectId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const updated = await res.json();
            this.project = updated;
            this.settingsChapterWordCount = Math.round((updated.target_word_count || 0) / 1000);
            Alpine.store('app').toast('保存成功', 'success');
        } catch (e) {
            console.error('保存失败:', e);
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        } finally {
            this.saving = false;
        }
    },

    async deleteProject() {
        if (!confirm(`⚠️ 即将永久删除项目《${this.project.title}》\n此操作不可撤销！确定删除？`)) return;
        try {
            const res = await fetch(`/api/projects/${this.projectId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('项目已删除', 'success');
            Alpine.store('app').clearLastRoute();
            Alpine.store('app').navigate('/');
        } catch (e) {
            console.error('删除失败:', e);
            Alpine.store('app').toast('删除失败: ' + e.message, 'error');
        }
    },

    async regenerateSettings() {
        if (!confirm('确定重新生成全部设定吗？这将覆盖已有的设定内容。')) return;
        this.isRegeneratingSettings = true;
        try {
            const res = await fetch(`/api/projects/${this.projectId}/regenerate-settings`, {
                method: 'POST',
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            Alpine.store('app').toast('设定重新生成已启动', 'success');
            if (data.run_id) {
                await this.loadBootstrapStatus(this.projectId);
            }
        } catch (e) {
            console.error('重新生成失败:', e);
            Alpine.store('app').toast('操作失败: ' + e.message, 'error');
        } finally {
            this.isRegeneratingSettings = false;
        }
    },

    get formatToken() {
        return (n) => {
            if (!n) return '0';
            if (n >= 1000000) return (n / 1000000).toFixed(2) + 'M';
            if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
            return String(n);
        };
    },

    formatDuration(ms) {
        if (!ms) return '0ms';
        if (ms >= 60000) return (ms / 60000).toFixed(1) + 'min';
        if (ms >= 1000) return (ms / 1000).toFixed(1) + 's';
        return ms + 'ms';
    },

    formatDate(dt) {
        if (!dt) return '';
        return new Date(dt).toLocaleString('zh-CN');
    },

    backToHome() {
        Alpine.store('app').navigate('/');
    },

    goToEditor() {
        const type = this.project?.project_type || 'novel';
        const path = type === 'script'
            ? `/project/${this.projectId}/script`
            : `/project/${this.projectId}/novel`;
        Alpine.store('app').navigate(path);
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('project_settings', `
<div class="page project-settings-page">
  <template x-if="loading">
    <div class="page-loading"><div class="spinner"></div><p>加载中...</p></div>
  </template>

  <template x-if="!loading && project">
    <div class="settings-container">
      <div class="page-header">
        <h1>⚙️ 项目设置</h1>
        <div class="header-actions">
          <button class="btn-secondary" @click="goToEditor()">↩ 返回编辑器</button>
          <button class="btn-secondary" @click="backToHome()">🏠 项目列表</button>
        </div>
      </div>

      <div class="settings-section">
        <h2>📋 项目信息</h2>
        <div class="form-grid">
          <label>标题
            <input type="text" x-model="project.title" @change="updateProject('title', project.title)">
          </label>
          <label>题材
            <input type="text" :value="Array.isArray(project.genre) ? project.genre.join('、') : (project.genre || '')" disabled>
          </label>
          <label>总章数
            <input type="number" x-model.number="project.total_chapters" @change="updateProject('total_chapters', project.total_chapters)">
          </label>
          <label>章节字数（千字）
            <input type="number" x-model.number="settingsChapterWordCount" @change="updateProject('chapter_word_count', settingsChapterWordCount)">
          </label>
          <label class="full-width">描述
            <textarea x-model="project.description" rows="3" @change="updateProject('description', project.description)"></textarea>
          </label>
        </div>
      </div>

      <!-- Bootstrap 状态 -->
      <div class="settings-section">
        <h2>🚀 设定生成状态</h2>
        <template x-if="bootstrapLoading">
          <p>⏳ 加载中...</p>
        </template>
        <template x-if="!bootstrapLoading && bootstrapStatus">
          <div class="bootstrap-status">
            <p><strong>状态：</strong> <span x-text="bootstrapStatus.status || '-'"></span></p>
            <p x-show="bootstrapStatus.run_id"><strong>Run ID：</strong> <span x-text="bootstrapStatus.run_id"></span></p>
            <p x-show="bootstrapStatus.started_at"><strong>开始时间：</strong> <span x-text="formatDate(bootstrapStatus.started_at)"></span></p>
            <button class="btn-secondary" :disabled="isRegeneratingSettings" @click="regenerateSettings()">
              <span x-show="!isRegeneratingSettings">🔄 重新生成全部设定</span>
              <span x-show="isRegeneratingSettings">⏳ 生成中...</span>
            </button>
          </div>
        </template>
        <template x-if="!bootstrapLoading && !bootstrapStatus">
          <div class="empty-state"><p>暂无设定生成记录</p></div>
        </template>
      </div>

      <!-- Token 用量 -->
      <div class="settings-section">
        <h2>📊 Token 用量</h2>
        <template x-if="tokenUsageLoading">
          <p>⏳ 加载中...</p>
        </template>
        <template x-if="!tokenUsageLoading && tokenUsage">
          <div class="token-stats">
            <div class="stat-card">
              <span class="stat-label">输入 Token</span>
              <span class="stat-value" x-text="formatToken(tokenUsage.input_tokens || tokenUsage.prompt_tokens || 0)"></span>
            </div>
            <div class="stat-card">
              <span class="stat-label">输出 Token</span>
              <span class="stat-value" x-text="formatToken(tokenUsage.output_tokens || tokenUsage.completion_tokens || 0)"></span>
            </div>
            <div class="stat-card">
              <span class="stat-label">总 Token</span>
              <span class="stat-value" x-text="formatToken(tokenUsage.total_tokens || 0)"></span>
            </div>
            <div class="stat-card" x-show="tokenUsage.estimated_cost">
              <span class="stat-label">预估花费</span>
              <span class="stat-value" x-text="(tokenUsage.estimated_cost || 0).toFixed(4)"></span>
            </div>
          </div>
        </template>
      </div>

      <!-- 最近用量 -->
      <div class="settings-section">
        <h2>🕒 最近用量</h2>
        <template x-if="recentUsageLoading"><p>⏳ 加载中...</p></template>
        <template x-if="!recentUsageLoading && recentUsage.length === 0"><p class="empty-state">暂无记录</p></template>
        <table class="data-table" x-show="!recentUsageLoading && recentUsage.length > 0">
          <thead>
            <tr><th>时间</th><th>操作</th><th>输入</th><th>输出</th><th>耗时</th></tr>
          </thead>
          <tbody>
            <template x-for="(u, i) in recentUsage" :key="i">
              <tr>
                <td x-text="formatDate(u.created_at || u.timestamp)"></td>
                <td x-text="u.operation || u.action || '-'"></td>
                <td x-text="formatToken(u.input_tokens || u.prompt_tokens || 0)"></td>
                <td x-text="formatToken(u.output_tokens || u.completion_tokens || 0)"></td>
                <td x-text="formatDuration(u.duration_ms)"></td>
              </tr>
            </template>
          </tbody>
        </table>
      </div>

      <!-- 角色 / 主题概览 -->
      <div class="settings-section">
        <h2>👥 角色 / 🎯 主题概览</h2>
        <p>角色数：<strong x-text="characters.length"></strong> · 主题数：<strong x-text="themes.length"></strong></p>
      </div>

      <!-- 危险操作 -->
      <div class="settings-section danger-zone">
        <h2>⚠️ 危险操作</h2>
        <button class="btn-danger" @click="deleteProject()">🗑️ 删除此项目</button>
      </div>
    </div>
  </template>
</div>
`);