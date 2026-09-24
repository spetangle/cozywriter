// 角色面板组件（剧本 / 小说通用）
//
// 数据归属：characters 数组由父页面（scriptEditor）持有，本组件通过 Alpine
// 作用域链读取，并只做「原地」修改 —— 子作用域里对 characters 直接赋值会创建
// 同名自有属性从而遮蔽父级，导致父页面读不到更新。
document.addEventListener('alpine:init', () => {
    Alpine.data('characterPanel', () => ({
        activeTab: 'list',
        activeCharacter: null,
        loading: false,
        submitting: false,
        generatingAppearance: false,

        showCreateModal: false,
        createForm: { name: '', role: '配角', description: '' },

        editingId: null,
        editForm: { name: '', role: '配角', description: '' },

        // 外貌草稿：与后端 Character.appearance 的 JSON 结构一致
        appearanceDraft: {},

        // 必须与 storage/models/character.py 的 APPEARANCE_FIELDS 保持一致
        get appearanceFields() {
            return [
                { key: 'age_range', label: '年龄区间' },
                { key: 'height', label: '身高' },
                { key: 'build', label: '体型' },
                { key: 'face', label: '面部特征' },
                { key: 'hair', label: '发型发色' },
                { key: 'eyes', label: '眼睛特征' },
                { key: 'skin', label: '肤色' },
                { key: 'clothing', label: '常着服饰' },
                { key: 'accessories', label: '标志性配饰' },
                { key: 'other', label: '其他特征' },
            ];
        },

        get roleOptions() {
            return ['主角', '反派', '配角', '龙套', '群像'];
        },

        get groupedByRole() {
            const groups = {};
            for (const c of this.characters) {
                const r = c.role || '其他';
                if (!groups[r]) groups[r] = [];
                groups[r].push(c);
            }
            return groups;
        },

        init() {
            this.loadCharacters(this.projectId);
        },

        _toast(msg, type = 'info') {
            Alpine.store('app').toast(msg, type);
        },

        // 原地替换父级数组内容，保持引用不变
        _replaceAll(arr, items) {
            arr.length = 0;
            arr.push(...items);
        },

        async loadCharacters(projectId) {
            this.loading = true;
            try {
                const res = await fetch(`/api/projects/${projectId}/characters`);
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this._replaceAll(this.characters, await res.json());
            } catch (e) {
                console.error('加载角色失败:', e);
                this._toast('加载角色失败: ' + e.message, 'error');
            } finally {
                this.loading = false;
            }
        },

        openCreateModal() {
            this.createForm = { name: '', role: '配角', description: '' };
            this.showCreateModal = true;
        },

        async createCharacter() {
            const f = this.createForm;
            if (!f.name.trim()) {
                this._toast('请输入角色名称', 'warning');
                return;
            }
            this.submitting = true;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/characters`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: f.name.trim(),
                        role: f.role,
                        description: f.description.trim(),
                        appearance: {},
                    }),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this.characters.push(await res.json());
                this.showCreateModal = false;
                this._toast('角色创建成功', 'success');
            } catch (e) {
                console.error('创建角色失败:', e);
                this._toast('创建失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        startEdit(character) {
            this.editingId = character.id;
            this.editForm = {
                name: character.name || '',
                role: character.role || '配角',
                description: character.description || '',
            };
        },

        cancelEdit() {
            this.editingId = null;
            this.editForm = { name: '', role: '配角', description: '' };
        },

        async saveEdit(character) {
            this.submitting = true;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/characters/${character.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(this.editForm),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                Object.assign(character, await res.json());
                this.editingId = null;
                this._toast('保存成功', 'success');
            } catch (e) {
                console.error('更新角色失败:', e);
                this._toast('保存失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        async deleteCharacter(character) {
            if (!confirm(`确定删除角色「${character.name}」？`)) return;
            try {
                const res = await fetch(`/api/projects/${this.projectId}/characters/${character.id}`, {
                    method: 'DELETE',
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    throw new Error(err.detail || `HTTP ${res.status}`);
                }
                const idx = this.characters.findIndex(c => c.id === character.id);
                if (idx >= 0) this.characters.splice(idx, 1);
                if (this.activeCharacter && this.activeCharacter.id === character.id) {
                    this.activeCharacter = null;
                    this.activeTab = 'list';
                }
                this._toast('删除成功', 'success');
            } catch (e) {
                console.error('删除角色失败:', e);
                this._toast('删除失败: ' + e.message, 'error');
            }
        },

        openAppearance(character) {
            this.activeCharacter = character;
            this.activeTab = 'appearance';
            // 拷贝一份草稿，取消时不污染列表数据
            this.appearanceDraft = { ...(character.appearance || {}) };
        },

        backToList() {
            this.activeTab = 'list';
            this.activeCharacter = null;
            this.appearanceDraft = {};
        },

        resetAppearance() {
            if (!confirm('确定清空当前外貌草稿的所有字段？（尚未保存）')) return;
            this.appearanceDraft = {};
        },

        async saveAppearance() {
            const character = this.activeCharacter;
            if (!character) return;
            this.submitting = true;
            try {
                // 只提交非空字段，避免把空串写回覆盖已有设定
                const appearance = {};
                for (const { key } of this.appearanceFields) {
                    const v = (this.appearanceDraft[key] || '').trim();
                    if (v) appearance[key] = v;
                }
                const res = await fetch(`/api/projects/${this.projectId}/characters/${character.id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ appearance }),
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                Object.assign(character, await res.json());
                this._toast('外貌已保存', 'success');
            } catch (e) {
                console.error('保存外貌失败:', e);
                this._toast('保存失败: ' + e.message, 'error');
            } finally {
                this.submitting = false;
            }
        },

        async generateAppearance() {
            const character = this.activeCharacter;
            if (!character) return;
            this.generatingAppearance = true;
            try {
                const res = await fetch(
                    `/api/projects/${this.projectId}/characters/${character.id}/generate-appearance`,
                    { method: 'POST' },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const { task_id } = await res.json();

                // 后端是异步任务，轮询到终态再取结果
                const task = await this._pollAppearanceTask(task_id);
                if (task.status !== 'completed') {
                    throw new Error(task.error || `任务${task.status}`);
                }
                const generated = (task.result && task.result.appearance) || {};
                // 补全语义：只填空缺字段，用户已填的值不被覆盖
                this.appearanceDraft = { ...generated, ...this._nonEmpty(this.appearanceDraft) };
                this._toast('外貌已补全空缺字段，请审阅后保存', 'success');
            } catch (e) {
                console.error('生成外貌失败:', e);
                this._toast('生成失败: ' + e.message, 'error');
            } finally {
                this.generatingAppearance = false;
            }
        },

        _nonEmpty(obj) {
            const out = {};
            for (const [k, v] of Object.entries(obj || {})) {
                if (typeof v === 'string' ? v.trim() : v) out[k] = v;
            }
            return out;
        },

        async _pollAppearanceTask(taskId) {
            const interval = 2000;
            const timeout = 300000;
            const t0 = Date.now();
            while (Date.now() - t0 < timeout) {
                try {
                    const res = await fetch(`/api/tasks/${taskId}`);
                    if (res.ok) {
                        const task = await res.json();
                        if (['completed', 'failed', 'cancelled'].includes(task.status)) return task;
                    }
                } catch (e) {
                    console.warn(`[AppearanceTask ${taskId}] err:`, e);
                }
                await new Promise(r => setTimeout(r, interval));
            }
            throw new Error(`Task ${taskId} 轮询超时`);
        },

        get appearanceChanges() {
            return (this.activeCharacter && this.activeCharacter.appearance_changes) || [];
        },
    }));
});

window.registerComponentTemplate('character_panel', `
  <div x-data="characterPanel" x-init="init()">
    <!-- 列表 tab -->
    <div x-show="activeTab === 'list'">
      <div class="panel-toolbar">
        <h3>👥 角色（共 <span x-text="characters.length"></span> 个）</h3>
        <button class="btn-primary btn-small" @click="openCreateModal()">＋ 新建角色</button>
      </div>

      <template x-if="loading"><p class="empty-hint">⏳ 加载中...</p></template>
      <template x-if="!loading && characters.length === 0"><p class="empty-hint">暂无角色</p></template>

      <template x-for="(group, role) in groupedByRole" :key="role">
        <div class="panel-section">
          <h4 class="role-group-title" x-text="role"></h4>
          <div class="card-grid">
            <template x-for="c in group" :key="c.id">
              <div class="info-card">
                <template x-if="editingId !== c.id">
                  <div>
                    <h4 x-text="c.name"></h4>
                    <span class="tag" x-text="c.role"></span>
                    <span class="tag" x-show="c.appearance && Object.keys(c.appearance).length"
                          x-text="'外貌 ' + Object.keys(c.appearance).length + ' 项'"></span>
                    <p x-text="c.description || '暂无描述'"></p>
                    <div class="form-actions">
                      <button class="btn-secondary btn-small" @click="openAppearance(c)">🎭 外貌</button>
                      <button class="btn-secondary btn-small" @click="startEdit(c)">✏️ 编辑</button>
                      <button class="btn-danger btn-small" @click="deleteCharacter(c)">🗑</button>
                    </div>
                  </div>
                </template>
                <template x-if="editingId === c.id">
                  <div>
                    <label>姓名 <input type="text" x-model="editForm.name"></label>
                    <label>定位
                      <select x-model="editForm.role">
                        <template x-for="r in roleOptions" :key="r"><option :value="r" x-text="r"></option></template>
                      </select>
                    </label>
                    <label>描述 <textarea x-model="editForm.description" rows="3"></textarea></label>
                    <div class="form-actions">
                      <button class="btn-primary btn-small" :disabled="submitting" @click="saveEdit(c)">💾 保存</button>
                      <button class="btn-secondary btn-small" @click="cancelEdit()">取消</button>
                    </div>
                  </div>
                </template>
              </div>
            </template>
          </div>
        </div>
      </template>
    </div>

    <!-- 外貌 tab -->
    <div x-show="activeTab === 'appearance'">
      <template x-if="activeCharacter">
        <div>
          <div class="panel-toolbar">
            <h3>🎭 <span x-text="activeCharacter.name"></span> · 外貌设定</h3>
            <div class="form-actions">
              <button class="btn-secondary btn-small" @click="backToList()">← 返回列表</button>
              <button class="btn-secondary btn-small" :disabled="generatingAppearance" @click="generateAppearance()">
                <span x-show="!generatingAppearance">🤖 AI 生成</span>
                <span x-show="generatingAppearance">⏳ 生成中...</span>
              </button>
              <button class="btn-secondary btn-small" @click="resetAppearance()">清空</button>
              <button class="btn-primary btn-small" :disabled="submitting" @click="saveAppearance()">💾 保存外貌</button>
            </div>
          </div>

          <div class="form-grid">
            <template x-for="f in appearanceFields" :key="f.key">
              <label x-bind:class="f.key === 'face' || f.key === 'clothing' || f.key === 'other' ? 'full-width' : ''">
                <span x-text="f.label"></span>
                <input type="text" x-model="appearanceDraft[f.key]">
              </label>
            </template>
          </div>

          <div class="panel-section">
            <h4 class="role-group-title">外貌变化记录（共 <span x-text="appearanceChanges.length"></span> 条）</h4>
            <template x-if="appearanceChanges.length === 0"><p class="empty-hint">暂无变化记录，场景生成后会自动追加</p></template>
            <table class="data-table" x-show="appearanceChanges.length > 0">
              <thead><tr><th>场景</th><th>变化</th><th>原因</th><th>变化前</th><th>变化后</th></tr></thead>
              <tbody>
                <template x-for="(ch, i) in appearanceChanges" :key="i">
                  <tr>
                    <td x-text="ch.scene_id || '-'"></td>
                    <td x-text="ch.description || '-'"></td>
                    <td x-text="ch.reason || '-'"></td>
                    <td x-text="ch.before || '-'"></td>
                    <td x-text="ch.after || '-'"></td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建角色弹窗 -->
    <template x-if="showCreateModal">
      <div class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal">
          <button class="modal-close-x" @click="showCreateModal = false">×</button>
          <h2>👤 新建角色</h2>
          <div class="form-grid">
            <label>姓名
              <input type="text" x-model="createForm.name" placeholder="例如：林墨白" required>
            </label>
            <label>定位
              <select x-model="createForm.role">
                <template x-for="r in roleOptions" :key="r"><option :value="r" x-text="r"></option></template>
              </select>
            </label>
            <label class="full-width">描述
              <textarea x-model="createForm.description" rows="3" placeholder="身份、性格、动机..."></textarea>
            </label>
          </div>
          <p class="modal-hint">外貌可在创建后进入「🎭 外貌」页签填写或用 AI 生成。</p>
          <div class="form-footer">
            <button class="btn-secondary" @click="showCreateModal = false">取消</button>
            <button class="btn-primary" :disabled="submitting" @click="createCharacter()">
              <span x-show="!submitting">创建</span>
              <span x-show="submitting">⏳ 创建中...</span>
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
`);
