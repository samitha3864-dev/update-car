let data = { categories: [], products: {} };
let selectedCategory = '';
let selected = [];
let detectTimer = null;
let detectedCategoryForInput = '';
const $ = id => document.getElementById(id);

async function api(url, method='GET', payload) {
  const response = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: payload ? JSON.stringify(payload) : undefined
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || 'Request failed.');
  return result;
}
function normalized(value) { return String(value || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase(); }
const categoryPalette = {'seat cover':['#fff1f2','#be123c'],'floor mat / mat':['#ecfdf5','#047857'],'rubber coating':['#f5f3ff','#7c3aed'],'interior rubber coating':['#e0f2fe','#0369a1'],'steering cover':['#ffe4e6','#9f1239'],'sunfilm':['#fef3c7','#a16207'],'door visor':['#e0e7ff','#4338ca'],'wheel cup':['#ccfbf1','#0f766e'],'mud flap':['#fce7f3','#9d174d'],'skin / sponge / foamcoat':['#ecfccb','#4d7c0f'],'anti chikmat / perfume':['#f3e8ff','#6d28d9'],'horn':['#ffedd5','#c2410c'],'fog lamp':['#dbeafe','#1d4ed8'],'cleaning / interior-exterior service':['#e2e8f0','#475569'],'other':['#f1f5f9','#334155']};
function categoryStyle(category) { const pair = categoryPalette[normalized(category)] || ['#f8fafc','#475569']; return `background:${pair[0]};border-color:${pair[1]}55;color:${pair[1]};`; }
function findSavedProduct(name) {
  const key = normalized(name);
  for (const category of data.categories) {
    const products = data.products[category] || [];
    const match = products.find(p => normalized(p) === key);
    if (match) return { category, product: match };
  }
  return null;
}
async function load() {
  data = await api('/api/data');
  const now = new Date();
  $('entryDate').value = `${String(now.getDate()).padStart(2,'0')}-${String(now.getMonth()+1).padStart(2,'0')}-${now.getFullYear()}`;
  if (!selectedCategory || !data.categories.includes(selectedCategory)) selectedCategory = data.categories[0] || '';
  renderCategories(); renderProducts(); updateSelected();
}
function renderCategories() { renderCategoryOptionsOnly(); }

function productsForCategory(category) {
  const exact = data.products && data.products[category];
  if (Array.isArray(exact)) return exact;
  const key = Object.keys(data.products || {}).find(k => normalized(k) === normalized(category));
  return key && Array.isArray(data.products[key]) ? data.products[key] : [];
}
function renderProducts() {
  const q = $('productSearch').value.trim();
  const exact = q ? findSavedProduct(q) : null;
  if (exact) selectedCategory = exact.category;
  else if (q && detectedCategoryForInput && data.categories.some(c => normalized(c) === normalized(detectedCategoryForInput))) selectedCategory = data.categories.find(c => normalized(c) === normalized(detectedCategoryForInput));
  renderCategoryOptionsOnly();
  const list = $('productList');
  const categoryProducts = productsForCategory(selectedCategory);
  const countLabel = $('categoryProductsLabel'); if (countLabel) countLabel.textContent = `${selectedCategory || 'Selected'} — ${categoryProducts.length} product${categoryProducts.length === 1 ? '' : 's'}`;
  const visibleProducts = categoryProducts.filter(product => !q || normalized(product).includes(normalized(q)));
  list.innerHTML = visibleProducts.map(product => `<button type="button" class="product-chip" style="${categoryStyle(selectedCategory)}" data-product="${esc(product)}">＋ ${esc(product)}</button>`).join('');
  list.querySelectorAll('[data-product]').forEach(button => button.addEventListener('click', () => addProduct(button.dataset.product, selectedCategory)));
  if (!visibleProducts.length) list.innerHTML = `<p class="hint">${categoryProducts.length ? 'No products match your search. Clear the search box to view all products.' : 'No products saved in this category yet. Add a product below to build this category list.'}</p>`;

  if (exact) {
    detectedCategoryForInput = exact.category;
    $('newProductBox').hidden = true;
    $('productHint').textContent = `Category detected: ${exact.category}. Press Enter to add.`;
  } else if (q && detectedCategoryForInput) {
    $('newProductBox').hidden = true;
    $('productHint').textContent = `Category detected automatically: ${detectedCategoryForInput}. Press Enter to add this product.`;
  } else if (q) {
    $('newProductBox').hidden = false;
    $('newProductText').textContent = `Category not recognized for “${q}”. Choose the correct category once; the site will save it for next time.`;
    const categorySelect = $('newProductCategory');
    const previous = selectedCategory;
    categorySelect.innerHTML = data.categories.map(c => `<option value="${esc(c)}">${esc(c)}</option>`).join('');
    categorySelect.value = data.categories.find(c => normalized(c) === normalized(previous)) || data.categories[0] || '';
    $('productHint').textContent = 'Type a product name. The detected category appears above; no product search is needed.';
  } else {
    detectedCategoryForInput = '';
    $('newProductBox').hidden = true;
    $('productHint').textContent = 'Choose a category to view every product, or type to search the catalogue.';
  }
}
function renderCategoryOptionsOnly() {
  const s = $('categorySelect');
  s.innerHTML = data.categories.map(c => `<option value="${esc(c)}" ${normalized(c) === normalized(selectedCategory) ? 'selected' : ''}>${esc(c)}</option>`).join('');
  s.onchange = () => { selectedCategory = s.value; $('productSearch').value = ''; detectedCategoryForInput = ''; renderProducts(); };
}

function addProduct(product, category) {
  const existing = selected.find(x => normalized(x.category) === normalized(category) && normalized(x.product) === normalized(product));
  if (existing) existing.quantity++;
  else selected.push({ category, product, quantity: 1 });
  updateSelected();
}
async function addNewProductToCategory(product, category) {
  const saved = findSavedProduct(product);
  if (saved) {
    selectedCategory = saved.category; renderCategories(); addProduct(saved.product, saved.category);
    $('productSearch').value = ''; detectedCategoryForInput = ''; renderProducts(); return;
  }
  const result = await api('/api/product', 'POST', { category, product });
  data = result.data; selectedCategory = category; renderCategories();
  const exact = findSavedProduct(product);
  addProduct(exact ? exact.product : product, category);
  $('productSearch').value = ''; detectedCategoryForInput = ''; renderProducts();
  toast(`“${product}” saved under ${category}. Next time its category will be recognized.`);
}
async function chooseCategoryAndAdd(product) {
  const categories = data.categories;
  if (!product || !categories.length) return;
  const menu = categories.map((c, i) => `${i + 1}. ${c}`).join('\n');
  const answer = prompt(`Choose category for “${product}”.\nType the category name OR its number:\n\n${menu}`);
  if (answer === null || !answer.trim()) return;
  const raw = answer.trim(), index = Number(raw) - 1;
  const category = (Number.isInteger(index) && index >= 0 && index < categories.length)
    ? categories[index] : categories.find(c => normalized(c) === normalized(raw));
  if (!category) { toast(`Category not found: ${raw}. No product added.`, 'error'); return; }
  try { await addNewProductToCategory(product, category); }
  catch (e) { toast(e.message, 'error'); }
}
function parseBulkProductLine(line) {
  let value = String(line || '').trim();
  // Remove list numbering such as "4." or "5)" without treating it as quantity.
  const hadListNumber = /^\s*(?:[-*•]+\s*)?(?:\d+|[A-Za-z]|[०-९]+)\s*[.)]\s*/u.test(value);
  value = value.replace(/^\s*(?:[-*•]+\s*)?(?:\d+|[A-Za-z]|[०-९]+)\s*[.)]\s*/u, '').trim();
  if (!value) return null;

  let quantity = 1;
  let amount = null;

  // A leading bare number ("2 Floor Mat 3000") is the quantity.
  const leadingQty = value.match(/^(\d{1,3})\s+(.+)$/);
  if (leadingQty && Number(leadingQty[1]) > 0) {
    quantity = Number(leadingQty[1]);
    value = leadingQty[2].trim();
  }

  // Strip the final amount only when there is another numeric token in the line,
  // a leading quantity, or a currency marker. This preserves model numbers like 2032.
  const hasCurrency = /(?:₹|\brs\.?\s*)\s*\d/i.test(value);
  const amountMatch = value.match(/\s+(?:₹\s*|rs\.?\s*)?([\d,]+(?:\.\d{1,2})?)\s*$/i);
  if (amountMatch) {
    const beforeAmount = value.slice(0, amountMatch.index).trim();
    const numsBefore = beforeAmount.match(/\d+/g) || [];
    const trailingAmount = Number(amountMatch[1].replace(/,/g, ''));
    const knownPrefix = beforeAmount && !!resolveCatalogProduct(beforeAmount);
    const looksLikeAmount = hadListNumber || quantity !== 1 || numsBefore.length > 0 || hasCurrency || knownPrefix || trailingAmount >= 100;
    // Treat the final numeric token as the line amount; keep earlier model numbers (e.g. 2032).
    if (beforeAmount && looksLikeAmount) {
      amount = Number(amountMatch[1].replace(/,/g, ''));
      value = beforeAmount;
      // Some pasted lists place quantity after the name: "Side Film 1 3200".
      // Recognize only a short final number here, so model numbers like 2032 stay in the name.
      if (quantity === 1) {
        const trailingQty = value.match(/^(.*\S)\s+(\d{1,2})$/);
        if (trailingQty && (trailingQty[1].match(/\d+/g) || []).length === 0) {
          quantity = Number(trailingQty[2]) || 1;
          value = trailingQty[1].trim();
        }
      }
    }
  }

  // Handle explicit quantity forms such as "Seat Cover x2" / "Seat Cover qty 2".
  const explicitQty = value.match(/\s+(?:x|×|qty\s*[:=]?)\s*(\d+)\s*$/i);
  if (explicitQty) {
    quantity = Number(explicitQty[1]) || quantity;
    value = value.slice(0, explicitQty.index).trim();
  }
  return value ? { name: value, quantity: Math.max(1, quantity), amount } : null;
}

function resolveCatalogProduct(rawName) {
  const key = normalized(rawName).replace(/[^a-z0-9]+/g, ' ').trim();
  const compact = key.replace(/\s+/g, ' ');
  const aliases = [
    { test: /sunfilm.*side|side.*(?:ercdey|ceramic|shield)/i, category: 'Sunfilm', product: 'Side Ceramic Shield' },
    { test: /sunfilm.*front|front.*(?:cr+r?onty|ceramic|shield)|cr+r?onty|fronty|sunfiln.*cr+r?onty/i, category: 'Sunfilm', product: 'Front Ceramic Shield' },
    { test: /remote.*(?:rettery|battery)|(?:rettery|battery).*remote/i, category: 'accessories', product: 'remote battery' },
    { test: /key.*cove|cove.*key/i, category: 'accessories', product: 'key cover' },
    { test: /steer.*(?:cover|cove|eove|e?ovee)/i, category: 'Steering Cover', product: /leath|reath/i.test(rawName) ? 'steering cover leather' : 'Steering Cover' },
    { test: /name\s*sticker|namesticler/i, category: 'accessories', product: 'Name sticker' },
    { test: /noodle\s*mat/i, category: 'Floor Mat / Mat', product: 'Noodle Mat' },
    { test: /r(?:e|a)ae?.*bumpe?r.*(?:surya|sooya)|(?:surya|sooya).*bumpe?r|bumpee.*sooya/i, category: 'rear bumper', product: 'rear bumper surya' },
    { test: /hella.*(?:chrome|choro|choro me).*hon|chrome.*hella.*horn|hella.*hon/i, category: 'Horn', product: 'hella chrome horn' }
  ];
  for (const alias of aliases) {
    if (alias.test.test(rawName)) {
      const category = data.categories.find(c => normalized(c) === normalized(alias.category));
      const products = category ? productsForCategory(category) : [];
      const product = products.find(p => normalized(p) === normalized(alias.product));
      if (category && product) return { category, product };
    }
  }
  return findSavedProduct(rawName);
}

async function processPastedProducts(text) {
  // One item per line/tab/semicolon. Trailing prices are removed before product lookup,
  // so a price like 3200 is never accidentally saved as part of a product name.
  const lines = String(text || '').split(/\r?\n|\t|;/).map(x => x.trim()).filter(Boolean);
  if (!lines.length) return;
  const parsed = lines.map(parseBulkProductLine).filter(Boolean);
  const prices = parsed.map(item => item.amount);

  for (const item of parsed) {
    const rawName = item.name;
    const quantity = item.quantity;
    const saved = resolveCatalogProduct(rawName);
    if (saved) {
      selectedCategory = saved.category;
      renderCategories();
      const existing = selected.find(x => normalized(x.category) === normalized(saved.category) && normalized(x.product) === normalized(saved.product));
      if (existing) existing.quantity += quantity;
      else selected.push({ category: saved.category, product: saved.product, quantity });
      updateSelected();
      continue;
    }

    let inferred = null;
    try {
      const result = await api('/api/detect-product-category', 'POST', { product: rawName });
      if (result.found && data.categories.some(c => normalized(c) === normalized(result.category))) {
        inferred = data.categories.find(c => normalized(c) === normalized(result.category));
      }
    } catch (_) {}

    if (inferred) {
      await addNewProductToCategory(rawName, inferred);
      const itemAdded = selected.find(x => normalized(x.product) === normalized(rawName) && normalized(x.category) === normalized(inferred));
      if (itemAdded) itemAdded.quantity = quantity;
      updateSelected();
    } else {
      // Preserve the entered product name and avoid interrupting bulk entry with category prompts.
      // Use the detected category when clear; otherwise store it under Other rather than selecting an unrelated item.
      const fallbackCategory = data.categories.find(c => normalized(c) === 'other') || data.categories[0];
      await addNewProductToCategory(rawName, fallbackCategory);
      const itemAdded = selected.find(x => normalized(x.product) === normalized(rawName) && normalized(x.category) === normalized(fallbackCategory));
      if (itemAdded) itemAdded.quantity = quantity;
      updateSelected();
    }
  }

  // Sum all line amounts that were supplied, even if one or more products have no amount.
  // Keep a total the user has already entered manually.
  const knownPrices = prices.filter(value => value !== null && Number.isFinite(value));
  if (knownPrices.length) {
    // The pasted line-item prices are the source of truth for the bill total.
    $('totalAmount').value = String(knownPrices.reduce((sum, value) => sum + value, 0));
  }
  $('productSearch').value = '';
  detectedCategoryForInput = '';
  renderProducts();
}

function updateSelected() {
  $('selectedCount').textContent = `${selected.length} product${selected.length === 1 ? '' : 's'} selected`;
  $('selectedProducts').innerHTML = selected.map((x, i) => `<div class="selected-item" style="border-left:4px solid ${(categoryPalette[normalized(x.category)] || ['#f8fafc','#475569'])[1]}"><div><b>${esc(x.product)}</b><small style="display:block;color:${(categoryPalette[normalized(x.category)] || ['#f8fafc','#475569'])[1]}">${esc(x.category)}</small></div><input type="number" min="1" value="${x.quantity}" data-i="${i}"><button type="button" class="remove" data-i="${i}">×</button></div>`).join('');
  document.querySelectorAll('.selected-item input').forEach(e => e.oninput = () => { selected[+e.dataset.i].quantity = Math.max(1, +e.value || 1); });
  document.querySelectorAll('.remove').forEach(e => e.onclick = () => { selected.splice(+e.dataset.i, 1); updateSelected(); });
}
$('processBulkProductsBtn').addEventListener('click', async () => {
  const bulkText = $('bulkProducts').value.trim();
  if (!bulkText) return toast('Type or paste your product list first.', 'error');
  const button = $('processBulkProductsBtn');
  button.disabled = true;
  const oldLabel = button.textContent;
  button.textContent = 'Adding products...';
  try {
    await processPastedProducts(bulkText);
    $('bulkProducts').value = '';
    toast('Bulk product list processed. Check the selected products before saving.');
  } catch (e) {
    toast(e.message || 'Could not process the product list.', 'error');
  } finally {
    button.disabled = false;
    button.textContent = oldLabel;
  }
});
$('clearBulkProductsBtn').addEventListener('click', () => { $('bulkProducts').value = ''; $('bulkProducts').focus(); });

$('productSearch').addEventListener('input', () => {
  detectedCategoryForInput = '';
  renderProducts();
  clearTimeout(detectTimer);
  detectTimer = setTimeout(async () => {
    const name = $('productSearch').value.trim();
    if (!name || findSavedProduct(name)) return;
    try {
      const result = await api('/api/detect-product-category', 'POST', { product: name });
      if (result.found && data.categories.includes(result.category)) {
        detectedCategoryForInput = result.category;
        selectedCategory = result.category; renderCategories(); renderProducts();
      }
    } catch (_) { /* Keep the category chooser available if detection is unavailable. */ }
  }, 250);
});
$('productSearch').addEventListener('keydown', async event => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  const name = $('productSearch').value.trim();
  if (!name) return;
  await processPastedProducts(name);
});
$('productSearch').addEventListener('paste', event => {
  const pasted = (event.clipboardData || window.clipboardData).getData('text');
  if (/\r?\n|\t|;/.test(pasted)) {
    event.preventDefault();
    processPastedProducts(pasted).catch(e => toast(e.message, 'error'));
  }
});
$('addNewProductBtn').onclick = async () => { const product = $('productSearch').value.trim(); const category = $('newProductCategory').value; if (!product || !category) return; try { await addNewProductToCategory(product, category); } catch (e) { toast(e.message, 'error'); } };
$('saveBtn').onclick = async () => {
  if (!selected.length) return toast('Add at least one product', 'error');
  const body = { customer: { date: $('entryDate').value, name: $('customerName').value, mobile: $('mobile').value, vehicle: $('vehicle').value, total_amount: $('totalAmount').value }, products: selected };
  try {
    const result = await api('/api/save-customer', 'POST', body);
    toast(result.message || 'Customer saved.');
    ['customerName', 'mobile', 'vehicle', 'totalAmount'].forEach(id => $(id).value = '');
    selected = []; updateSelected();
  } catch (e) { toast(e.message || 'Save failed', 'error'); }
};
load().catch(e => toast(`Could not load products: ${e.message}`, 'error'));
