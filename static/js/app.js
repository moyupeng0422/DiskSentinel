/* DiskSentinel 前端主逻辑 */

const API = '';

// ========== 工具函数 ==========

function fmtSize(bytes) {
  if (bytes === undefined || bytes === null) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  while (bytes >= 1024 && i < units.length - 1) { bytes /= 1024; i++; }
  return bytes.toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
}

function fmtDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toLocaleString('zh-CN');
}

async function api(path, options = {}) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || '请求失败');
  }
  return res.json();
}

// ========== 导航 ==========

let currentPage = 'dashboard';
const charts = {};

function navigate(page) {
  if (_dirPollTimer) { clearInterval(_dirPollTimer); _dirPollTimer = null; }
  document.querySelectorAll('.page').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.remove('active'));
  document.getElementById('page-' + page).style.display = 'block';
  document.querySelector(`[data-page="${page}"]`).classList.add('active');
  currentPage = page;
  loadPage(page);
}

function loadPage(page) {
  switch (page) {
    case 'dashboard': loadDashboard(); break;
    case 'snapshots': loadSnapshots(); break;
    case 'comparison': loadComparison(); break;
    case 'cleaner': loadCleaner(); break;
    case 'monitor': break;
  }
}

// ========== 清理目录状态 ==========
let cleanerDirs = []; // {path, total_size, own_size, file_count}

function renderLargestDirs(dirs) {
  const tbody = document.getElementById('largest-dirs');
  const permCount = dirs.filter(d => d.permission_error).length;
  let html = '';
  if (permCount > 0) {
    html += `<tr><td colspan="5" class="text-muted" style="font-size:12px;padding:8px">
      <strong>提示:</strong> ${permCount} 个目录因权限不足未完全扫描。
      <button class="btn btn-outline" style="padding:2px 8px;font-size:11px;margin-left:8px" onclick="loadDashboard()">刷新</button>
    </td></tr>`;
  }
  html += dirs.map((d, i) => {
    const perm = d.permission_error ? ' <span class="text-muted" title="权限不足">[部分]</span>' : '';
    const checked = cleanerDirs.some(c => c.path === d.path) ? 'checked' : '';
    return `<tr><td><input type="checkbox" class="dir-check" value="${i}" ${checked} onchange="updateSelectedCount()"></td><td>${escHtml(d.path)}${perm}</td><td class="text-right">${fmtSize(d.own_size)}</td><td class="text-right text-muted">${fmtSize(d.total_size)}</td><td class="text-right">${d.file_count?.toLocaleString() || '-'}</td></tr>`;
  }).join('');
  tbody.innerHTML = html;
  updateSelectedCount();
}

let _currentDirs = [];

async function loadDashboard() {
  try {
    const overview = await api('/api/dashboard/overview');
    renderOverview(overview);
  } catch (e) { console.error('加载概览失败:', e); }

  try {
    const history = await api('/api/dashboard/usage-history?days=30');
    renderTrendChart(history);
  } catch (e) { console.error('加载趋势失败:', e); }

  try {
    const aiDirs = await api('/api/cleaner/selected-dirs').catch(() => []);
    cleanerDirs = [...aiDirs];

    // 先检查当前扫描状态，避免重复发起或覆盖已完成的结果
    const state = await api('/api/dashboard/largest-dirs');
    if (state.status === 'completed') {
      _currentDirs = state.dirs;
      renderLargestDirs(state.dirs);
      if (state.file_types) renderTypeChart(state.file_types);
      document.getElementById('selected-count').textContent = '';
    } else {
      // 扫描中或未开始，启动扫描并轮询
      if (state.status === 'idle') {
        await api('/api/dashboard/largest-dirs', { method: 'POST' });
      }
      pollDirScanProgress();
    }
  } catch (e) { console.error('启动目录扫描失败:', e); }
}

let _dirPollTimer = null;

function pollDirScanProgress() {
  if (_dirPollTimer) clearInterval(_dirPollTimer);
  _dirPollTimer = setInterval(async () => {
    try {
      const state = await api('/api/dashboard/largest-dirs');
      if (state.status === 'scanning') {
        document.getElementById('selected-count').innerHTML = `<span class="scanning-text">扫描中...</span> 已扫描 ${state.dir_count?.toLocaleString() || 0} 个目录`;
      } else if (state.status === 'completed') {
        clearInterval(_dirPollTimer);
        _dirPollTimer = null;
        _currentDirs = state.dirs;
        renderLargestDirs(state.dirs);
        if (state.file_types) renderTypeChart(state.file_types);
        document.getElementById('selected-count').textContent = '';
      }
    } catch (e) { console.error('轮询进度失败:', e); }
  }, 1000);
}

function renderOverview(d) {
  const pct = d.usage_percent;
  const cls = pct > 90 ? 'high' : pct > 70 ? 'medium' : 'low';
  const cardCls = pct > 90 ? 'danger' : pct > 70 ? 'warning' : 'success';
  document.getElementById('disk-stats').innerHTML = `
    <div class="stat-card ${cardCls}">
      <div class="label">C 盘使用率</div>
      <div class="value">${pct}%</div>
      <div class="usage-bar"><div class="fill ${cls}" style="width:${pct}%"></div></div>
    </div>
    <div class="stat-card">
      <div class="label">总容量</div>
      <div class="value">${fmtSize(d.total_bytes)}</div>
    </div>
    <div class="stat-card">
      <div class="label">已使用</div>
      <div class="value">${fmtSize(d.used_bytes)}</div>
    </div>
    <div class="stat-card">
      <div class="label">可用空间</div>
      <div class="value">${fmtSize(d.free_bytes)}</div>
    </div>
    <div class="stat-card">
      <div class="label">簇大小</div>
      <div class="value">${d.cluster_size}</div>
      <div class="sub">字节</div>
    </div>
  `;
}

function renderTrendChart(history) {
  const ctx = document.getElementById('trend-chart').getContext('2d');
  if (charts.trend) charts.trend.destroy();
  const labels = history.map(h => fmtDate(h.recorded_at).slice(5, 16));
  charts.trend = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: '已用', data: history.map(h => h.used_bytes), borderColor: '#d93025', backgroundColor: 'rgba(217,48,37,0.1)', fill: true, tension: 0.3 },
        { label: '可用', data: history.map(h => h.free_bytes), borderColor: '#1e8e3e', backgroundColor: 'rgba(30,142,62,0.1)', fill: true, tension: 0.3 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      scales: {
        x: { ticks: { maxTicksLimit: 10, font: { size: 11 } } },
        y: { ticks: { callback: v => fmtSize(v), font: { size: 11 } } },
      },
      plugins: { legend: { labels: { font: { size: 12 } } } },
    },
  });
}

function renderTypeChart(types) {
  const ctx = document.getElementById('type-chart').getContext('2d');
  if (charts.type) charts.type.destroy();
  const colors = ['#1a73e8','#d93025','#1e8e3e','#f9ab00','#9334e6','#e8710a','#0d652d','#a50e0e','#7627bb','#4285f4','#ea4335','#34a853'];
  const entries = Object.entries(types).slice(0, 10);
  charts.type = new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: entries.map(e => e[0]),
      datasets: [{ data: entries.map(e => e[1].size), backgroundColor: colors.slice(0, entries.length) }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { font: { size: 11 }, boxWidth: 12 } },
        tooltip: { callbacks: { label: ctx => `${ctx.label}: ${fmtSize(ctx.raw)}` } },
      },
    },
  });
}

// ========== 目录勾选 & 发送到清理中心 ==========

function toggleAllDirs(checked) {
  document.querySelectorAll('.dir-check').forEach(cb => cb.checked = checked);
  updateSelectedCount();
}

function updateSelectedCount() {
  const checked = document.querySelectorAll('.dir-check:checked');
  const btn = document.getElementById('btn-send-cleaner');
  const span = document.getElementById('selected-count');
  if (checked.length > 0) {
    btn.disabled = false;
    span.textContent = `已选 ${checked.length} 个目录`;
  } else {
    btn.disabled = true;
    span.textContent = '';
  }
}

function sendToCleaner() {
  const checked = document.querySelectorAll('.dir-check:checked');
  if (!checked.length) return;
  const newDirs = [];
  let alreadyCount = 0;
  checked.forEach(cb => {
    const d = _currentDirs[parseInt(cb.value)];
    if (!d) return;
    if (cleanerDirs.some(c => c.path === d.path)) {
      alreadyCount++;
    } else {
      newDirs.push({ path: d.path, total_size: d.total_size, own_size: d.own_size, file_count: d.file_count });
    }
  });
  cleanerDirs.push(...newDirs);
  const msg = newDirs.length > 0
    ? `已添加 ${newDirs.length} 个目录到清理中心${alreadyCount > 0 ? `（${alreadyCount} 个已存在）` : ''}（共 ${cleanerDirs.length} 个）`
    : `${alreadyCount} 个目录已在清理中心列表中（共 ${cleanerDirs.length} 个）`;
  alert(msg);
}

function clearCleanerDirs() {
  cleanerDirs = [];
  renderCleanerDirs();
}

function renderCleanerDirs() {
  const container = document.getElementById('cleaner-dirs-list');
  const btnPreview = document.getElementById('btn-preview-dirs');
  const btnClear = document.getElementById('btn-clear-dirs');
  if (!cleanerDirs.length) {
    container.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary)">暂无已选目录，请在仪表盘中勾选目录后点击"发送到清理中心"</div>';
    btnPreview.disabled = true;
    btnClear.style.display = 'none';
    return;
  }
  btnPreview.disabled = false;
  btnClear.style.display = '';
  const totalSize = cleanerDirs.reduce((s, d) => s + d.total_size, 0);
  let html = `<div style="padding:8px 12px;font-size:13px;color:var(--text-secondary);border-bottom:1px solid #f1f3f4">共 ${cleanerDirs.length} 个目录，合计 ${fmtSize(totalSize)}</div>`;
  html += cleanerDirs.map((d, i) => `
    <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 12px;border-bottom:1px solid #f1f3f4">
      <div style="font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:500px" title="${escHtml(d.path)}">${escHtml(d.path)}</div>
      <div style="display:flex;align-items:center;gap:12px">
        <span style="font-size:12px;color:var(--text-secondary)">${fmtSize(d.total_size)}</span>
        <button class="btn btn-outline" style="padding:2px 6px;font-size:11px" onclick="removeCleanerDir(${i})">移除</button>
      </div>
    </div>
  `).join('');
  container.innerHTML = html;
}

function removeCleanerDir(index) {
  cleanerDirs.splice(index, 1);
  renderCleanerDirs();
}

function switchCleanerTab(tab) {
  document.querySelectorAll('#page-cleaner .tab').forEach((t, i) => {
    t.classList.toggle('active', (tab === 'dirs' && i === 0) || (tab === 'rules' && i === 1));
  });
  document.getElementById('cleaner-dirs-tab').style.display = tab === 'dirs' ? '' : 'none';
  document.getElementById('cleaner-rules-tab').style.display = tab === 'rules' ? '' : 'none';
  if (tab === 'dirs') renderCleanerDirs();
}

let dirPreviewData = null;

async function previewDirCleanup() {
  if (!cleanerDirs.length) return;
  try {
    const dirPaths = cleanerDirs.map(d => d.path);
    const data = await api('/api/cleaner/preview-dirs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dirs: dirPaths }) });
    dirPreviewData = data;
    document.getElementById('cleanup-preview').style.display = 'block';
    document.getElementById('btn-execute-dirs').disabled = data.total_files === 0;
    document.getElementById('preview-summary').innerHTML = `<strong>共 ${data.total_files.toLocaleString()} 个文件，预计释放 ${fmtSize(data.total_size)}</strong>`;
    const tbody = document.getElementById('preview-files');
    tbody.innerHTML = data.files.map(f => `
      <tr>
        <td style="max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(f.path)}">${escHtml(f.path)}</td>
        <td class="text-right">${fmtSize(f.size)}</td>
        <td style="font-size:12px;color:var(--text-secondary)">${escHtml(f.name)}</td>
      </tr>
    `).join('');
  } catch (e) {
    alert('预览失败: ' + e.message);
  }
}

async function executeDirCleanup() {
  const drive = document.getElementById('backup-drive').value;
  if (!drive) return alert('请选择备份目标盘');
  if (!dirPreviewData || !dirPreviewData.total_files) return alert('请先点击"预览清理"查看待清理文件');
  const totalSize = dirPreviewData.total_size;
  if (!confirm(`确定将 ${cleanerDirs.length} 个目录中的文件备份到 ${drive} 后清理？\n预计释放 ${fmtSize(totalSize)}`)) return;
  try {
    const dirPaths = cleanerDirs.map(d => d.path);
    const result = await api('/api/cleaner/execute-dirs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ dirs: dirPaths, backup_drive: drive }) });
    if (result.success) {
      alert(`清理完成！移动 ${result.files_moved} 个文件，释放 ${fmtSize(result.bytes_freed)}`);
      cleanerDirs = [];
      renderCleanerDirs();
      loadCleaner();
    } else {
      alert('清理失败: ' + (result.error || '未知错误'));
    }
  } catch (e) {
    alert('清理失败: ' + e.message);
  }
}

// ========== 快照管理 ==========

async function loadSnapshots() {
  const snapshots = await api('/api/snapshots');
  const tbody = document.getElementById('snapshot-list');
  if (!snapshots.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="text-muted" style="text-align:center;padding:20px">暂无快照，点击"创建新快照"开始</td></tr>';
    return;
  }
  tbody.innerHTML = snapshots.map(s => {
    const statusMap = { running: '扫描中...', completed: '完成', failed: '失败' };
    const statusCls = s.status === 'completed' ? 'text-success' : s.status === 'failed' ? 'text-danger' : '';
    return `<tr>
      <td>${escHtml(s.name)}</td>
      <td class="text-muted">${fmtDate(s.scan_started)}</td>
      <td class="text-right">${s.total_files?.toLocaleString() || '-'}</td>
      <td class="text-right">${fmtSize(s.total_size)}</td>
      <td class="text-right">${fmtSize(s.total_alloc)}</td>
      <td class="${statusCls}">${statusMap[s.status] || s.status}</td>
      <td><button class="btn btn-outline" style="padding:4px 8px;font-size:12px" onclick="deleteSnapshot(${s.id})">删除</button></td>
    </tr>`;
  }).join('');
}

async function createSnapshot() {
  try {
    const { snapshot_id } = await api('/api/snapshots', { method: 'POST' });
    document.getElementById('scan-progress').style.display = 'block';
    const es = new EventSource(API + `/api/snapshots/${snapshot_id}/progress`);
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      const pct = Math.min(99, d.file_count ? Math.log10(d.file_count + 1) * 15 : 0);
      document.getElementById('progress-fill').style.width = pct + '%';
      document.getElementById('progress-text').textContent = `已扫描 ${d.file_count?.toLocaleString() || 0} 个文件...`;
      if (d.done) {
        es.close();
        document.getElementById('progress-fill').style.width = '100%';
        document.getElementById('progress-text').textContent = `扫描完成！共 ${d.file_count?.toLocaleString()} 个文件`;
        setTimeout(() => document.getElementById('scan-progress').style.display = 'none', 3000);
        loadSnapshots();
      }
      if (d.error) {
        es.close();
        document.getElementById('progress-text').textContent = `扫描失败: ${d.error}`;
        loadSnapshots();
      }
    };
    loadSnapshots();
  } catch (e) {
    alert('创建快照失败: ' + e.message);
  }
}

async function deleteSnapshot(id) {
  if (!confirm('确定删除此快照？')) return;
  await api(`/api/snapshots/${id}`, { method: 'DELETE' });
  loadSnapshots();
}

// ========== 快照对比 ==========

async function loadComparison() {
  const snapshots = await api('/api/snapshots?limit=50');
  const options = snapshots.map(s => `<option value="${s.id}">${s.name} (${fmtDate(s.scan_started)})</option>`).join('');
  document.getElementById('compare-base').innerHTML = options;
  document.getElementById('compare-new').innerHTML = options;
  if (snapshots.length >= 2) {
    document.getElementById('compare-new').selectedIndex = 0;
    document.getElementById('compare-base').selectedIndex = 1;
  }
}

async function runComparison() {
  const baseId = document.getElementById('compare-base').value;
  const newId = document.getElementById('compare-new').value;
  if (!baseId || !newId) return alert('请选择两个快照');
  if (baseId === newId) return alert('请选择不同的快照');

  document.getElementById('comparison-result').style.display = 'block';
  document.getElementById('comparison-empty').style.display = 'none';

  const data = await api(`/api/comparison/${baseId}/${newId}/summary`);
  const s = data;
  document.getElementById('diff-summary').innerHTML = `
    <div class="diff-card new"><div class="count text-success">${s.new_count}</div><div class="size">${fmtSize(s.new_total_bytes)}</div><div style="font-size:12px">新增</div></div>
    <div class="diff-card deleted"><div class="count text-danger">${s.deleted_count}</div><div class="size">${fmtSize(s.deleted_total_bytes)}</div><div style="font-size:12px">删除</div></div>
    <div class="diff-card grown"><div class="count text-danger">${s.grown_count}</div><div class="size">+${fmtSize(s.grown_total_bytes)}</div><div style="font-size:12px">变大</div></div>
    <div class="diff-card shrunk"><div class="count text-success">${s.shrunk_count}</div><div class="size">-${fmtSize(s.shrunk_total_bytes)}</div><div style="font-size:12px">变小</div></div>
  `;
  switchDiffTab('new', baseId, newId);
}

let diffBaseId, diffNewId;
function switchDiffTab(tab, bId, nId) {
  document.querySelectorAll('#page-comparison .tab').forEach(t => t.classList.remove('active'));
  event?.target?.classList?.add('active');
  if (bId) { diffBaseId = bId; diffNewId = nId; }
  if (!diffBaseId) return;

  const urlMap = { new: 'new-files', deleted: 'deleted-files', grown: 'grown-files', shrunk: 'shrunk-files' };
  api(`/api/comparison/${diffBaseId}/${diffNewId}/${urlMap[tab]}`).then(data => {
    const items = data.items;
    const tbody = document.getElementById('diff-table');
    if (!items.length) { tbody.innerHTML = '<tr><td colspan="3" class="text-muted" style="text-align:center;padding:20px">无数据</td></tr>'; return; }
    tbody.innerHTML = items.map(item => {
      const delta = item.delta || 0;
      const cls = (tab === 'new' || tab === 'grown') ? 'text-danger' : 'text-success';
      const sign = tab === 'new' ? '+' : tab === 'grown' ? '+' : '-';
      return `<tr>
        <td style="max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(item.file_path)}">${escHtml(item.file_path)}</td>
        <td class="text-right">${fmtSize(item.file_size)}</td>
        <td class="text-right ${cls}">${tab === 'new' ? fmtSize(item.file_size) : (delta ? sign + fmtSize(Math.abs(delta)) : '-')}</td>
      </tr>`;
    }).join('');
  });
}

// ========== 清理中心 ==========

let previewData = null;

async function loadCleaner() {
  renderCleanerDirs();
  const [rules, targets, backups] = await Promise.all([
    api('/api/cleaner/rules'),
    api('/api/cleaner/backup-targets'),
    api('/api/cleaner/backups'),
  ]);

  // 备份目标盘
  const sel = document.getElementById('backup-drive');
  sel.innerHTML = targets.map(t => `<option value="${t.drive}">${t.label}</option>`).join('');
  if (!targets.length) sel.innerHTML = '<option>无可用目标盘</option>';

  // 清理规则
  const container = document.getElementById('cleaner-rules');
  const categories = {};
  rules.forEach(r => { (categories[r.category] = categories[r.category] || []).push(r); });
  const catNames = { temp: '临时文件', cache: '缓存', logs: '日志', update: '系统更新', other: '其他' };

  container.innerHTML = Object.entries(categories).map(([cat, rs]) => `
    <div class="collapse-header" onclick="toggleCollapse(this)">
      <span>${catNames[cat] || cat} (${rs.length})</span>
      <span class="arrow">&#9654;</span>
    </div>
    <div class="collapse-body">
      ${rs.map(r => `
        <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #f1f3f4">
          <div>
            <div style="font-size:13px">${escHtml(r.name)}</div>
            <div style="font-size:11px;color:var(--text-secondary)">${escHtml(r.description || '')}</div>
          </div>
          <label class="switch">
            <input type="checkbox" ${r.is_enabled ? 'checked' : ''} onchange="toggleRule(${r.id}, this.checked)">
            <span class="slider"></span>
          </label>
        </div>
      `).join('')}
    </div>
  `).join('');

  // 备份历史
  const btbody = document.getElementById('backup-history');
  if (!backups.length) {
    btbody.innerHTML = '<tr><td colspan="5" class="text-muted" style="text-align:center;padding:16px">暂无备份记录</td></tr>';
  } else {
    btbody.innerHTML = backups.map(b => `
      <tr>
        <td>${fmtDate(b.created_at)}</td>
        <td>${b.backup_drive}</td>
        <td class="text-right">${b.total_files}</td>
        <td class="text-right">${fmtSize(b.total_size)}</td>
        <td><button class="btn btn-outline" style="padding:4px 8px;font-size:12px" onclick="restoreBackup('${b.batch_id}')">恢复</button></td>
      </tr>
    `).join('');
  }
}

function toggleCollapse(header) {
  header.classList.toggle('open');
  header.nextElementSibling.classList.toggle('open');
}

async function toggleRule(id, enabled) {
  await api(`/api/cleaner/rules/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled }) });
}

async function previewCleanup() {
  try {
    const data = await api('/api/cleaner/preview', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ use_enabled: true }) });
    previewData = data;
    document.getElementById('cleanup-preview').style.display = 'block';
    document.getElementById('btn-execute').disabled = data.total_files === 0;

    const catNames = { temp: '临时文件', cache: '缓存', logs: '日志', update: '系统更新', other: '其他' };
    document.getElementById('preview-summary').innerHTML = `
      <div style="margin-bottom:12px">
        <strong>共 ${data.total_files} 个文件，预计释放 ${fmtSize(data.total_size)}</strong>
      </div>
      ${Object.entries(data.by_category).map(([cat, s]) => `
        <div style="font-size:13px;margin:4px 0">${catNames[cat] || cat}: ${s.count} 个文件 (${fmtSize(s.size)})</div>
      `).join('')}
    `;

    const tbody = document.getElementById('preview-files');
    tbody.innerHTML = data.files.map(f => `
      <tr>
        <td style="max-width:500px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${escHtml(f.path)}">${escHtml(f.path)}</td>
        <td class="text-right">${fmtSize(f.size)}</td>
        <td>${escHtml(f.rule_name)}</td>
        <td><span class="${f.risk_level === 'medium' ? 'text-danger' : 'text-success'}">${f.risk_level}</span></td>
      </tr>
    `).join('');
  } catch (e) {
    alert('预览失败: ' + e.message);
  }
}

async function executeCleanup() {
  const drive = document.getElementById('backup-drive').value;
  if (!drive) return alert('请选择备份目标盘');
  if (!confirm(`确定将文件备份到 ${drive} 后清理？\n预计释放 ${fmtSize(previewData?.total_size || 0)}`)) return;

  try {
    const rules = await api('/api/cleaner/rules');
    const enabledIds = rules.filter(r => r.is_enabled).map(r => r.id);
    const result = await api('/api/cleaner/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rule_ids: enabledIds, backup_drive: drive }),
    });

    if (result.success) {
      alert(`清理完成！\n已备份 ${result.files_moved} 个文件\n释放 ${fmtSize(result.bytes_freed)}\n备份位置: ${result.backup_dir}`);
      loadCleaner();
    } else {
      alert('清理失败: ' + (result.error || '未知错误'));
    }
  } catch (e) {
    alert('执行失败: ' + e.message);
  }
}

async function restoreBackup(batchId) {
  if (!confirm('确定从备份恢复文件到 C 盘原位？')) return;
  try {
    const result = await api('/api/cleaner/restore', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ batch_id: batchId }),
    });
    if (result.success) {
      alert(`恢复完成！${result.files_restored} 个文件已恢复`);
      loadCleaner();
    } else {
      alert('恢复失败: ' + (result.error || ''));
    }
  } catch (e) {
    alert('恢复失败: ' + e.message);
  }
}

// ========== 实时监控 ==========

let monitorEs = null;
let _monitorStats = {}; // {dirPath: {created, modified, deleted, sizeChange}}
let _monitorTotalEvents = 0;
let _analysisTimer = null;

function _getDirLevel(path, level) {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts.slice(0, level).join('\\') + '\\';
}

function _recordMonitorEvent(d) {
  _monitorTotalEvents++;
  const dir = _getDirLevel(d.path, 3); // C:\Users\xxx\
  if (!_monitorStats[dir]) _monitorStats[dir] = { created: 0, modified: 0, deleted: 0, sizeChange: 0 };
  const s = _monitorStats[dir];
  if (d.type === 'created') { s.created++; s.sizeChange += d.size || 0; }
  else if (d.type === 'modified') { s.modified++; }
  else if (d.type === 'deleted') { s.deleted++; }
}

function _renderAnalysis() {
  const panel = document.getElementById('monitor-analysis');
  if (!panel) return;

  const entries = Object.entries(_monitorStats).filter(([, s]) => s.created + s.modified + s.deleted > 0);
  if (entries.length === 0) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';

  document.getElementById('analysis-summary').textContent =
    `共监控到 ${_monitorTotalEvents.toLocaleString()} 个事件，涉及 ${entries.length} 个目录`;

  // 异常检测：单目录操作 > 20 次，或大小变化 > 50MB
  const alerts = [];
  const sorted = entries.sort((a, b) => {
    const sa = a[1].created + a[1].modified + a[1].deleted;
    const sb = b[1].created + b[1].modified + b[1].deleted;
    return sb - sa;
  }).slice(0, 10);

  let alertsHtml = '';
  for (const [dir, s] of sorted) {
    const total = s.created + s.modified + s.deleted;
    if (s.sizeChange > 500 * 1024 * 1024) {
      alertsHtml += `<div class="analysis-alert">&#9888; <strong>${escHtml(dir)}</strong> — 新增占用 ${fmtSize(s.sizeChange)}</div>`;
    }
  }
  document.getElementById('analysis-alerts').innerHTML = alertsHtml;

  let tableHtml = '';
  for (const [dir, s] of sorted) {
    const total = s.created + s.modified + s.deleted;
    const abnormal = s.sizeChange > 500 * 1024 * 1024;
    tableHtml += `<tr${abnormal ? ' class="row-alert"' : ''}><td>${escHtml(dir)}</td><td class="text-right">${s.created}</td><td class="text-right">${s.modified}</td><td class="text-right">${s.deleted}</td><td class="text-right">${s.sizeChange ? fmtSize(s.sizeChange) : '-'}</td></tr>`;
  }
  document.getElementById('analysis-table').innerHTML = tableHtml;
}

async function startMonitor() {
  await api('/api/monitor/start', { method: 'POST' });
  document.getElementById('btn-monitor-start').disabled = true;
  document.getElementById('btn-monitor-stop').disabled = false;
  document.getElementById('monitor-status').textContent = '监控中...';
  document.getElementById('event-stream').innerHTML = '';
  document.getElementById('monitor-analysis').style.display = 'none';
  _monitorStats = {};
  _monitorTotalEvents = 0;

  _analysisTimer = setInterval(_renderAnalysis, 3000);

  monitorEs = new EventSource(API + '/api/monitor/events');
  monitorEs.onmessage = (e) => {
    if (!e.data) return;
    const d = JSON.parse(e.data);
    if (d.type === 'error') {
      document.getElementById('monitor-status').textContent = '错误: ' + d.message;
      return;
    }
    _recordMonitorEvent(d);
    const badgeCls = { created: 'badge-created', deleted: 'badge-deleted', modified: 'badge-modified' }[d.type] || '';
    const typeNames = { created: '新增', deleted: '删除', modified: '修改', renamed_old: '重命名', renamed_new: '重命名' };
    const now = new Date().toLocaleTimeString('zh-CN');
    const div = document.createElement('div');
    div.className = 'event-item';
    div.innerHTML = `<span class="time">${now}</span><span class="badge ${badgeCls}">${typeNames[d.type] || d.type}</span>${escHtml(d.path)}${d.size ? ` (${fmtSize(d.size)})` : ''}`;
    const stream = document.getElementById('event-stream');
    stream.prepend(div);
    while (stream.children.length > 500) stream.removeChild(stream.lastChild);
  };
  monitorEs.onerror = () => {
    document.getElementById('monitor-status').textContent = '连接断开';
  };
}

async function stopMonitor() {
  await api('/api/monitor/stop', { method: 'POST' });
  if (monitorEs) { monitorEs.close(); monitorEs = null; }
  if (_analysisTimer) { clearInterval(_analysisTimer); _analysisTimer = null; }
  _renderAnalysis();
  document.getElementById('btn-monitor-start').disabled = false;
  document.getElementById('btn-monitor-stop').disabled = true;
  document.getElementById('monitor-status').textContent = '已停止';
}

// ========== 工具 ==========

function escHtml(str) {
  const div = document.createElement('div');
  div.textContent = str || '';
  return div.innerHTML;
}

// 初始化
document.addEventListener('DOMContentLoaded', () => loadPage('dashboard'));
