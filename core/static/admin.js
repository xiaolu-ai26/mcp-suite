/* 秋招岗位库 · 管理后台交互。CSP 安全：无内联脚本、无 eval、无第三方库；全部 addEventListener。
 * API 路径相对当前文档解析：页面在 /qiuzhao/admin，./api/... 自动解析到 /qiuzhao/api/...。
 * Token 只存 sessionStorage（随标签页关闭清除），仅用于 Authorization 请求头，绝不写入 URL、日志或页面。
 * 正式码 / 测试码：能否删除、删除时是否作废 key 由服务端判定（codes 列表里的 deletable、delete_revokes_key）；
 * 早鸟阶梯和剩余名额来自服务端（stats.early_bird）。这里不写死任何规则或价格数字。 */
(function () {
  'use strict';
  var TOKEN_KEY = 'qz_admin_token';
  var PLANS = ['qiuzhao-2026'];
  var token = '';
  var allCodes = [];
  var codeFilter = 'all';
  var kindFilter = 'all';
  var noteFilter = '';

  var $ = function (id) { return document.getElementById(id); };
  // 接口前缀相对当前后台页解析：去掉末尾的 /admin、/admin/ 或 /admin.html，得到 /qiuzhao/ 前缀。
  var BASE = location.pathname.replace(/\/admin(?:\.html)?\/?$/, '/');
  if (BASE.slice(-1) !== '/') BASE += '/';
  function api(path) { return BASE + path; }
  function sh(dateLike) {
    var d = new Date(dateLike);
    if (isNaN(d.getTime())) return '';
    try { return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(d); }
    catch (e) { return d.toISOString().slice(0, 10); }
  }
  function fmtTime(s) {
    if (!s) return '—';
    var t = String(s).replace('T', ' ');
    return t.length >= 16 ? t.slice(0, 16) : t;
  }
  function money(n) { var v = Number(n); return '¥' + (isFinite(v) ? v : 0).toFixed(2); }
  function yuan(n) { var v = Number(n); return isFinite(v) ? '¥' + v.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '—'; }

  var toastTimer;
  function toast(text) {
    var t = $('toast'); t.textContent = text; t.classList.add('show');
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove('show'); }, 2200);
  }
  function msg(id, text, kind) {
    var el = $(id); if (!el) return;
    el.textContent = text || ''; el.className = 'msg' + (kind ? ' ' + kind : '');
  }

  function readToken() { try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch (e) { return ''; } }
  function saveToken(t) { try { sessionStorage.setItem(TOKEN_KEY, t); } catch (e) {} }
  function dropToken() { try { sessionStorage.removeItem(TOKEN_KEY); } catch (e) {} }

  // Auth error surfaced so callers can bounce to the login view.
  function AuthError() { this.name = 'AuthError'; }
  AuthError.prototype = Object.create(Error.prototype);

  // opts: { method, body }（body 为 JSON 字符串）。
  function request(path, opts) {
    opts = opts || {};
    var headers = { 'Authorization': 'Bearer ' + token };
    if (opts.body != null) headers['Content-Type'] = 'application/json';
    return fetch(api(path), {
      method: opts.method || 'GET', body: opts.body, headers: headers,
      cache: 'no-store', credentials: 'omit'
    }).then(function (res) {
      if (res.status === 401 || res.status === 403) throw new AuthError();
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok) throw new Error(body && body.error ? body.error : ('请求失败（' + res.status + '）'));
        return body;
      });
    });
  }
  function handleError(e, id) {
    if (e instanceof AuthError) { logout('登录已过期或令牌无效，请重新登录。'); return true; }
    if (id) msg(id, e.message || '网络错误，请重试。', 'error');
    return false;
  }

  // ---- views ----
  function showLogin(text, kind) {
    $('app-view').hidden = true; $('login-view').hidden = false;
    if (text) msg('login-msg', text, kind || 'error'); else msg('login-msg', '');
    var f = $('token-input'); if (f) { f.value = ''; f.focus(); }
  }
  function showApp() {
    $('login-view').hidden = true; $('app-view').hidden = false;
    refreshAll();
  }
  function logout(text) {
    token = ''; dropToken(); allCodes = []; showLogin(text || '', text ? 'error' : null);
  }

  function attemptLogin(candidate) {
    if (!candidate) { msg('login-msg', '请输入管理员令牌。', 'error'); return; }
    var btn = $('login-btn'); btn.disabled = true; msg('login-msg', '正在校验…', 'ok');
    token = candidate;
    request('api/admin/stats').then(function () {
      saveToken(candidate); btn.disabled = false; msg('login-msg', '');
      showApp();
    }).catch(function (e) {
      btn.disabled = false; token = '';
      if (e instanceof AuthError) msg('login-msg', '令牌无效，请检查后重试。', 'error');
      else msg('login-msg', e.message || '校验失败，请重试。', 'error');
    });
  }

  // ---- overview ----
  function kindLine(k) { return k ? '已兑换 ' + k.redeemed + ' · 未兑换 ' + k.pending : '—'; }
  function renderEarlyBird(e) {
    if (!e) { $('stat-early-sold').textContent = '—'; $('stat-early-sub').textContent = '暂时无法读取早鸟进度'; return; }
    $('stat-early-sold').textContent = '已售 ' + e.sold;
    $('stat-early-sub').textContent = e.early_bird_active
      ? '当前第 ' + e.current_tier + ' 档，剩 ' + e.remaining + ' 个名额 · ' + yuan(e.current_price_cny) + '/月'
      : '早鸟名额已满，恢复标准价 ' + yuan(e.standard_price_cny) + '/月';
  }
  function renderStats(s) {
    $('stat-total').textContent = s.total;
    $('stat-redeemed').textContent = s.redeemed;
    $('stat-pending').textContent = s.pending;
    var pct = s.total > 0 ? Math.round((s.redeemed / s.total) * 100) : 0;
    $('usage-fill').style.width = pct + '%';
    $('usage-label').textContent = '兑换率 ' + pct + '%';
    var kinds = s.kinds || {};
    $('stat-formal-total').textContent = kinds.formal ? kinds.formal.total : '—';
    $('stat-formal-sub').textContent = kindLine(kinds.formal);
    $('stat-test-total').textContent = kinds.test ? kinds.test.total : '—';
    $('stat-test-sub').textContent = kindLine(kinds.test);
    var other = kinds.other;
    $('stat-other').hidden = !(other && other.total > 0);
    $('stat-other').textContent = other && other.total > 0
      ? '另有其他产品的兑换码 ' + other.total + ' 个（不区分正式 / 测试），已计入上方总数。' : '';
    renderEarlyBird(s.early_bird);
  }
  function renderToday() {
    var today = sh(Date.now()), nNew = 0, nRed = 0;
    allCodes.forEach(function (c) {
      if (c.created_at && sh(c.created_at) === today) nNew++;
      if (c.redeemed_at && sh(c.redeemed_at) === today) nRed++;
    });
    $('stat-today-new').textContent = nNew;
    $('stat-today-redeemed').textContent = nRed;
  }
  function loadStats() {
    return request('api/admin/stats').then(renderStats).catch(function (e) { handleError(e); });
  }
  function loadDistribution() {
    request('api/distribution/stats').then(function (d) {
      $('dist-referrals').textContent = (d.total_referrals != null ? d.total_referrals : 0);
      $('dist-total').textContent = money(d.total_commission);
      $('dist-pending').textContent = money(d.pending_commission);
    }).catch(function (e) { if (!handleError(e)) { $('dist-referrals').textContent = '—'; } });
    request('api/distribution/list').then(renderDistTable).catch(function (e) {
      if (!handleError(e)) setState('dist-body', 4, e.message || '加载失败', true);
    });
  }

  // ---- codes ----
  var CODE_COLS = 9;
  function setState(bodyId, cols, text, isError) {
    var body = $(bodyId);
    body.innerHTML = '';
    var tr = document.createElement('tr');
    var td = document.createElement('td');
    td.colSpan = cols; td.className = 'state-row' + (isError ? ' error' : '');
    td.textContent = text; tr.appendChild(td); body.appendChild(tr);
  }
  function cell(text, cls) {
    var td = document.createElement('td'); if (cls) td.className = cls;
    td.textContent = text == null ? '' : text; return td;
  }
  function badge(ok) {
    var td = document.createElement('td'); var b = document.createElement('span');
    b.className = 'badge ' + (ok ? 'ok' : 'pending'); b.textContent = ok ? '已兑换' : '未兑换';
    td.appendChild(b); return td;
  }
  function kindBadge(c) {
    var td = document.createElement('td'); var b = document.createElement('span');
    if (!c.kind_applies) { b.className = 'badge kind-na'; b.textContent = '不区分'; }
    else if (c.code_kind === 'formal') { b.className = 'badge kind-formal'; b.textContent = '正式'; }
    else { b.className = 'badge kind-test'; b.textContent = '测试'; }
    td.appendChild(b); return td;
  }
  function filteredCodes() {
    return allCodes.filter(function (c) {
      if (codeFilter === 'redeemed' && !c.redeemed_at) return false;
      if (codeFilter === 'pending' && c.redeemed_at) return false;
      if (kindFilter !== 'all' && !(c.kind_applies && c.code_kind === kindFilter)) return false;
      if (noteFilter && String(c.admin_note || '').toLowerCase().indexOf(noteFilter) === -1) return false;
      return true;
    });
  }
  // 权益配置列：到期方式与总次数。测试码可设固定截止/总次数；其余一律沿用原套餐规则。
  function benefitText(c) {
    var parts = [];
    if (c.benefit_expires_at) parts.push('固定截止 ' + fmtTime(c.benefit_expires_at));
    if (c.benefit_total_calls != null) {
      var total = c.benefit_total_calls;
      parts.push(c.redeemed_at && c.remaining_total != null
        ? '总次数 ' + total + ' · 剩 ' + c.remaining_total
        : '总次数 ' + total);
    }
    return parts.length ? parts.join('；') : '原套餐规则';
  }
  function editNote(c) {
    var current = c.admin_note || '';
    var next = window.prompt('编辑备注（仅管理员可见，500 字符内；留空则清除备注）：', current);
    if (next === null) return;
    if (next.length > 500) { toast('备注不能超过 500 字符'); return; }
    request('api/admin/edit_note', {
      method: 'POST',
      body: JSON.stringify({ code_hash: c.code_hash, note: next })
    }).then(function () {
      toast('备注已更新');
      loadCodes();
    }).catch(function (e) { if (!handleError(e)) toast(e.message || '备注修改失败'); });
  }
  function noteCell(c) {
    var td = document.createElement('td'); td.className = 'note-cell';
    var text = document.createElement('span');
    text.textContent = c.admin_note || '—';
    td.appendChild(text);
    if (c.code_kind === 'test') {
      var btn = document.createElement('button');
      btn.type = 'button'; btn.className = 'btn btn-ghost btn-sm';
      btn.textContent = c.admin_note ? '改备注' : '加备注';
      btn.addEventListener('click', function () { editNote(c); });
      td.appendChild(btn);
    }
    return td;
  }
  function shortCode(c) { var s = c.code_plain || c.code_hash || ''; return s.length > 15 ? s.slice(0, 15) + '…' : s; }
  function deleteConfirmText(c) {
    if (!c.kind_applies) return '确定删除这个兑换码吗？删除后无法恢复。';
    var text = '确定删除测试码 ' + shortCode(c) + ' 吗？删除后无法恢复。';
    if (c.delete_revokes_key) text += '\n\n该码已兑换，对应的 key 会同时作废，之后用这把 key 的调用都会被拒绝。';
    return text;
  }
  function deleteCode(c, btn) {
    if (!confirm(deleteConfirmText(c))) return;
    btn.disabled = true;
    request('api/admin/delete_code', {
      method: 'POST',
      body: JSON.stringify({ code_hash: c.code_hash })
    }).then(function (d) {
      toast(d && d.key_revoked ? '已删除，对应的 key 已作废' : '删除成功');
      loadStats(); loadCodes();
    }).catch(function (e) {
      btn.disabled = false;
      if (!handleError(e)) toast(e.message || '删除失败');
    });
  }
  function renderCodes() {
    var rows = filteredCodes();
    var body = $('codes-body'); body.innerHTML = '';
    if (!rows.length) { setState('codes-body', CODE_COLS, '暂无符合条件的兑换码'); return; }
    rows.forEach(function (c) {
      var tr = document.createElement('tr');
      // 第一列：完整兑换码 + 复制按钮
      var codeCell = document.createElement('td');
      codeCell.className = 'mono';
      var codeText = document.createElement('div');
      codeText.style.fontSize = '12px';
      codeText.style.wordBreak = 'break-all';
      codeText.textContent = c.code_plain || (c.code_hash ? c.code_hash.slice(0, 18) + '…' : '—');
      var copyBtn = document.createElement('button');
      copyBtn.className = 'btn btn-ghost btn-sm';
      copyBtn.style.marginTop = '4px';
      copyBtn.textContent = '复制';
      copyBtn.onclick = function() {
        var code = c.code_plain || c.code_hash;
        navigator.clipboard.writeText(code).then(function() {
          toast('已复制到剪贴板');
        }).catch(function() {
          // 兜底
          var ta = document.createElement('textarea');
          ta.value = code;
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          toast('已复制到剪贴板');
        });
      };
      codeCell.appendChild(codeText);
      codeCell.appendChild(copyBtn);
      tr.appendChild(codeCell);
      tr.appendChild(kindBadge(c));
      tr.appendChild(cell(c.plan || '—', 'mono'));
      tr.appendChild(cell(benefitText(c), 'benefit-cell'));
      tr.appendChild(cell(fmtTime(c.created_at), 'mono'));
      tr.appendChild(badge(!!c.redeemed_at));
      tr.appendChild(cell(c.redeemed_at ? fmtTime(c.redeemed_at) : '—', 'mono'));
      tr.appendChild(noteCell(c));
      // 最后一列：服务端判定可删的才有删除按钮；正式码永远没有。
      var actionCell = document.createElement('td');
      if (c.deletable) {
        var delBtn = document.createElement('button');
        delBtn.type = 'button';
        delBtn.className = 'btn btn-ghost btn-sm btn-danger-text';
        delBtn.textContent = '删除';
        delBtn.addEventListener('click', function () { deleteCode(c, delBtn); });
        actionCell.appendChild(delBtn);
      } else {
        var note = document.createElement('span');
        note.className = 'dim';
        note.textContent = c.kind_applies && c.code_kind === 'formal' ? '不可删除' : '—';
        actionCell.appendChild(note);
      }
      tr.appendChild(actionCell);
      body.appendChild(tr);
    });
  }
  function loadCodes() {
    setState('codes-body', CODE_COLS, '加载中…');
    return request('api/admin/codes?limit=200').then(function (d) {
      allCodes = Array.isArray(d.codes) ? d.codes : [];
      renderCodes(); renderToday();
    }).catch(function (e) { if (!handleError(e)) setState('codes-body', CODE_COLS, e.message || '加载失败', true); });
  }
  function readBenefits(kind) {
    // 返回 {payload, error}：三个可选项都只做静态校验，真正的判定在服务端。
    var out = {};
    var expires = $('gen-expires').value;
    var total = $('gen-total').value.trim();
    var note = $('gen-note').value;
    if (kind !== 'test' && (expires || total || note.trim())) {
      return { error: '固定截止、总次数和备注仅测试码可设；正式码请留空。' };
    }
    if (kind !== 'test') return { payload: out };
    if (expires) {
      // datetime-local 给出 'YYYY-MM-DDTHH:MM'（分钟精度），按北京时间解释。
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(expires) || isNaN(new Date(expires).getTime())) {
        return { error: '固定截止时间无效，请用日期时间选择器填写（北京时间）。' };
      }
      out.expires_at = expires;
    }
    if (total) {
      if (!/^\d+$/.test(total) || parseInt(total, 10) < 1) {
        return { error: '总调用次数必须是正整数（指 MCP 业务工具调用次数）。' };
      }
      out.total_calls = parseInt(total, 10);
    }
    if (note.trim()) {
      if (note.length > 500) return { error: '备注不能超过 500 字符。' };
      out.note = note;
    }
    return { payload: out };
  }
  function generate() {
    var count = parseInt($('gen-count').value, 10);
    var plan = $('gen-plan').value;
    var kind = $('gen-kind').value;
    if (!(count >= 1 && count <= 100)) { msg('gen-msg', '数量需在 1–100 之间。', 'error'); return; }
    if (kind !== 'test' && kind !== 'formal') { msg('gen-msg', '请选择兑换码类别。', 'error'); return; }
    var benefits = readBenefits(kind);
    if (benefits.error) { msg('gen-msg', benefits.error, 'error'); return; }
    if (kind === 'formal' && !confirm('正式码生成后不能删除，将计入早鸟名额（兑换成功时计入）。\n\n确定生成 ' + count + ' 个正式码吗？')) {
      msg('gen-msg', '已取消，没有生成正式码。', 'ok'); return;
    }
    var summary = [];
    if (benefits.payload.expires_at) summary.push('固定截止 ' + benefits.payload.expires_at.replace('T', ' '));
    if (benefits.payload.total_calls != null) summary.push('总次数 ' + benefits.payload.total_calls);
    if (benefits.payload.note) summary.push('已写备注');
    var btn = $('gen-btn'); btn.disabled = true; msg('gen-msg', '生成中…', 'ok');
    request('api/admin/generate', {
      method: 'POST',
      body: JSON.stringify({ count: count, plan: plan, kind: kind,
                             expires_at: benefits.payload.expires_at,
                             total_calls: benefits.payload.total_calls,
                             note: benefits.payload.note })
    }).then(function (d) {
      btn.disabled = false;
      var codes = Array.isArray(d.codes) ? d.codes : [];
      msg('gen-msg', '成功生成 ' + codes.length + ' 个' + (kind === 'formal' ? '正式' : '测试') + '兑换码'
          + (summary.length ? '（' + summary.join('，') + '）' : '') + '。新码已出现在下方列表中。', 'ok');
      $('gen-kind').value = 'test';  // 每次生成后回到默认的测试码，防手滑
      loadStats(); loadCodes();
    }).catch(function (e) { btn.disabled = false; handleError(e, 'gen-msg'); });
  }
  function prefillFan5() {
    // 只预填，不提交、不填日期、不批量：数量保持管理员自己的选择。
    $('gen-kind').value = 'test';
    $('gen-total').value = '5';
    msg('gen-msg', '已预填「测试码 + 总调用 5 次」。固定截止与备注请按需填写，确认后手动点「生成兑换码」。', 'ok');
    $('gen-expires').focus();
  }
  function renderGenerated(codes) {
    var box = $('gen-out'); var list = $('gen-list'); list.innerHTML = '';
    if (!codes.length) { box.hidden = true; return; }
    box.hidden = false;
    $('gen-copy-all').setAttribute('data-codes', codes.join('\n'));
    codes.forEach(function (code) {
      var row = document.createElement('div'); row.className = 'code-item';
      var span = document.createElement('span'); span.textContent = code; row.appendChild(span);
      var b = document.createElement('button'); b.type = 'button'; b.className = 'icon-btn';
      b.textContent = '复制';
      b.addEventListener('click', function () { copy(code, '兑换码已复制'); });
      row.appendChild(b); list.appendChild(row);
    });
  }
  function copy(text, okText) {
    function fallback() { window.prompt('自动复制不可用，请手动复制：', text); }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(okText || '已复制'); }, fallback);
    } else fallback();
  }

  // ---- distribution table ----
  function pick(obj, keys) { for (var i = 0; i < keys.length; i++) if (obj[keys[i]] != null && obj[keys[i]] !== '') return obj[keys[i]]; return null; }
  function renderDistTable(records) {
    var list = Array.isArray(records) ? records : (records && records.records) || [];
    var body = $('dist-body'); body.innerHTML = '';
    if (!list.length) { setState('dist-body', 4, '暂无分销记录'); return; }
    list.forEach(function (r) {
      var tr = document.createElement('tr');
      tr.appendChild(cell(pick(r, ['wechat_id', 'wechat', 'referrer', 'referrer_wechat']) || '—', 'mono'));
      tr.appendChild(cell(fmtTime(pick(r, ['created_at', 'referred_at', 'time'])), 'mono'));
      var redeemed = pick(r, ['redeemed', 'is_redeemed', 'redeemed_at', 'status']);
      var ok = redeemed === true || redeemed === 1 || redeemed === '已兑换' || redeemed === 'redeemed' || (typeof redeemed === 'string' && /^\d{4}-/.test(redeemed));
      tr.appendChild(badge(ok));
      var comm = pick(r, ['commission', 'commission_amount', 'amount']);
      tr.appendChild(cell(comm != null ? money(comm) : '—', 'mono'));
      body.appendChild(tr);
    });
  }

  function refreshAll() { loadStats().then(loadCodes).then(loadDistribution); }

  function wireChips(attr, onPick) {
    var chips = document.querySelectorAll('.chip-btn[' + attr + ']');
    Array.prototype.forEach.call(chips, function (btn) {
      btn.addEventListener('click', function () {
        Array.prototype.forEach.call(chips, function (b) { b.classList.remove('on'); });
        this.classList.add('on'); onPick(this.getAttribute(attr)); renderCodes();
      });
    });
  }

  // ---- wire up ----
  function init() {
    // plans
    var sel = $('gen-plan');
    PLANS.forEach(function (p) { var o = document.createElement('option'); o.value = p; o.textContent = p; sel.appendChild(o); });
    $('gen-kind').value = 'test';  // 浏览器可能恢复上次的选择；每次打开都从测试码开始

    $('login-btn').addEventListener('click', function () { attemptLogin($('token-input').value.trim()); });
    $('token-input').addEventListener('keydown', function (e) { if (e.key === 'Enter') attemptLogin(this.value.trim()); });
    $('logout-btn').addEventListener('click', function () { logout(); });
    $('refresh-btn').addEventListener('click', refreshAll);
    $('gen-btn').addEventListener('click', generate);
    $('gen-fan5').addEventListener('click', prefillFan5);
    $('codes-refresh').addEventListener('click', loadCodes);
    $('dist-refresh').addEventListener('click', loadDistribution);
    $('note-filter').addEventListener('input', function () {
      noteFilter = this.value.trim().toLowerCase(); renderCodes();
    });
    $('gen-copy-all').addEventListener('click', function () {
      var all = this.getAttribute('data-codes') || ''; if (all) copy(all, '已复制全部兑换码');
    });
    // 状态筛选（全部 / 未兑换 / 已兑换）与类别筛选（全部类别 / 正式 / 测试）同时生效。
    wireChips('data-filter', function (v) { codeFilter = v; });
    wireChips('data-kind', function (v) { kindFilter = v; });

    var saved = readToken();
    if (saved) { token = saved; request('api/admin/stats').then(function () { showApp(); }).catch(function () { logout(); }); }
    else showLogin();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
