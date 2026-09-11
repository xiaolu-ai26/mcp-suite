'use strict';
const form = document.getElementById('redeem-form');
let keyInMemory = '';
if (form) {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = document.getElementById('submit');
    const error = document.getElementById('error');
    button.disabled = true;
    button.textContent = '正在兑换…';
    error.textContent = '';
    try {
      const response = await fetch('./redeem', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({code: document.getElementById('code').value.trim()})
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || '兑换失败，请稍后重试。');
      keyInMemory = data.api_key;
      document.getElementById('api-key').value = keyInMemory;
      document.getElementById('mcp-url').value = data.mcp_url;
      document.getElementById('remaining').textContent = `${data.remaining_today} 次`;
      document.getElementById('code').value = '';
      document.getElementById('redeem-panel').hidden = true;
      document.getElementById('result').hidden = false;
      document.getElementById('api-key').focus();
    } catch (err) {
      error.textContent = err instanceof TypeError ? '网络异常，暂未收到兑换结果。请保留兑换码并联系卖家核实，避免丢失 key。' : err.message;
    } finally {
      button.disabled = false;
      button.textContent = '兑换并生成 API key';
    }
  });
  document.getElementById('copy-key').addEventListener('click', async () => {
    const status = document.getElementById('copy-status');
    try {
      await navigator.clipboard.writeText(keyInMemory);
      status.textContent = '已复制，请保存到你自己的密码管理器。';
    } catch (_) {
      document.getElementById('api-key').select();
      status.textContent = '请手动复制上方已选中的 API key。';
    }
  });
}
