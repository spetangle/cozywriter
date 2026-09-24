document.addEventListener('alpine:init', () => {
Alpine.data('globalSettings', () => ({
    loading: false,
    saving: false,
    providers: [],
    editingProvider: null,
    providerForm: { id: '', name: '', api_key: '', base_url: '', model: '' },
    showAddProvider: false,
    providerSaving: false,
    testProviderLoading: {},
    availableModels: [],
    loadingModels: false,
    showModelPicker: false,
    defaultProvider: null,
    globalTokenUsage: null,
    globalTokenUsageLoading: false,
    selectedTab: 'providers',

    tabs: [
        { id: 'providers', label: '服务商', icon: '🔌' },
        { id: 'token-usage', label: '用量统计', icon: '📊' },
        { id: 'about', label: '关于', icon: 'ℹ️' },
    ],

    init() {
        this.loadProviders();
        this.loadGlobalTokenUsage();
    },

    async loadProviders() {
        this.loading = true;
        try {
            const res = await fetch('/api/providers');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.providers = await res.json();
            const def = this.providers.find(p => p.is_default);
            if (def) this.defaultProvider = def.id;
        } catch (e) {
            console.error('加载服务商失败:', e);
            Alpine.store('app').toast('加载服务商失败: ' + e.message, 'error');
        } finally {
            this.loading = false;
        }
    },

    async loadGlobalTokenUsage() {
        this.globalTokenUsageLoading = true;
        try {
            const res = await fetch('/api/token-usage/global');
            if (!res.ok) return;
            this.globalTokenUsage = await res.json();
        } catch (e) {
            console.warn('加载全局用量失败:', e);
        } finally {
            this.globalTokenUsageLoading = false;
        }
    },

    async setDefaultProvider(providerId) {
        try {
            const res = await fetch('/api/providers/set-default', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ provider_id: providerId }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.defaultProvider = providerId;
            await this.loadProviders();
            Alpine.store('app').toast('默认服务商已更新', 'success');
        } catch (e) {
            console.error('设置默认服务商失败:', e);
            Alpine.store('app').toast('操作失败: ' + e.message, 'error');
        }
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
        this.availableModels = [];
        this.showModelPicker = false;
    },

    cancelEditProvider() {
        this.editingProvider = null;
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
        this.availableModels = [];
        this.showModelPicker = false;
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
            Alpine.store('app').toast('保存成功', 'success');
        } catch (e) {
            console.error('保存失败:', e);
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        } finally {
            this.providerSaving = false;
        }
    },

    async testProviderConnection(providerId, useFormValues = false) {
        if (this.testProviderLoading[providerId]) return;
        this.testProviderLoading = { ...this.testProviderLoading, [providerId]: true };
        try {
            const body = { provider_id: providerId };
            if (useFormValues) {
                if (this.providerForm.api_key) body.api_key = this.providerForm.api_key;
                if (this.providerForm.base_url) body.base_url = this.providerForm.base_url;
                if (this.providerForm.model) body.model = this.providerForm.model;
            }
            const res = await fetch('/api/providers/test-connection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const result = await res.json();
            if (result.ok) {
                let msg = `✅ 连接成功！\n延迟: ${result.duration_ms}ms`;
                if (result.balance) {
                    const b = result.balance;
                    msg += `\n💰 余额: ${b.balance} ${b.currency}`;
                    if (b.warning) msg += `\n⚠️ ${b.message}`;
                }
                if (result.models) {
                    msg += `\n📦 可用模型: ${result.models.available.join(', ')}`;
                }
                alert(msg);
            } else {
                alert(`❌ 连接失败: ${result.message}`);
            }
        } catch (e) {
            alert('测试失败: ' + e.message);
        } finally {
            this.testProviderLoading = { ...this.testProviderLoading, [providerId]: false };
        }
    },

    startAddProvider() {
        this.showAddProvider = true;
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
        this.availableModels = [];
        this.showModelPicker = false;
    },

    cancelAddProvider() {
        this.showAddProvider = false;
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '' };
    },

    async createProvider() {
        if (this.providerSaving) return;
        if (!this.providerForm.id || !this.providerForm.name) {
            Alpine.store('app').toast('ID 和名称为必填', 'warning');
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
            Alpine.store('app').toast('创建成功', 'success');
        } catch (e) {
            console.error('创建失败:', e);
            Alpine.store('app').toast('创建失败: ' + e.message, 'error');
        } finally {
            this.providerSaving = false;
        }
    },

    async deleteProvider(providerId) {
        if (!confirm(`确认删除服务商 "${providerId}"？`)) return;
        try {
            const res = await fetch(`/api/providers/${providerId}`, { method: 'DELETE' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await this.loadProviders();
            Alpine.store('app').toast('删除成功', 'success');
        } catch (e) {
            console.error('删除失败:', e);
            Alpine.store('app').toast('删除失败: ' + e.message, 'error');
        }
    },

    async fetchAvailableModels(useFormValues = false) {
        let providerId;
        if (useFormValues) {
            providerId = this.providerForm.id;
        } else if (this.editingProvider) {
            providerId = this.editingProvider;
        }
        if (!providerId) {
            Alpine.store('app').toast('请先选择服务商', 'warning');
            return;
        }
        this.loadingModels = true;
        this.availableModels = [];
        try {
            const body = { provider_id: providerId };
            if (useFormValues || this.editingProvider) {
                if (this.providerForm.api_key) body.api_key = this.providerForm.api_key;
                if (this.providerForm.base_url) body.base_url = this.providerForm.base_url;
            }
            const res = await fetch('/api/providers/list-models', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const result = await res.json();
            if (result.ok) {
                this.availableModels = result.models || [];
                this.showModelPicker = true;
            } else {
                alert('获取模型列表失败: ' + result.message);
            }
        } catch (e) {
            alert('获取模型列表异常: ' + e.message);
        } finally {
            this.loadingModels = false;
        }
    },

    selectModel(modelId) {
        this.providerForm.model = modelId;
        this.showModelPicker = false;
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

    backToHome() {
        Alpine.store('app').navigate('/');
    },
}));
}); // end alpine:init

// ─── 注册页面 HTML 模板 ───
window.registerPageTemplate?.('global_settings', `
<div class="page global-settings-page">
  <div class="page-header">
    <h1>⚙️ 全局设置</h1>
    <button class="btn-secondary" @click="backToHome()">🏠 返回项目</button>
  </div>

  <!-- 标签页 -->
  <div class="settings-tabs">
    <template x-for="t in tabs" :key="t.id">
      <button class="settings-tab" :class="{ active: selectedTab === t.id }" @click="selectedTab = t.id">
        <span x-text="t.icon"></span> <span x-text="t.label"></span>
      </button>
    </template>
  </div>

  <!-- 服务商管理 -->
  <div x-show="selectedTab === 'providers'" class="settings-content">
    <div class="settings-section">
      <div class="section-header">
        <h2>🔌 服务商管理</h2>
        <button class="btn-primary" @click="startAddProvider()">➕ 添加服务商</button>
      </div>

      <template x-if="loading"><p>⏳ 加载中...</p></template>
      <template x-if="!loading && providers.length === 0"><p class="empty-state">暂无服务商，请点击「添加服务商」</p></template>

      <div class="provider-list" x-show="!loading && providers.length > 0">
        <template x-for="p in providers" :key="p.id">
          <div class="provider-card" :class="{ default: p.is_default }">
            <div class="provider-card-header">
              <h4>
                <span x-text="p.name"></span>
                <span class="badge-default" x-show="p.is_default">默认</span>
              </h4>
              <span class="provider-id" x-text="p.id"></span>
            </div>
            <div class="provider-meta">
              <span x-show="p.model">🤖 <span x-text="p.model"></span></span>
              <span x-show="p.base_url">🔗 <span x-text="p.base_url"></span></span>
            </div>

            <!-- 编辑表单 -->
            <template x-if="editingProvider === p.id">
              <div class="provider-edit-form">
                <label>名称
                  <input type="text" x-model="providerForm.name">
                </label>
                <label>API Key（留空不修改）
                  <input type="password" x-model="providerForm.api_key" placeholder="sk-...">
                </label>
                <label>Base URL
                  <input type="text" x-model="providerForm.base_url" placeholder="https://...">
                </label>
                <label>模型
                  <input type="text" x-model="providerForm.model" placeholder="模型 ID">
                </label>
                <div class="form-actions">
                  <button class="btn-secondary" @click="fetchAvailableModels(true)" :disabled="loadingModels">
                    <span x-show="!loadingModels">📦 获取模型列表</span>
                    <span x-show="loadingModels">⏳ 获取中...</span>
                  </button>
                  <button class="btn-secondary" @click="testProviderConnection(p.id, true)">🔌 测试连接</button>
                  <button class="btn-primary" @click="saveProviderEdit()" :disabled="providerSaving">💾 保存</button>
                  <button class="btn-secondary" @click="cancelEditProvider()">取消</button>
                </div>

                <!-- 模型选择器 -->
                <template x-if="showModelPicker && availableModels.length > 0">
                  <div class="model-picker">
                    <h5>可用模型</h5>
                    <template x-for="m in availableModels" :key="m">
                      <button type="button" class="model-option" @click="selectModel(m)" x-text="m"></button>
                    </template>
                  </div>
                </template>
              </div>
            </template>

            <!-- 操作按钮 -->
            <div class="provider-actions" x-show="editingProvider !== p.id">
              <button class="btn-small" @click="startEditProvider(p)">✏️ 编辑</button>
              <button class="btn-small" @click="testProviderConnection(p.id)" :disabled="testProviderLoading[p.id]">
                <span x-show="!testProviderLoading[p.id]">🔌 测试</span>
                <span x-show="testProviderLoading[p.id]">⏳ 测试中</span>
              </button>
              <button class="btn-small" x-show="!p.is_default" @click="setDefaultProvider(p.id)">⭐ 设为默认</button>
              <button class="btn-small btn-danger" @click="deleteProvider(p.id)">🗑️ 删除</button>
            </div>
          </div>
        </template>
      </div>

      <!-- 添加服务商表单 -->
      <template x-if="showAddProvider">
        <div class="modal-overlay" @click.self="cancelAddProvider()">
          <div class="modal">
            <button class="modal-close-x" @click="cancelAddProvider()">×</button>
            <h2>➕ 添加服务商</h2>
            <div class="form-grid">
              <label>ID（唯一标识，如 anthropic）
                <input type="text" x-model="providerForm.id" placeholder="anthropic">
              </label>
              <label>名称
                <input type="text" x-model="providerForm.name" placeholder="Anthropic">
              </label>
              <label>API Key
                <input type="password" x-model="providerForm.api_key" placeholder="sk-...">
              </label>
              <label>Base URL（可选）
                <input type="text" x-model="providerForm.base_url" placeholder="https://...">
              </label>
              <label>模型（可选）
                <input type="text" x-model="providerForm.model" placeholder="claude-3-5-sonnet">
              </label>
            </div>
            <div class="form-footer">
              <button class="btn-secondary" @click="cancelAddProvider()">取消</button>
              <button class="btn-primary" @click="createProvider()" :disabled="providerSaving">
                <span x-show="!providerSaving">💾 创建</span>
                <span x-show="providerSaving">⏳ 创建中...</span>
              </button>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>

  <!-- 用量统计 -->
  <div x-show="selectedTab === 'token-usage'" class="settings-content">
    <div class="settings-section">
      <h2>📊 全局 Token 用量</h2>
      <template x-if="globalTokenUsageLoading"><p>⏳ 加载中...</p></template>
      <template x-if="!globalTokenUsageLoading && globalTokenUsage">
        <div class="token-stats">
          <div class="stat-card">
            <span class="stat-label">输入 Token</span>
            <span class="stat-value" x-text="formatToken(globalTokenUsage.input_tokens || globalTokenUsage.prompt_tokens || 0)"></span>
          </div>
          <div class="stat-card">
            <span class="stat-label">输出 Token</span>
            <span class="stat-value" x-text="formatToken(globalTokenUsage.output_tokens || globalTokenUsage.completion_tokens || 0)"></span>
          </div>
          <div class="stat-card">
            <span class="stat-label">总 Token</span>
            <span class="stat-value" x-text="formatToken(globalTokenUsage.total_tokens || 0)"></span>
          </div>
          <div class="stat-card" x-show="globalTokenUsage.estimated_cost">
            <span class="stat-label">预估总花费</span>
            <span class="stat-value" x-text="(globalTokenUsage.estimated_cost || 0).toFixed(4)"></span>
          </div>
        </div>
      </template>
      <template x-if="!globalTokenUsageLoading && !globalTokenUsage">
        <p class="empty-state">暂无用量数据</p>
      </template>
    </div>
  </div>

  <!-- 关于 -->
  <div x-show="selectedTab === 'about'" class="settings-content">
    <div class="settings-section">
      <h2>ℹ️ 关于 CozyWriter</h2>
      <p>CozyWriter - 智能创作助手</p>
      <p>LLM 驱动的小说 / 剧本创作工具，集成 RAG 知识管理、智能评审与一致性检查。</p>
    </div>
  </div>
</div>
`);