// 道具面板组件（剧本编辑器）
//
// 数据归属：properties 数组由父页面（scriptEditor）持有，本组件通过 Alpine
// 作用域链读取，并只做「原地」修改。
document.addEventListener('alpine:init', () => {
    Alpine.data('propertyPanel', () => ({
        loading: false,
        submitting: false,
        showCreateModal: false,
        editingId: null,
        expandedId: null,

        emptyForm: {
            name: '',
            type: '道具',
            description: '',
            origin: '',
            owner: '',
            status: '完好',
        },
        createForm: {},
        editForm: {},

        historyForm: { action: '使用', description: '', owner: '', status: '' },
        historyForId: null,

        get typeOptions() {
            return ['武器', '服饰', '道具', '交通工具', '信物', '其他'];
        },

        get statusOptions() {
            return ['完好', '获得', '使用', '损坏', '失去', '遗失'];
        },

        get actionOptions() {
            return ['获得', '使用', '损坏', '失去', '转手', '修复'];
        },

        init() {
            this.createForm = { ...this.emptyForm };
            this.loadProperties(this.projectId);
        },

        _toast(msg, type = 'info') {
            Alpine.store('app').toast(msg, type);
        },

        async loadProperties(projectId) {
            this.loading = true;
            try {
                const res = await fetch(`/api/projects/${projectId}/properties`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const items = await res.json();
                this.properties.length = 0;
                this.properties.push(...items);
            } catch (e) {
                console.error('加载道具失败:', e);
                this._toast('加载道具失败: ' + e.message, 'error');
            } finally {
                this.loading = false;
            }
        },

        openCreateModal() {
            this.createForm = { ...this.emptyForm };
            this.showCreateModal = true;
        },

        async createProperty() {
            const f = this.createForm;
            if (!f.name.trim()) {
                this._toast('请输入道具名称', 'warning');
                return;
            }
            this.submitting = true;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/properties`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ...f, name: f.name.trim() }),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this.properties.push(await res.json());
                this.showCreateModal = false;
                this._toast('道具已创建', 'success');
            } catch (e) {
                console.error('创建道具失败:', e);
                this._toast('创建失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        startEdit(prop) {
            this.editingId = prop.id;
            this.editForm = {
                name: prop.name || '',
                type: prop.type || '道具',
                description: prop.description || '',
                origin: prop.origin || '',
                owner: prop.owner || '',
                status: prop.status || '完好',
            };
        },

        cancelEdit() {
            this.editingId = null;
            this.editForm = {};
        },

        async saveEdit(prop) {
            this.submitting = true;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/properties/${prop.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.editForm),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                Object.assign(prop, await res.json());
                this.editingId = null;
                this._toast('道具已保存', 'success');
            } catch (e) {
                console.error('保存道具失败:', e);
                this._toast('保存失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        async deleteProperty(prop) {
            if (!confirm(`确定删除道具「${prop.name}」？`)) return;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/properties/${prop.id}`, {
                    method: 'DELETE',
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const idx = this.properties.findIndex(p => p.id === prop.id);
                if (idx >= 0) this.properties.splice(idx, 1);
                this._toast('道具已删除', 'success');
            } catch (e) {
                console.error('删除道具失败:', e);
                this._toast('删除失败: ' + e.message, 'error');
            }
        },

        toggleHistory(prop) {
            this.expandedId = this.expandedId === prop.id ? null : prop.id;
        },

        openHistoryForm(prop) {
            this.historyForId = prop.id;
            this.historyForm = {
                action: '使用',
                description: '',
                owner: prop.owner || '',
                status: '',
            };
            this.expandedId = prop.id;
        },

        async appendHistory(prop) {
            const f = this.historyForm;
            if (!f.description.trim()) {
                this._toast('请填写流转说明', 'warning');
                return;
            }
            this.submitting = true;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/properties/${prop.id}/history`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(f),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                Object.assign(prop, await res.json());
                this.historyForId = null;
                this._toast('流转记录已追加', 'success');
            } catch (e) {
                console.error('追加流转记录失败:', e);
                this._toast('追加失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        historyOf(prop) {
            return prop.history || [];
        },
    }));
});

window.registerComponentTemplate('property_panel', `
  <div x-data="propertyPanel" x-init="init()">
    <div class="panel-toolbar">
      <h3>🗝️ 道具（共 <span x-text="properties.length"></span> 件）</h3>
      <button class="btn-primary btn-small" @click="openCreateModal()">＋ 新建道具</button>
    </div>

    <template x-if="loading"><p class="empty-hint">⏳ 加载中...</p></template>
    <template x-if="!loading && properties.length === 0">
      <p class="empty-hint">暂无道具，场景生成时会自动识别并登记</p>
    </template>

    <div class="card-list">
      <template x-for="prop in properties" :key="prop.id">
        <div class="info-card">
          <template x-if="editingId !== prop.id">
            <div>
              <h4 x-text="prop.name"></h4>
              <span class="tag" x-text="prop.type"></span>
              <span class="tag" x-text="prop.status"></span>
              <span class="tag" x-show="prop.owner" x-text="'持有：' + prop.owner"></span>
              <p x-text="prop.description || '暂无描述'"></p>
              <p class="sb-meta" x-show="prop.origin" x-text="'来源：' + prop.origin"></p>
              <div class="form-actions">
                <button class="btn-secondary btn-small" @click="toggleHistory(prop)">
                  📜 流转 (<span x-text="historyOf(prop).length"></span>)
                </button>
                <button class="btn-secondary btn-small" @click="openHistoryForm(prop)">＋ 记录</button>
                <button class="btn-secondary btn-small" @click="startEdit(prop)">✏️ 编辑</button>
                <button class="btn-danger btn-small" @click="deleteProperty(prop)">🗑</button>
              </div>
            </div>
          </template>

          <template x-if="editingId === prop.id">
            <div>
              <div class="scene-info-grid">
                <label>名称 <input type="text" x-model="editForm.name"></label>
                <label>类型
                  <select x-model="editForm.type">
                    <template x-for="t in typeOptions" :key="t"><option :value="t" x-text="t"></option></template>
                  </select>
                </label>
                <label>状态
                  <select x-model="editForm.status">
                    <template x-for="s in statusOptions" :key="s"><option :value="s" x-text="s"></option></template>
                  </select>
                </label>
                <label>持有者 <input type="text" x-model="editForm.owner"></label>
                <label>来源 <input type="text" x-model="editForm.origin"></label>
              </div>
              <label>描述 <textarea x-model="editForm.description" rows="3"></textarea></label>
              <div class="form-actions">
                <button class="btn-primary btn-small" :disabled="submitting" @click="saveEdit(prop)">💾 保存</button>
                <button class="btn-secondary btn-small" @click="cancelEdit()">取消</button>
              </div>
            </div>
          </template>

          <!-- 流转历史 -->
          <div class="panel-section" x-show="expandedId === prop.id">
            <h4 class="role-group-title">流转历史</h4>
            <template x-if="historyOf(prop).length === 0">
              <p class="empty-hint">暂无流转记录</p>
            </template>
            <table class="data-table" x-show="historyOf(prop).length > 0">
              <thead><tr><th>动作</th><th>说明</th><th>持有者</th></tr></thead>
              <tbody>
                <template x-for="(h, i) in historyOf(prop)" :key="i">
                  <tr>
                    <td><span class="tag" x-text="h.action || '-'"></span></td>
                    <td x-text="h.description || '-'"></td>
                    <td x-text="h.owner || '-'"></td>
                  </tr>
                </template>
              </tbody>
            </table>

            <template x-if="historyForId === prop.id">
              <div class="info-card">
                <div class="scene-info-grid">
                  <label>动作
                    <select x-model="historyForm.action">
                      <template x-for="a in actionOptions" :key="a"><option :value="a" x-text="a"></option></template>
                    </select>
                  </label>
                  <label>持有者 <input type="text" x-model="historyForm.owner"></label>
                  <label>更新状态
                    <select x-model="historyForm.status">
                      <option value="">（不变）</option>
                      <template x-for="s in statusOptions" :key="s"><option :value="s" x-text="s"></option></template>
                    </select>
                  </label>
                </div>
                <label>说明 <input type="text" x-model="historyForm.description" placeholder="例如：在酒馆交给对方"></label>
                <div class="form-actions">
                  <button class="btn-primary btn-small" :disabled="submitting" @click="appendHistory(prop)">💾 追加</button>
                  <button class="btn-secondary btn-small" @click="historyForId = null">取消</button>
                </div>
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建道具弹窗 -->
    <template x-if="showCreateModal">
      <div class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal">
          <button class="modal-close-x" @click="showCreateModal = false">×</button>
          <h2>🗝️ 新建道具</h2>
          <div class="form-grid">
            <label>名称 <input type="text" x-model="createForm.name" placeholder="例如：青冥剑" required></label>
            <label>类型
              <select x-model="createForm.type">
                <template x-for="t in typeOptions" :key="t"><option :value="t" x-text="t"></option></template>
              </select>
            </label>
            <label>状态
              <select x-model="createForm.status">
                <template x-for="s in statusOptions" :key="s"><option :value="s" x-text="s"></option></template>
              </select>
            </label>
            <label>持有者 <input type="text" x-model="createForm.owner"></label>
            <label class="full-width">来源 <input type="text" x-model="createForm.origin"></label>
            <label class="full-width">描述
              <textarea x-model="createForm.description" rows="3" placeholder="外观、来历、作用..."></textarea>
            </label>
          </div>
          <div class="form-footer">
            <button class="btn-secondary" @click="showCreateModal = false">取消</button>
            <button class="btn-primary" :disabled="submitting" @click="createProperty()">
              <span x-show="!submitting">创建</span>
              <span x-show="submitting">⏳ 创建中...</span>
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
`);
