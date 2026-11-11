let selectedTool = null;

function selectTool(el) {
  document.querySelectorAll('.tool-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');

  selectedTool = {
    code: el.dataset.code,
    name: el.dataset.name,
    platform: el.dataset.platform,
    tier: el.dataset.tier,
    cost: el.dataset.cost,
    desc: el.dataset.desc
  };

  document.getElementById('active-tool-title').innerText = `[${selectedTool.platform}] ${selectedTool.name}`;
  document.getElementById('active-tool-desc').innerText = selectedTool.desc;

  const badge = document.getElementById('active-tool-badge');
  if (selectedTool.tier === 'pro') {
    badge.className = 'badge badge-pro';
    badge.innerText = `PRO (${selectedTool.cost} KREDİ)`;
  } else {
    badge.className = 'badge badge-free';
    badge.innerText = 'ÜCRETSİZ (0 KREDİ)';
  }
}

async function executeQuery(e) {
  e.preventDefault();
  if (!selectedTool) {
    alert('Lütfen sol listeden bir istihbarat modülü seçin.');
    return;
  }
  const target = document.getElementById('target-input').value.trim();
  if (!target) return;

  const output = document.getElementById('terminal-output');
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.innerText = 'SORGULANIYOR...';
  output.style.color = '#94a3b8';
  output.innerText = `[*] OSINTCORE Engine v2.4 başlatıldı...\n[*] Modül: ${selectedTool.name}\n[*] Hedef: ${target}\n[*] Açık kaynak uç noktaları taranıyor...`;

  try {
    const res = await fetch('/api/run-tool', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool_code: selectedTool.code, target: target })
    });
    const json = await res.json();

    if (!json.ok) {
      output.style.color = '#f87171';
      output.innerText = `[!] HATA: ${json.error}`;
      if (json.upgrade_required) {
        output.innerText += '\n[i] PRO modülleri açmak için üst menüden "Paketler" sayfasına gidin.';
      }
    } else {
      output.style.color = '#34d399';
      output.innerText = `[+] İSTİHBARAT RAPORU TAMAMLANDI (${json.tool})\n` +
        `[+] Kalan Kredi: ${json.remaining_credits}\n` +
        `------------------------------------------------------------\n` +
        JSON.stringify(json.data, null, 2);

      const creditEl = document.getElementById('user-credits');
      if (creditEl) creditEl.innerText = json.remaining_credits;
    }
  } catch (err) {
    output.style.color = '#f87171';
    output.innerText = `[!] Ağ bağlantı hatası: ${err.message}`;
  } finally {
    btn.disabled = false;
    btn.innerText = 'İSTİHBARAT ÇEK';
  }
}

window.addEventListener('DOMContentLoaded', () => {
  const firstTool = document.querySelector('.tool-item');
  if (firstTool) selectTool(firstTool);
});
