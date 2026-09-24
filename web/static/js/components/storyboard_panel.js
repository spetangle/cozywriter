// 分镜面板组件（剧本编辑器）
//
// 数据归属：storyboards 数组与 loadStoryboardsForScreenplay() 由父页面
// （scriptEditor）持有 —— 底部状态栏的「分镜数」也要读它。本组件通过 Alpine
// 作用域链调用父级方法，并只做「原地」修改数组。
document.addEventListener('alpine:init', () => {
    Alpine.data('storyboardPanel', () => ({
        density: 'standard',
        generating: false,
        submittingId: null,
        editingId: null,
        showCreateForm: false,

        emptyShot: {
            shot_number: 1,
            shot_type: '中景',
            camera_angle: '平视',
            camera_movement: '固定',
            duration_estimate: '3-5秒',
            location: '',
            visual_description: '',
            dialogue: '',
            sound_effects: '',
            notes: '',
        },
        createForm: {},
        editForm: {},

        get densityOptions() {
            return [
                { value: 'coarse', label: '粗略 (每场景 1-2 个分镜)' },
                { value: 'standard', label: '标准 (每场景 3-5 个分镜)' },
                { value: 'fine', label: '精细 (每场景 5-8 个分镜)' },
            ];
        },

        get shotTypeOptions() {
            return ['大特写', '特写', '近景', '中景', '全景', '远景'];
        },

        get cameraAngleOptions() {
            return ['平视', '仰拍', '俯拍', '鸟瞰', '荷兰角'];
        },

        get cameraMovementOptions() {
            return ['固定', '推', '拉', '摇', '移', '跟', '升降', '手持'];
        },

        get durationOptions() {
            return ['1-3秒', '3-5秒', '5-10秒', '10-15秒', '15-30秒'];
        },

        init() {
            this.createForm = { ...this.emptyShot };
        },

        _toast(msg, type = 'info') {
            Alpine.store('app').toast(msg, type);
        },

        _replaceAll(arr, items) {
            arr.length = 0;
            arr.push(...items);
        },

        async _pollTask(taskId) {
            const interval = 2000;
            const timeout = 600000;
            const t0 = Date.now();
            while (Date.now() - t0 < timeout) {
                try {
                    const res = await fetch(`/api/tasks/${taskId}`);
                    if (res.ok) {
                        const task = await res.json();
                        if (['completed', 'failed', 'cancelled'].includes(task.status)) return task;
                    }
                } catch (e) {
                    console.warn(`[StoryboardTask ${taskId}] err:`, e);
                }
                await new Promise(r => setTimeout(r, interval));
            }
            throw new Error(`Task ${taskId} 轮询超时`);
        },

        async generate() {
            const sp = this.currentScreenplay;
            if (!sp) return;
            if (!sp.content) {
                this._toast('场景正文为空，请先生成或填写正文', 'warning');
                return;
            }
            if (!confirm('确定为该场景生成分镜？已有分镜将被覆盖。')) return;
            this.generating = true;
            try {
                const res = await fetch(
                    `/api/projects/${this.projectId}/screenplays/${sp.id}/storyboards/generate`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ density: this.density }),
                    },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const { task_id } = await res.json();
                const task = await this._pollTask(task_id);
                if (task.status !== 'completed') {
                    throw new Error(task.error || `任务${task.status}`);
                }
                await this.loadStoryboardsForScreenplay(sp.id);
                this._toast('分镜生成成功', 'success');
            } catch (e) {
                console.error('生成分镜失败:', e);
                this._toast('生成分镜失败: ' + e.message, 'error');
            } finally {
                this.generating = false;
            }
        },

        async reload() {
            const sp = this.currentScreenplay;
            if (sp) await this.loadStoryboardsForScreenplay(sp.id);
        },

        openCreateForm() {
            const sp = this.currentScreenplay;
            this.createForm = {
                ...this.emptyShot,
                shot_number: this.storyboards.length + 1,
                location: (sp && sp.location) || '',
            };
            this.showCreateForm = true;
        },

        async createShot() {
            const sp = this.currentScreenplay;
            if (!sp) return;
            this.submittingId = 'create';
            try {
                const res = await fetch(
                    `/api/projects/${this.projectId}/screenplays/${sp.id}/storyboards`,
                    {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.createForm),
                    },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                this.storyboards.push(await res.json());
                this.showCreateForm = false;
                this._toast('分镜已添加', 'success');
            } catch (e) {
                console.error('添加分镜失败:', e);
                this._toast('添加失败: ' + e.message, 'error');
            } finally {
                this.submittingId = null;
            }
        },

        startEdit(shot) {
            this.editingId = shot.id;
            this.editForm = {
                shot_number: shot.shot_number,
                shot_type: shot.shot_type,
                camera_angle: shot.camera_angle,
                camera_movement: shot.camera_movement,
                duration_estimate: shot.duration_estimate,
                location: shot.location || '',
                visual_description: shot.visual_description || '',
                dialogue: shot.dialogue || '',
                sound_effects: shot.sound_effects || '',
                notes: shot.notes || '',
            };
        },

        cancelEdit() {
            this.editingId = null;
            this.editForm = {};
        },

        async saveEdit(shot) {
            this.submittingId = shot.id;
            try {
                const res = await fetch(
                    `/api/projects/${this.projectId}/storyboards/${shot.id}`,
                    {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(this.editForm),
                    },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                Object.assign(shot, await res.json());
                this.editingId = null;
                this._toast('分镜已保存', 'success');
            } catch (e) {
                console.error('保存分镜失败:', e);
                this._toast('保存失败: ' + e.message, 'error');
            } finally {
                this.submittingId = null;
            }
        },

        async deleteShot(shot) {
            if (!confirm(`确定删除镜头 ${shot.shot_number}？`)) return;
            this.submittingId = shot.id;
            try {
                const res = await fetch(
                    `/api/projects/${this.projectId}/storyboards/${shot.id}`,
                    { method: 'DELETE' },
                );
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const idx = this.storyboards.findIndex(s => s.id === shot.id);
                if (idx >= 0) this.storyboards.splice(idx, 1);
                this._toast('分镜已删除', 'success');
            } catch (e) {
                console.error('删除分镜失败:', e);
                this._toast('删除失败: ' + e.message, 'error');
            } finally {
                this.submittingId = null;
            }
        },

        sortByShotNumber() {
            const sorted = [...this.storyboards].sort(
                (a, b) => (a.shot_number || 0) - (b.shot_number || 0));
            this._replaceAll(this.storyboards, sorted);
        },
    }));
});

window.registerComponentTemplate('storyboard_panel', `
  <div x-data="storyboardPanel" x-init="init()">
    <template x-if="!currentScreenplay">
      <p class="empty-hint">请先选择一个场景</p>
    </template>

    <template x-if="currentScreenplay">
      <div>
        <div class="panel-toolbar">
          <label>分镜密度
            <select x-model="density">
              <template x-for="d in densityOptions" :key="d.value">
                <option :value="d.value" x-text="d.label"></option>
              </template>
            </select>
          </label>
          <div class="form-actions">
            <button class="btn-secondary btn-small" @click="sortByShotNumber()" x-show="storyboards.length > 1">↕ 按镜号排序</button>
            <button class="btn-secondary btn-small" @click="openCreateForm()">＋ 手动添加</button>
            <button class="btn-primary btn-small" :disabled="generating" @click="generate()">
              <span x-show="!generating">🎞️ AI 生成分镜</span>
              <span x-show="generating">⏳ 生成中...</span>
            </button>
          </div>
        </div>

        <!-- 手动添加表单 -->
        <template x-if="showCreateForm">
          <div class="info-card">
            <h4>新增分镜</h4>
            <div class="scene-info-grid">
              <label>镜号 <input type="number" x-model.number="createForm.shot_number" min="1"></label>
              <label>景别
                <select x-model="createForm.shot_type">
                  <template x-for="o in shotTypeOptions" :key="o"><option :value="o" x-text="o"></option></template>
                </select>
              </label>
              <label>角度
                <select x-model="createForm.camera_angle">
                  <template x-for="o in cameraAngleOptions" :key="o"><option :value="o" x-text="o"></option></template>
                </select>
              </label>
              <label>运镜
                <select x-model="createForm.camera_movement">
                  <template x-for="o in cameraMovementOptions" :key="o"><option :value="o" x-text="o"></option></template>
                </select>
              </label>
              <label>时长
                <select x-model="createForm.duration_estimate">
                  <template x-for="o in durationOptions" :key="o"><option :value="o" x-text="o"></option></template>
                </select>
              </label>
              <label>地点 <input type="text" x-model="createForm.location"></label>
            </div>
            <label>画面描述 <textarea x-model="createForm.visual_description" rows="3"></textarea></label>
            <label>对白 <textarea x-model="createForm.dialogue" rows="2"></textarea></label>
            <label>音效 <input type="text" x-model="createForm.sound_effects"></label>
            <label>备注 <input type="text" x-model="createForm.notes"></label>
            <div class="form-actions">
              <button class="btn-primary btn-small" :disabled="submittingId === 'create'" @click="createShot()">💾 添加</button>
              <button class="btn-secondary btn-small" @click="showCreateForm = false">取消</button>
            </div>
          </div>
        </template>

        <template x-if="storyboards.length === 0 && !showCreateForm">
          <p class="empty-hint">暂无分镜，可用「AI 生成分镜」从已定稿正文拆解，或手动添加</p>
        </template>

        <div class="storyboard-list">
          <template x-for="sb in storyboards" :key="sb.id">
            <div class="storyboard-item">
              <!-- 只读展示 -->
              <template x-if="editingId !== sb.id">
                <div>
                  <div class="sb-header">
                    <strong x-text="'镜头 ' + (sb.shot_number || '')"></strong>
                    <span class="tag" x-show="sb.shot_type" x-text="sb.shot_type"></span>
                    <span class="tag" x-show="sb.camera_angle" x-text="sb.camera_angle"></span>
                    <span class="tag" x-show="sb.camera_movement" x-text="sb.camera_movement"></span>
                    <span class="tag" x-show="sb.duration_estimate" x-text="sb.duration_estimate"></span>
                    <span class="tag" x-show="sb.location" x-text="sb.location"></span>
                    <span class="sb-actions">
                      <button class="btn-secondary btn-small" @click="startEdit(sb)">✏️</button>
                      <button class="btn-danger btn-small" :disabled="submittingId === sb.id" @click="deleteShot(sb)">🗑</button>
                    </span>
                  </div>
                  <p x-text="sb.visual_description || '（无画面描述）'"></p>
                  <p class="sb-dialogue" x-show="sb.dialogue" x-text="sb.dialogue"></p>
                  <p class="sb-meta" x-show="sb.sound_effects" x-text="'🔊 ' + sb.sound_effects"></p>
                  <p class="sb-meta" x-show="sb.notes" x-text="'📝 ' + sb.notes"></p>
                </div>
              </template>

              <!-- 编辑态 -->
              <template x-if="editingId === sb.id">
                <div>
                  <div class="scene-info-grid">
                    <label>镜号 <input type="number" x-model.number="editForm.shot_number" min="1"></label>
                    <label>景别
                      <select x-model="editForm.shot_type">
                        <template x-for="o in shotTypeOptions" :key="o"><option :value="o" x-text="o"></option></template>
                      </select>
                    </label>
                    <label>角度
                      <select x-model="editForm.camera_angle">
                        <template x-for="o in cameraAngleOptions" :key="o"><option :value="o" x-text="o"></option></template>
                      </select>
                    </label>
                    <label>运镜
                      <select x-model="editForm.camera_movement">
                        <template x-for="o in cameraMovementOptions" :key="o"><option :value="o" x-text="o"></option></template>
                      </select>
                    </label>
                    <label>时长
                      <select x-model="editForm.duration_estimate">
                        <template x-for="o in durationOptions" :key="o"><option :value="o" x-text="o"></option></template>
                      </select>
                    </label>
                    <label>地点 <input type="text" x-model="editForm.location"></label>
                  </div>
                  <label>画面描述 <textarea x-model="editForm.visual_description" rows="3"></textarea></label>
                  <label>对白 <textarea x-model="editForm.dialogue" rows="2"></textarea></label>
                  <label>音效 <input type="text" x-model="editForm.sound_effects"></label>
                  <label>备注 <input type="text" x-model="editForm.notes"></label>
                  <div class="form-actions">
                    <button class="btn-primary btn-small" :disabled="submittingId === sb.id" @click="saveEdit(sb)">💾 保存</button>
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
`);
