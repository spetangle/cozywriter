document.addEventListener('alpine:init', () => {
Alpine.data('globalSettings', () => ({
    loading: false,
    saving: false,
    providers: [],
    editingProvider: null,
    providerForm: { id: '', name: '', api_key: '', base_url: '', model: '', use_json_output: 'auto' },
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

    // ─── RAG embedding（本地 CPU / 在线 API 切换）───
    ragSettings: { mode: 'local', base_url: '', api_key: '', model: '' },
    ragHasApiKey: false,
    ragApiKeyMasked: '',
    ragLoading: false,
    ragSaving: false,
    ragTesting: false,
    ragTestResult: null,

    // ─── 联网搜索（「搜索相似小说」用）───
    searchSettings: { provider: '', api_key: '' },
    searchHasApiKey: false,
    searchApiKeyMasked: '',
    searchLoading: false,
    searchSaving: false,
    searchTesting: false,
    searchTestResult: null,

    tabs: [
        { id: 'providers', label: '服务商', icon: '🔌' },
        { id: 'rag', label: 'RAG 向量', icon: '🧠' },
        { id: 'search', label: '联网搜索', icon: '🔍' },
        { id: 'token-usage', label: '用量统计', icon: '📊' },
        { id: 'about', label: '关于', icon: 'ℹ️' },
    ],

    init() {
        this.loadProviders();
        this.loadGlobalTokenUsage();
        this.loadRagSettings();
        this.loadSearchSettings();
    },

    async loadRagSettings() {
        this.ragLoading = true;
        try {
            const res = await fetch('/api/config/rag');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.ragSettings.mode = data.mode || 'local';
            this.ragSettings.base_url = data.base_url || '';
            this.ragSettings.model = data.model || '';
            this.ragSettings.api_key = '';
            this.ragHasApiKey = !!data.has_api_key;
            this.ragApiKeyMasked = data.api_key_masked || '';
        } catch (e) {
            console.error('加载 RAG 设置失败:', e);
        } finally {
            this.ragLoading = false;
        }
    },

    async saveRagSettings() {
        this.ragSaving = true;
        try {
            const payload = {
                mode: this.ragSettings.mode,
                base_url: this.ragSettings.base_url,
                model: this.ragSettings.model,
            };
            // 只在用户输入了新 key 时才更新，避免把掩码/空值写回
            if (this.ragSettings.api_key) payload.api_key = this.ragSettings.api_key;
            const res = await fetch('/api/config/rag', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('RAG 设置已保存', 'success');
            await this.loadRagSettings();
        } catch (e) {
            Alpine.store('app').toast('保存 RAG 设置失败: ' + e.message, 'error');
        } finally {
            this.ragSaving = false;
        }
    },

    async clearRagApiKey() {
        if (!confirm('确定清空在线 embedding 的 API Key？')) return;
        this.ragSaving = true;
        try {
            const res = await fetch('/api/config/rag', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: '' }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('已清空 API Key', 'success');
            await this.loadRagSettings();
        } catch (e) {
            Alpine.store('app').toast('清空失败: ' + e.message, 'error');
        } finally {
            this.ragSaving = false;
        }
    },

    async testRag() {
        this.ragTesting = true;
        this.ragTestResult = null;
        try {
            const payload = {
                mode: this.ragSettings.mode,
                base_url: this.ragSettings.base_url,
                model: this.ragSettings.model,
            };
            if (this.ragSettings.api_key) payload.api_key = this.ragSettings.api_key;
            const res = await fetch('/api/config/rag/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            this.ragTestResult = await res.json();
        } catch (e) {
            this.ragTestResult = { ok: false, message: '请求失败: ' + e.message };
        } finally {
            this.ragTesting = false;
        }
    },

    async resetRag() {
        if (!confirm('切换 embedding 模式/模型后向量维度会变化，需要清空旧向量库。确定重置吗？')) return;
        try {
            const res = await fetch('/api/config/rag/reset', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('RAG 向量库已重置，将按新模型重建', 'success');
        } catch (e) {
            Alpine.store('app').toast('重置失败: ' + e.message, 'error');
        }
    },

    // ─── 联网搜索设置 ───
    async loadSearchSettings() {
        this.searchLoading = true;
        try {
            const res = await fetch('/api/config/search');
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.searchSettings.provider = data.provider || '';
            this.searchSettings.api_key = '';
            this.searchHasApiKey = !!data.has_api_key;
            this.searchApiKeyMasked = data.api_key_masked || '';
        } catch (e) {
            console.error('加载联网搜索设置失败:', e);
        } finally {
            this.searchLoading = false;
        }
    },

    async saveSearchSettings() {
        this.searchSaving = true;
        try {
            const payload = { provider: this.searchSettings.provider };
            if (this.searchSettings.api_key) payload.api_key = this.searchSettings.api_key;
            const res = await fetch('/api/config/search', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            Alpine.store('app').toast('联网搜索设置已保存', 'success');
            await this.loadSearchSettings();
        } catch (e) {
            Alpine.store('app').toast('保存失败: ' + e.message, 'error');
        } finally {
            this.searchSaving = false;
        }
    },

    async clearSearchApiKey() {
        try {
            const res = await fetch('/api/config/search', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_key: '' }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            await this.loadSearchSettings();
            Alpine.store('app').toast('已清空搜索 API Key', 'success');
        } catch (e) {
            Alpine.store('app').toast('清空失败: ' + e.message, 'error');
        }
    },

    async testSearch() {
        this.searchTesting = true;
        this.searchTestResult = null;
        try {
            const res = await fetch('/api/config/search/test', { method: 'POST' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.searchTestResult = await res.json();
        } catch (e) {
            this.searchTestResult = { ok: false, message: e.message };
        } finally {
            this.searchTesting = false;
        }
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
            use_json_output: (provider.use_json_output === true) ? 'true'
                : (provider.use_json_output === false) ? 'false' : 'auto',
        };
        this.availableModels = [];
        this.showModelPicker = false;
    },

    cancelEditProvider() {
        this.editingProvider = null;
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '', use_json_output: 'auto' };
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
            // 'auto' → null（按 provider 默认），'true'/'false' → 显式开关
            body.use_json_output = this.providerForm.use_json_output === 'true' ? true
                : this.providerForm.use_json_output === 'false' ? false : null;

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
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '', use_json_output: 'auto' };
        this.availableModels = [];
        this.showModelPicker = false;
    },

    cancelAddProvider() {
        this.showAddProvider = false;
        this.providerForm = { id: '', name: '', api_key: '', base_url: '', model: '', use_json_output: 'auto' };
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
                <label>JSON 输出模式
                  <select x-model="providerForm.use_json_output">
                    <option value="auto">跟随服务商默认</option>
                    <option value="true">强制开启（response_format=json_object）</option>
                    <option value="false">强制关闭（部分模型兼容性差时选择）</option>
                  </select>
                </label>
                <p class="hint" x-show="providerForm.use_json_output === 'false'">
                  关闭后任务仍要求 JSON，但不再传 response_format；部分 DeepSeek 模型返回空响应时可尝试此项。
                </p>
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
                    <template x-for="m in availableModels" :key="m.id">
                      <button type="button" class="model-option" @click="selectModel(m.id)" x-text="m.name"></button>
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

  <!-- RAG 向量模型（本地 / 在线切换） -->
  <div x-show="selectedTab === 'rag'" class="settings-content">
    <div class="settings-section">
      <h2>🧠 RAG 向量模型</h2>
      <p class="empty-hint">
        RAG 用于事件去重 / 相似章节检索 / 评审上下文。可选用本地 CPU 模型，或在线 embedding API。
        切换模式或模型后向量维度会变化，需要点「重置向量库」。
      </p>

      <template x-if="ragLoading"><p>⏳ 加载中...</p></template>
      <template x-if="!ragLoading">
        <div class="rag-settings-form">
          <label>模式
            <select x-model="ragSettings.mode">
              <option value="local">本地 CPU 模型（sentence-transformers）</option>
              <option value="online">在线 Embedding API（OpenAI 兼容）</option>
            </select>
          </label>

          <template x-if="ragSettings.mode === 'local'">
            <div class="rag-local-hint">
              <p>本地模型：<code>moka-ai/m3e-base</code>（约 400MB，CPU 运行）</p>
              <p>依赖安装：运行 <code>tools/install_rag_cpu</code> 脚本；模型可在「模型管理」下载。</p>
            </div>
          </template>

          <template x-if="ragSettings.mode === 'online'">
            <div class="rag-online-fields">
              <label>Base URL
                <input type="text" x-model="ragSettings.base_url" placeholder="如 https://api.openai.com/v1">
              </label>
              <label>模型名
                <input type="text" x-model="ragSettings.model" placeholder="如 text-embedding-3-small">
              </label>
              <label>API Key
                <input type="password" x-model="ragSettings.api_key"
                       :placeholder="ragHasApiKey ? ('已配置：' + ragApiKeyMasked + '（留空不修改）') : '尚未配置'">
              </label>
              <button class="btn-secondary" @click="clearRagApiKey()" :disabled="!ragHasApiKey">清空 Key</button>
            </div>
          </template>

          <div class="rag-actions">
            <button class="btn-primary" @click="saveRagSettings()" :disabled="ragSaving">💾 保存</button>
            <button class="btn-secondary" @click="testRag()" :disabled="ragTesting">🔍 测试连接</button>
            <button class="btn-secondary" @click="resetRag()">♻️ 重置向量库</button>
          </div>

          <div class="rag-test-result" x-show="ragTestResult"
               :style="{ color: ragTestResult && ragTestResult.ok ? '#2e7d32' : '#c62828' }">
            <span x-text="ragTestResult ? (ragTestResult.ok ? '✅ ' : '❌ ') + ragTestResult.message : ''"></span>
          </div>
        </div>
      </template>
    </div>
  </div>

  <!-- 联网搜索（搜索相似小说用） -->
  <div x-show="selectedTab === 'search'" class="settings-content">
    <div class="settings-section">
      <h2>🔍 联网搜索</h2>
      <p class="empty-hint">
        用于问卷汇总页的「搜索相似小说」：把小说信息交给 LLM，并联网检索市面上是否有相近作品。
        未配置时该功能仍可用，但结果仅基于模型已有知识（不联网）。
      </p>

      <template x-if="searchLoading"><p>⏳ 加载中...</p></template>
      <template x-if="!searchLoading">
        <div class="rag-settings-form">
          <label>搜索服务
            <select x-model="searchSettings.provider">
              <option value="">不联网（仅用模型知识）</option>
              <option value="tavily">Tavily</option>
              <option value="serper">Serper（Google）</option>
            </select>
          </label>

          <template x-if="searchSettings.provider">
            <label>API Key
              <input type="password" x-model="searchSettings.api_key"
                     :placeholder="searchHasApiKey ? ('已配置：' + searchApiKeyMasked + '（留空不修改）') : '尚未配置'">
            </label>
          </template>

          <div class="rag-actions">
            <button class="btn-primary" @click="saveSearchSettings()" :disabled="searchSaving">💾 保存</button>
            <button class="btn-secondary" @click="testSearch()" :disabled="searchTesting || !searchSettings.provider">🔍 测试连接</button>
            <button class="btn-secondary" @click="clearSearchApiKey()" :disabled="!searchHasApiKey">清空 Key</button>
          </div>

          <div class="rag-test-result" x-show="searchTestResult"
               :style="{ color: searchTestResult && searchTestResult.ok ? '#2e7d32' : '#c62828' }">
            <span x-text="searchTestResult ? (searchTestResult.ok ? '✅ ' : '❌ ') + searchTestResult.message : ''"></span>
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