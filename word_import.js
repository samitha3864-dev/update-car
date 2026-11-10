let file = null;
let preview = [];
const $ = id => document.getElementById(id);

$('wordFile').addEventListener('change', event => {
  file = event.target.files && event.target.files[0] ? event.target.files[0] : null;
  $('previewWord').disabled = !file;
  $('previewSection').hidden = true;
  preview = [];
});

$('previewWord').addEventListener('click', async () => {
  if (!file) return toast('Choose a Word file first.', 'error');
  const button = $('previewWord');
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = 'Reading Word...';
  try {
    const fd = new FormData();
    fd.append('file', file);
    const response = await fetch('/api/preview-word', { method: 'POST', body: fd });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || 'Could not read this Word file.');
    preview = Array.isArray(result.records) ? result.records : [];
    if (!preview.length) throw new Error('No customer rows found. Check the Word table headers and dates.');
    $('previewSection').hidden = false;
    $('previewSummary').textContent = `${preview.length} record(s) found in ${file.name}. Review the rows, then import selected data.`;
    $('wordPreviewBody').innerHTML = preview.map((record, index) => {
      const products = Array.isArray(record.products) ? record.products : [];
      const productText = products.length
        ? products.map(item => `${esc(item.category || 'Other')} · ${esc(item.product)} × ${esc(item.quantity)}`).join('<br>')
        : '<em>No product columns found</em>';
      return `<tr><td><input class="row-check" data-i="${index}" type="checkbox" checked></td><td>${esc(record.date || '')}</td><td>${esc(record.name || 'Nil')}</td><td>${esc(record.mobile || 'Nil')}</td><td>${esc(record.vehicle || 'Nil')}</td><td class="product-text">${productText}</td><td>${money(record.total_amount)}</td></tr>`;
    }).join('');
    $('selectAll').checked = true;
    toast(`Preview ready: ${preview.length} record(s).`);
  } catch (error) {
    $('previewSection').hidden = true;
    toast(error.message || 'Word preview failed.', 'error');
  } finally {
    button.disabled = !file;
    button.textContent = oldText;
  }
});

$('selectAll').addEventListener('change', () => {
  document.querySelectorAll('.row-check').forEach(input => { input.checked = $('selectAll').checked; });
});

$('wordPreviewBody').addEventListener('change', event => {
  if (!event.target.classList.contains('row-check')) return;
  const boxes = [...document.querySelectorAll('.row-check')];
  $('selectAll').checked = boxes.length > 0 && boxes.every(input => input.checked);
});

$('importWord').addEventListener('click', async () => {
  const chosen = preview.filter((_, index) => document.querySelector(`.row-check[data-i="${index}"]`)?.checked);
  if (!chosen.length) return toast('Select at least one row to import.', 'error');
  const button = $('importWord');
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = `Importing ${chosen.length} record(s)...`;
  try {
    const response = await fetch('/api/import-excel-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ records: chosen })
    });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || 'Word import failed while saving.');
    toast(result.message || 'Word data imported successfully.');
    $('previewSummary').textContent = result.message || 'Import completed.';
    // Keep preview visible briefly so the user can see the confirmed result.
    setTimeout(() => { window.location.href = '/dashboard'; }, 900);
  } catch (error) {
    toast(error.message || 'Word import failed.', 'error');
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
});
