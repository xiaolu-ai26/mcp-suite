/* 秋招岗位库 · 管理后台交互。CSP 安全：无内联脚本、无 eval、无第三方库；全部 addEventListener。
 * API 路径相对当前文档解析：页面在 /qiuzhao/admin，./api/... 自动解析到 /qiuzhao/api/...。
 * Token 只存 sessionStorage（随标签页关闭清除），仅用于 Authorization 请求头，绝不写入 URL、日志或页面。 */
(function () {
  'use strict';
  var TOKEN_KEY = 'qz_admin_token';
  var PLANS = ['qiuzhao-2026'];
  var token = '';
  var allCodes = [];
  var codeFilter = 'all';

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

  function request(path) {
    return fetch(api(path), {
      headers: { 'Authorization': 'Bearer ' + token },
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
  function renderStats(s) {
    $('stat-total').textContent = s.total; 
    $('stat-redeemed').textContent = s.redeemed;
    $('stat-pending').textContent = s.pending;
    var pct = s.total > 0 ? Math.round((s.redeemed / s.total) * 100) : 0;
    $('usage-fill').style.width = pct + '%';
    $('usage-label').textContent = '兑换率 ' + pct + '%';
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
  function filteredCodes() {
    return allCodes.filter(function (c) {
      if (codeFilter === 'redeemed') return !!c.redeemed_at;
      if (codeFilter === 'pending') return !c.redeemed_at;
      return true;
    });
  }
  function renderCodes() {
    var rows = filteredCodes();
    var body = $('codes-body'); body.innerHTML = '';
    if (!rows.length) { setState('codes-body', 6, '暂无符合条件的兑换码'); return; }
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
      tr.appendChild(cell(c.plan || '—', 'mono'));
      tr.appendChild(cell(fmtTime(c.created_at), 'mono'));
      tr.appendChild(badge(!!c.redeemed_at));
      tr.appendChild(cell(c.redeemed_at ? fmtTime(c.redeemed_at) : '—', 'mono'));
      // 第六列：删除按钮
      var actionCell = document.createElement('td');
      if (!c.redeemed_at) {
        var delBtn = document.createElement('button');
        delBtn.className = 'btn btn-ghost btn-sm';
        delBtn.style.color = '#ff4d4f';
        delBtn.textContent = '删除';
        delBtn.onclick = function() {
          if (confirm('确定删除这个兑换码吗？删除后无法恢复。')) {
            request('api/admin/delete_code', {
              method: 'POST',
              body: JSON.stringify({ code_hash: c.code_hash })
            }).then(function() {
              toast('删除成功');
              loadCodes();
            }).catch(function(e) {
              toast(e.message || '删除失败');
            });
          }
        };
        actionCell.appendChild(delBtn);
      } else {
        actionCell.textContent = '—';
      }
      tr.appendChild(actionCell);
      body.appendChild(tr);
    });
  }
  function loadCodes() {
    setState('codes-body', 6, '加载中…');
    return request('api/admin/codes?limit=200').then(function (d) {
      allCodes = Array.isArray(d.codes) ? d.codes : [];
      renderCodes(); renderToday();
    }).catch(function (e) { if (!handleError(e)) setState('codes-body', 6, e.message || '加载失败', true); });
  }
  function generate() {
    var count = parseInt($('gen-count').value, 10);
    var plan = $('gen-plan').value;
    if (!(count >= 1 && count <= 100)) { msg('gen-msg', '数量需在 1–100 之间。', 'error'); return; }
    var btn = $('gen-btn'); btn.disabled = true; msg('gen-msg', '生成中…', 'ok');
    request('api/admin/generate?count=' + count + '&plan=' + encodeURIComponent(plan)).then(function (d) {
      btn.disabled = false;
      var codes = Array.isArray(d.codes) ? d.codes : [];
      msg('gen-msg', '成功生成 ' + codes.length + ' 个兑换码。新码已出现在下方列表中。', 'ok');
      loadStats(); loadCodes();
    }).catch(function (e) { btn.disabled = false; handleError(e, 'gen-msg'); });
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

  // ---- wire up ----
  function init() {
    // plans
    var sel = $('gen-plan');
    PLANS.forEach(function (p) { var o = document.createElement('option'); o.value = p; o.textContent = p; sel.appendChild(o); });

    $('login-btn').addEventListener('click', function () { attemptLogin($('token-input').value.trim()); });
    $('token-input').addEventListener('keydown', function (e) { if (e.key === 'Enter') attemptLogin(this.value.trim()); });
    $('logout-btn').addEventListener('click', function () { logout(); });
    $('refresh-btn').addEventListener('click', refreshAll);
    $('gen-btn').addEventListener('click', generate);
    $('codes-refresh').addEventListener('click', loadCodes);
    $('dist-refresh').addEventListener('click', loadDistribution);
    $('gen-copy-all').addEventListener('click', function () {
      var all = this.getAttribute('data-codes') || ''; if (all) copy(all, '已复制全部兑换码');
    });
    Array.prototype.forEach.call(document.querySelectorAll('.chip-btn[data-filter]'), function (btn) {
      btn.addEventListener('click', function () {
        codeFilter = this.getAttribute('data-filter');
        Array.prototype.forEach.call(document.querySelectorAll('.chip-btn[data-filter]'), function (b) { b.classList.remove('on'); });
        this.classList.add('on'); renderCodes();
      });
    });

    var saved = readToken();
    if (saved) { token = saved; request('api/admin/stats').then(function () { showApp(); }).catch(function () { logout(); }); }
    else showLogin();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
