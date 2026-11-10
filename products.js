
let data = { categories: [], products: {} };
let active = '';
let busy = false;

const $ = id => document.getElementById(id);

async function api(url, method = 'GET', payload) {
  const options = {
    method,
    headers: { 'Content-Type': 'application/json' }
  };

  if (payload !== undefined) {
    options.body = JSON.stringify(payload);
  }

  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(result.message || `Request failed (${response.status}).`);
  }

  return result;
}

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[ch]);
}

function normalize(value) {
  return String(value ?? '')
    .trim()
    .replace(/\s+/g, ' ')
    .toLocaleLowerCase();
}

function toast(message, type = 'success') {
  if (typeof window.showToast === 'function') {
    window.showToast(message, type);
  } else {
    console.log(`[${type}] ${message}`);
    if (type === 'error') alert(message);
  }
}

function validateElements() {
  const required = [
    'categoryList',
    'productTitle',
    'manageProducts',
    'addProduct',
    'addCategory',
    'checkDuplicates'
  ];

  const missing = required.filter(id => !$(id));

  if (missing.length) {
    throw new Error(
      'products.html missing element IDs: ' + missing.join(', ')
    );
  }
}

async function load() {
  try {
    validateElements();
    await refreshData();
    console.log(`Loaded ${data.categories.length} categories.`);
  } catch (error) {
    console.error('Product Management loading error:', error);
    alert('Product Management could not load: ' + error.message);
  }
}

async function refreshData() {
  const result = await api('/api/data');

  if (
    !result ||
    !Array.isArray(result.categories) ||
    !result.products ||
    typeof result.products !== 'object'
  ) {
    throw new Error('Invalid data returned by /api/data.');
  }

  data = result;

  data.categories = data.categories.filter(
    category => typeof category === 'string' && category.trim()
  );

  if (!active || !data.categories.includes(active)) {
    active = data.categories[0] || '';
  }

  renderCats();
  renderProducts();
}

function renderCats() {
  const list = $('categoryList');
  if (!list) return;

  list.innerHTML = data.categories.map(category => `
    <div class="category-item ${category === active ? 'active' : ''}"
         data-category="${esc(category)}">
      <span class="category-name"
            style="flex:1;overflow-wrap:anywhere">
        ${esc(category)}
      </span>

      <span>${(data.products[category] || []).length}</span>

      <button type="button"
              class="btn btn-sm rename-category"
              data-category="${esc(category)}">
        Rename
      </button>

      <button type="button"
              class="btn btn-sm delete-category"
              data-category="${esc(category)}">
        Delete
      </button>
    </div>
  `).join('') || '<div class="hint">No categories found.</div>';

  list.querySelectorAll('.category-item').forEach(item => {
    item.onclick = event => {
      if (event.target.closest('button')) return;

      active = item.dataset.category;
      renderCats();
      renderProducts();
    };
  });

  list.querySelectorAll('.rename-category').forEach(button => {
    button.onclick = async event => {
      event.stopPropagation();

      const oldName = button.dataset.category;
      const answer = prompt('Rename category:', oldName);

      if (answer === null || !answer.trim()) return;

      const newName = answer.trim();
      if (newName === oldName) return;

      if (data.categories.some(
        c => c !== oldName && normalize(c) === normalize(newName)
      )) {
        toast('This category already exists.', 'error');
        return;
      }

      try {
        const result = await api('/api/category', 'PUT', {
          old_category: oldName,
          new_category: newName
        });

        data = result.data;
        active = newName;
        renderCats();
        renderProducts();
        toast(result.message || 'Category renamed.');
      } catch (error) {
        toast(error.message, 'error');
      }
    };
  });

  list.querySelectorAll('.delete-category').forEach(button => {
    button.onclick = async event => {
      event.stopPropagation();

      const category = button.dataset.category;
      const count = (data.products[category] || []).length;

      if (!confirm(
        `Delete category "${category}" and its ${count} catalogue products?\n\n` +
        'Existing customer history should be preserved by the backend. Continue?'
      )) return;

      try {
        const result = await api(
          `/api/category/${encodeURIComponent(category)}`,
          'DELETE'
        );

        data = result.data;
        if (!data.categories.includes(active)) {
          active = data.categories[0] || '';
        }

        renderCats();
        renderProducts();
        toast(result.message || 'Category deleted.');
      } catch (error) {
        toast(error.message, 'error');
      }
    };
  });
}

function renderProducts() {
  const title = $('productTitle');
  const list = $('manageProducts');

  if (!title || !list) return;

  title.textContent = active || 'Products';

  const search = $('productManageSearch');
  const query = normalize(search ? search.value : '');

  const products = (data.products[active] || []).filter(product =>
    normalize(product).includes(query)
  );

  list.innerHTML = products.map(product => `
    <div class="manage-product"
         style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="flex:1;min-width:130px;overflow-wrap:anywhere">
        ${esc(product)}
      </span>

      <button type="button"
              class="btn btn-sm rename-product"
              data-product="${esc(product)}">
        Edit name
      </button>

      <button type="button"
              class="btn btn-sm move-product"
              data-product="${esc(product)}">
        Move
      </button>

      <button type="button"
              class="btn btn-sm delete-product"
              data-product="${esc(product)}">
        Delete
      </button>
    </div>
  `).join('') || '<div class="hint">No products in this category.</div>';

  list.querySelectorAll('.rename-product').forEach(button => {
    button.onclick = () => renameProduct(button.dataset.product);
  });

  list.querySelectorAll('.move-product').forEach(button => {
    button.onclick = () => moveProduct(button.dataset.product);
  });

  list.querySelectorAll('.delete-product').forEach(button => {
    button.onclick = () => removeProduct(button.dataset.product);
  });
}

async function removeProduct(product, askConfirmation = true) {
  if (!active || !product) return;

  if (
    askConfirmation &&
    !confirm(`Remove "${product}" from category "${active}" only?`)
  ) return false;

  try {
    // Deletes this catalogue entry from this category only.
    // Does not call the global duplicate-removal endpoint.
    const result = await api('/api/product', 'DELETE', {
      category: active,
      product
    });

    data = result.data;
    renderCats();
    renderProducts();

    if (askConfirmation) {
      toast(result.message || 'Product removed from category.');
    }

    return true;
  } catch (error) {
    toast(error.message, 'error');
    return false;
  }
}

async function renameProduct(product) {
  const answer = prompt('Correct or rename product:', product);

  if (answer === null || !answer.trim()) return;

  const newName = answer.trim();
  if (newName === product) return;

  if ((data.products[active] || []).some(
    p => normalize(p) === normalize(newName) &&
         normalize(p) !== normalize(product)
  )) {
    toast('This product already exists in this category.', 'error');
    return;
  }

  try {
    const result = await api('/api/product', 'PUT', {
      category: active,
      old_product: product,
      new_product: newName
    });

    data = result.data;
    renderCats();
    renderProducts();
    toast(result.message || 'Product name updated.');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function moveProduct(product) {
  try {
    await refreshData();

    const source = active;
    const choices = data.categories.filter(category => category !== source);

    if (!choices.length) {
      toast('Add another category before moving products.', 'error');
      return;
    }

    const menu = choices.map(
      (category, index) => `${index + 1}. ${category}`
    ).join('\n');

    const answer = prompt(
      `Move "${product}" from "${source}".\n\n` +
      `Enter destination category name or number:\n\n${menu}`
    );

    if (answer === null || !answer.trim()) return;

    const raw = answer.trim();
    const index = Number(raw) - 1;

    const destination =
      /^\d+$/.test(raw) && index >= 0 && index < choices.length
        ? choices[index]
        : choices.find(c => normalize(c) === normalize(raw));

    if (!destination) {
      toast(`Category not found: ${raw}`, 'error');
      return;
    }

    if ((data.products[destination] || []).some(
      p => normalize(p) === normalize(product)
    )) {
      toast(
        `"${product}" already exists in "${destination}". Check duplicates first.`,
        'error'
      );
      return;
    }

    if (!confirm(
      `Move "${product}" to "${destination}"?\n\n` +
      'The backend must preserve existing customer records.'
    )) return;

    const result = await api('/api/product/move', 'POST', {
      category: source,
      product,
      target_category: destination
    });

    data = result.data;
    active = destination;
    renderCats();
    renderProducts();
    toast(result.message || 'Product moved.');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function addProduct() {
  if (!active) {
    toast('Select a category first.', 'error');
    return;
  }

  const answer = prompt(`New product for "${active}":`);
  if (answer === null || !answer.trim()) return;

  const product = answer.trim();

  if ((data.products[active] || []).some(
    p => normalize(p) === normalize(product)
  )) {
    toast('This product already exists in the selected category.', 'error');
    return;
  }

  try {
    const result = await api('/api/product', 'POST', {
      category: active,
      product
    });

    data = result.data;
    renderCats();
    renderProducts();
    toast(result.message || 'Product added.');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function addCategory() {
  const answer = prompt('New category name:');
  if (answer === null || !answer.trim()) return;

  const category = answer.trim();

  if (data.categories.some(c => normalize(c) === normalize(category))) {
    toast('This category already exists.', 'error');
    return;
  }

  try {
    const result = await api('/api/category', 'POST', { category });

    data = result.data;
    active = category;
    renderCats();
    renderProducts();
    toast(result.message || 'Category added.');
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function checkDuplicates() {
  if (busy) return;

  busy = true;
  const button = $('checkDuplicates');
  if (button) button.disabled = true;

  try {
    await refreshData();

    // Group matching product names across categories.
    const groups = new Map();

    for (const category of data.categories) {
      for (const product of (data.products[category] || [])) {
        const key = normalize(product);
        if (!key) continue;

        if (!groups.has(key)) {
          groups.set(key, {
            product,
            categories: []
          });
        }

        const group = groups.get(key);

        if (!group.categories.includes(category)) {
          group.categories.push(category);
        }
      }
    }

    const duplicates = [...groups.values()].filter(
      group => group.categories.length > 1
    );

    if (!duplicates.length) {
      alert('No duplicate product names found across categories.');
      return;
    }

    let removed = 0;
    let skipped = 0;
    let failed = 0;

    for (const group of duplicates) {
      while (true) {
        // Fetch current catalogue before every decision.
        await refreshData();

        const matches = data.categories.filter(category =>
          (data.products[category] || []).some(
            product => normalize(product) === normalize(group.product)
          )
        );

        if (matches.length < 2) break;

        const menu = matches.map(
          (category, index) => `${index + 1}. ${category}`
        ).join('\n');

        const answer = prompt(
          `Duplicate product: "${group.product}"\n\n` +
          `Found in these categories:\n${menu}\n\n` +
          'Enter the NUMBER of the category to remove this product FROM.\n' +
          'The product will remain in the other categories.\n' +
          'Press Cancel to skip this product.'
        );

        if (answer === null) {
          skipped++;
          break;
        }

        const raw = answer.trim();

        if (!/^\d+$/.test(raw)) {
          alert('Enter a valid category number.');
          continue;
        }

        const index = Number(raw) - 1;

        if (index < 0 || index >= matches.length) {
          alert('Invalid category number. Try again.');
          continue;
        }

        const removeCategory = matches[index];

        const remaining = matches.filter(
          category => category !== removeCategory
        );

        if (!confirm(
          `Remove "${group.product}" from "${removeCategory}" only?\n\n` +
          `It will remain in: ${remaining.join(', ')}.\n\n` +
          'This uses the category-specific product delete route.'
        )) {
          skipped++;
          continue;
        }

        // The existing DELETE route removes one catalogue entry only.
        // It does not call /api/remove-duplicates or /api/resolve-duplicate.
        const result = await api('/api/product', 'DELETE', {
          category: removeCategory,
          product: group.product
        });

        data = result.data;
        active = removeCategory;
        renderCats();
        renderProducts();

        removed++;
        toast(
          result.message ||
          `"${group.product}" removed from "${removeCategory}".`
        );

        break;
      }
    }

    await refreshData();

    alert(
      'Duplicate check completed.\n\n' +
      `Duplicate groups found: ${duplicates.length}\n` +
      `Category entries removed: ${removed}\n` +
      `Skipped: ${skipped}\n` +
      `Errors: ${failed}\n\n` +
      'Customer records are not intentionally deleted by this frontend.'
    );
  } catch (error) {
    console.error('Duplicate check failed:', error);
    failed++;
    alert(
      'Duplicate check stopped: ' + error.message +
      '\n\nRefresh the page and check the catalogue.'
    );
  } finally {
    busy = false;
    if (button) button.disabled = false;
  }
}

function bindEvents() {
  $('addProduct').addEventListener('click', addProduct);
  $('addCategory').addEventListener('click', addCategory);
  $('checkDuplicates').addEventListener('click', checkDuplicates);

  const search = $('productManageSearch');
  if (search) {
    search.addEventListener('input', renderProducts);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  try {
    bindEvents();
    load();
  } catch (error) {
    console.error('Product Management error:', error);
    alert('Product Management error: ' + error.message);
  }
});
