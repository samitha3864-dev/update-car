let rows = [];
let editing = null;
let customerDailyChart = null;
let analyticsDailyData = [];
let productCatalog = { categories: [], products: {} };
const $ = id => document.getElementById(id);

async function load() {
    try {
        const customerResponse = await fetch('/api/customers');
        if (!customerResponse.ok) {
            throw new Error(`Customer API failed: ${customerResponse.status}`);
        }

        const j = await customerResponse.json();
        rows = Array.isArray(j.customers) ? j.customers : [];

        try {
            const cfgResponse = await fetch('/api/data');
            if (cfgResponse.ok) {
                const cfg = await cfgResponse.json();
                productCatalog = {
                categories: Array.isArray(cfg.categories) ? cfg.categories : [],
                products: cfg.products || {}
};
populateEditCategories();
                document.documentElement.style.setProperty(
                    '--priority-bg',
                    cfg.settings?.priority_color || '#fff2cc'
                );
                document.documentElement.style.setProperty(
                    '--priority-text',
                    cfg.settings?.priority_text_color || '#7f6000'
                );
            }
        } catch (error) {
            console.warn('Settings load failed:', error);
        }

        try {
            const analyticsResponse = await fetch('/api/analytics');
            if (analyticsResponse.ok) {
                const analytics = await analyticsResponse.json();
                analyticsDailyData = Array.isArray(analytics.daily_data)
                    ? analytics.daily_data
                    : [];
                renderCustomerGraph();
            }
        } catch (error) {
            console.error('Customer graph load failed:', error);
        }

        const monthFilter = $('monthFilter');
        if (monthFilter) {
            const months = [
                ...new Set(
                    rows
                        .filter(r => r.date)
                        .map(r => {
                            const parts = String(r.date).split('-');
                            if (parts.length !== 3) return null;

                            const date = new Date(
                                `${parts[2]}-${parts[1]}-${parts[0]}`
                            );

                            return Number.isNaN(date.getTime())
                                ? null
                                : date.toLocaleString('en', {
                                    month: 'long'
                                });
                        })
                        .filter(Boolean)
                )
            ];

            const previousMonth = monthFilter.value;
            monthFilter.innerHTML =
                '<option value="">All months</option>' +
                months.map(m =>
                    `<option value="${esc(m)}">${esc(m)}</option>`
                ).join('');

            if (months.includes(previousMonth)) {
                monthFilter.value = previousMonth;
            }
        }

        render();
        updateCustomerGraphTotal();

        console.log('Customer records loaded:', rows.length);
    } catch (error) {
        console.error('Customer records load failed:', error);

        const body = $('customerBody');
        if (body) {
            body.innerHTML =
                '<tr><td colspan="8" class="hint">' +
                'Unable to load customer records. Check the browser Console ' +
                'and Flask terminal for errors.' +
                '</td></tr>';
        }

        toast('Could not load customer records. Check the Flask terminal.', 'error');
    }
}

function formatCustomerDate(value) {
    const parts = String(value || '').split('-');

    return parts.length === 3
        ? `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`
        : value;
}

function toISODate(value) {
    const parts = String(value || '').split('-');

    return parts.length === 3
        ? `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`
        : '';
}

function isPriorityCustomer(record) {
    return (record.products || []).some(product => {
        const value =
            `${product.category || ''} ${product.product || ''}`.toLowerCase();

        return (
            (value.includes('sunfilm') || value.includes('seat cover')) &&
            Number(product.quantity || 0) > 0
        );
    });
}

function render() {
    const body = $('customerBody');
    if (!body) return;

    const q = ($('customerSearch')?.value || '').toLowerCase().trim();
    const selectedMonth = $('monthFilter')?.value || '';
    const selectedDate = $('dateFilter')?.value || '';

    const filtered = rows.filter(record => {
        const searchText =
            `${record.name || ''} ${record.mobile || ''} ${record.vehicle || ''}`
                .toLowerCase();

        const parts = String(record.date || '').split('-');
        const date = parts.length === 3
            ? new Date(`${parts[2]}-${parts[1]}-${parts[0]}`)
            : null;

        const month = date && !Number.isNaN(date.getTime())
            ? date.toLocaleString('en', { month: 'long' })
            : '';

        return (
            (!q || searchText.includes(q)) &&
            (!selectedMonth || month === selectedMonth) &&
            (!selectedDate || toISODate(record.date) === selectedDate)
        );
    });

    if (!filtered.length) {
        body.innerHTML =
            '<tr><td colspan="8" class="hint">' +
            (rows.length
                ? 'No customer records match the selected filters.'
                : 'No customer records returned by the API. Check the Flask backend and Excel data.') +
            '</td></tr>';
        return;
    }

    body.innerHTML = filtered.map(record => `
        <tr class="${isPriorityCustomer(record) ? 'priority-customer-row' : ''}">
            <td>${esc(record.display_no ?? '')}</td>
            <td>${esc(record.date ?? '')}</td>
            <td><b>${esc(record.name ?? '')}</b></td>
            <td>${esc(record.mobile ?? '')}</td>
            <td>${esc(record.vehicle ?? '')}</td>
            <td class="product-text">
                ${(record.products || []).map(product =>
                    `${esc(product.product ?? '')} × ${esc(product.quantity ?? 0)}`
                ).join(', ') || '—'}
            </td>
            <td><b>${money(record.total_amount ?? 0)}</b></td>
            <td>
                <div class="action-group">
                    <button class="btn btn-light btn-sm"
                        onclick="editRow('${esc(record.sheet ?? '')}', ${Number(record.excel_row) || 0})">
                        Edit
                    </button>
                    <button class="btn btn-sm"
                        style="background:#fee2e2;color:#b91c1c"
                        onclick="deleteRow('${esc(record.sheet ?? '')}', ${Number(record.excel_row) || 0})">
                        Delete
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
}

function renderCustomerGraph() {
    const canvas = $('customerDailyChart');
    if (!canvas || typeof Chart === 'undefined') return;

    const monthInput = $('graphMonthFilter');
    const allDays = analyticsDailyData
        .map(item => {
            const parts = String(item.date || '').split('-');
            if (parts.length !== 3) return null;

            return {
                date: `${parts[2]}-${parts[1].padStart(2, '0')}-${parts[0].padStart(2, '0')}`,
                amount: Number(item.amount || 0)
            };
        })
        .filter(Boolean);

    if (monthInput && !monthInput.value && allDays.length) {
        monthInput.value = allDays
            .map(item => item.date.slice(0, 7))
            .sort()
            .at(-1);
    }

    const selectedMonth = monthInput?.value || '';
    const matchingDays = allDays.filter(item =>
        item.date.startsWith(selectedMonth)
    );

    const amountsByDate = {};
    matchingDays.forEach(item => {
        amountsByDate[item.date] =
            (amountsByDate[item.date] || 0) + item.amount;
    });

    let labels = [];
    let values = [];

    if (selectedMonth) {
        const [year, month] = selectedMonth.split('-').map(Number);
        const daysInMonth = new Date(year, month, 0).getDate();

        for (let day = 1; day <= daysInMonth; day++) {
            const date =
                `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;

            labels.push(date);
            values.push(amountsByDate[date] || 0);
        }
    }

    if (customerDailyChart) customerDailyChart.destroy();

    customerDailyChart = new Chart(canvas, {
        type: 'line',
        data: {
            labels: labels.map(date => date.slice(8, 10)),
            datasets: [{
                label: 'Daily Income (₹)',
                data: values,
                fill: true,
                tension: 0.25,
                borderWidth: 2,
                pointRadius: 3,
                borderColor: '#2563eb',
                backgroundColor: 'rgba(37,99,235,.12)'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: true },
                tooltip: {
                    callbacks: {
                        label: context => `₹${Number(context.raw || 0).toLocaleString('en-IN')}`
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    title: { display: true, text: 'Income (₹)' }
                },
                x: {
                    title: { display: true, text: 'Day of month' }
                }
            }
        }
    });

    const total = values.reduce((sum, amount) => sum + amount, 0);

    if ($('customerGraphAmount')) {
        $('customerGraphAmount').textContent = money(total);
    }

    if ($('customerGraphDate')) {
        $('customerGraphDate').textContent = selectedMonth
            ? new Date(`${selectedMonth}-01T00:00:00`).toLocaleString('en-IN', {
                month: 'long',
                year: 'numeric'
            }) + ' total'
            : 'No month selected';
    }
}

if ($('graphMonthFilter')) {
    $('graphMonthFilter').addEventListener('change', renderCustomerGraph);
}

function updateCustomerGraphTotal() {
    const amountElement = $('customerGraphAmount');
    const dateElement = $('customerGraphDate');
    const selectedDate = $('dateFilter')?.value || '';

    const found = analyticsDailyData.find(
        item => toISODate(item.date) === selectedDate
    );

    if (amountElement) {
        const total = selectedDate
            ? Number(found?.amount || 0)
            : analyticsDailyData.reduce(
                (sum, item) => sum + Number(item.amount || 0), 0
            );

        amountElement.textContent = money(total);
    }

    if (dateElement) {
        dateElement.textContent = selectedDate
            ? formatCustomerDate(found?.date || selectedDate)
            : 'All dates total';
    }

    if (customerDailyChart) {
        customerDailyChart.data.datasets[0].pointBackgroundColor =
            analyticsDailyData.map(item =>
                toISODate(item.date) === selectedDate ? '#dc2626' : '#2563eb'
            );

        customerDailyChart.update();
    }
}
function populateEditCategories() {
    const categorySelect = $('editProductCategory');
    if (!categorySelect) return;

    const previous = categorySelect.value;

    categorySelect.innerHTML =
        '<option value="">Select category</option>' +
        productCatalog.categories.map(category =>
            `<option value="${esc(category)}">${esc(category)}</option>`
        ).join('');

    if (productCatalog.categories.includes(previous)) {
        categorySelect.value = previous;
    }

    populateEditProductNames();
}

function populateEditProductNames() {
    const category = $('editProductCategory')?.value || '';
    const productSelect = $('editProductName');
    if (!productSelect) return;

    const products = productCatalog.products[category] || [];

    productSelect.innerHTML =
        '<option value="">Select product</option>' +
        products.map(product =>
            `<option value="${esc(product)}">${esc(product)}</option>`
        ).join('');

    productSelect.disabled = !category;
}

if ($('editProductCategory')) {
    $('editProductCategory').addEventListener('change', populateEditProductNames);
}

if ($('addEditProductBtn')) {
    $('addEditProductBtn').addEventListener('click', () => {
        const category = $('editProductCategory').value;
        const product = $('editProductName').value;
        const quantity = Math.max(
            1,
            Number($('editProductQuantity').value) || 1
        );

        if (!category || !product) {
            toast('Please select a category and product.', 'error');
            return;
        }

        const list = $('editProducts');
        const existing = [...list.querySelectorAll('.edit-product-row')]
            .find(item =>
                item.dataset.category === category &&
                item.dataset.product === product
            );

        if (existing) {
            const input = existing.querySelector('.epq');
            input.value = (Number(input.value) || 0) + quantity;
        } else {
            const item = document.createElement('div');
            item.className = 'selected-item edit-product-row';
            item.dataset.category = category;
            item.dataset.product = product;

            const info = document.createElement('div');
            const title = document.createElement('b');
            title.textContent = product;
            const subtitle = document.createElement('small');
            subtitle.style.display = 'block';
            subtitle.style.color = '#64748b';
            subtitle.textContent = category;

            info.append(title, subtitle);

            const input = document.createElement('input');
            input.className = 'epq';
            input.type = 'number';
            input.min = '1';
            input.value = String(quantity);

            item.append(info, input);
            list.appendChild(item);
        }

        $('editProductQuantity').value = '1';
        toast('Product added to this customer.');
    });
}
async function editRow(sheet, row) {
    editing = { sheet, row };

    const record = rows.find(
        item => item.sheet === sheet && Number(item.excel_row) === Number(row)
    );

    if (!record) return;

    $('editDate').value = toISODate(record.date);
    $('editName').value = record.name || '';
    $('editMobile').value = record.mobile || '';
    $('editVehicle').value = record.vehicle || '';
    $('editAmount').value = record.total_amount ?? 0;

    $('editProducts').innerHTML = (record.products || []).map((product, index) => `
        <div class="selected-item edit-product-row"
            data-category="${esc(product.category || '')}"
            data-product="${esc(product.product || '')}">
            <div>
                <b>${esc(product.product || '')}</b>
                <small style="display:block;color:#64748b">
                    ${esc(product.category || '')}
                </small>
            </div>
            <input class="epq" data-i="${index}" type="number"
                min="1" value="${Number(product.quantity) || 1}">
        </div>
    `).join('');

    $('editModal').hidden = false;
}

async function deleteRow(sheet, row) {
    if (!confirm('Delete this customer record?')) return;

    try {
        const response = await fetch(
            `/api/customer/${encodeURIComponent(sheet)}/${row}`,
            { method: 'DELETE' }
        );

        const result = await response.json();

        if (!response.ok) {
            toast(result.message || 'Could not delete customer.', 'error');
            return;
        }

        toast(result.message || 'Customer deleted.');
        await load();
    } catch (error) {
        console.error(error);
        toast('Unable to delete customer. Check the Flask terminal.', 'error');
    }
}

if ($('updateBtn')) {
    $('updateBtn').onclick = async () => {
        const old = rows.find(
            item => item.sheet === editing?.sheet &&
                Number(item.excel_row) === Number(editing?.row)
        );

        if (!old) {
            toast('Customer record not found.', 'error');
            return;
        }

        const products = [
    ...$('editProducts').querySelectorAll('.edit-product-row')
].map(item => ({
    category: item.dataset.category,
    product: item.dataset.product,
    quantity: Math.max(
        1,
        Number(item.querySelector('.epq')?.value) || 1
    )
}));

        const body = {
            customer: {
                date: $('editDate').value,
                name: $('editName').value,
                mobile: $('editMobile').value,
                vehicle: $('editVehicle').value,
                total_amount: $('editAmount').value
            },
            products
        };

        try {
            const response = await fetch(
                `/api/customer/${encodeURIComponent(editing.sheet)}/${editing.row}`,
                {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body)
                }
            );

            const result = await response.json();

            if (!response.ok) {
                toast(result.message || 'Could not update customer.', 'error');
                return;
            }

            $('editModal').hidden = true;
            toast(result.message || 'Customer updated.');
            await load();
        } catch (error) {
            console.error(error);
            toast('Unable to update customer.', 'error');
        }
    };
}

if ($('closeEdit')) {
    $('closeEdit').onclick = () => {
        $('editModal').hidden = true;
    };
}

if ($('customerSearch')) {
    $('customerSearch').oninput = render;
}

if ($('monthFilter')) {
    $('monthFilter').onchange = () => {
        if ($('monthFilter').value && $('dateFilter')) {
            $('dateFilter').value = '';
        }
        render();
        updateCustomerGraphTotal();
    };
}

if ($('dateFilter')) {
    $('dateFilter').onchange = () => {
        if ($('dateFilter').value && $('monthFilter')) {
            $('monthFilter').value = '';
        }
        render();
        updateCustomerGraphTotal();
    };
}

if ($('refreshBtn')) {
    $('refreshBtn').onclick = async () => {
        await load();
        toast('Customer list refreshed.');
    };
}

if ($('clearFiltersBtn')) {
    $('clearFiltersBtn').onclick = () => {
        if ($('customerSearch')) $('customerSearch').value = '';
        if ($('monthFilter')) $('monthFilter').value = '';
        if ($('dateFilter')) $('dateFilter').value = '';
        render();
        updateCustomerGraphTotal();
    };
}

// This button clears customer records from the workbook.
// It does not run unless the user confirms.
if ($('clearCustomerBtn')) {
    $('clearCustomerBtn').onclick = async () => {
        const confirmed = confirm(
            'Are you sure you want to clear ALL customer records?\n\n' +
            'This may remove entries from the Excel month sheets. ' +
            'Your product catalogue should be kept.'
        );

        if (!confirmed) return;

        const button = $('clearCustomerBtn');
        button.disabled = true;

        try {
            const response = await fetch('/api/clear-excel', {
                method: 'POST'
            });

            const result = await response.json();

            if (!response.ok || !result.success) {
                toast(result.message || 'Could not clear customer records.', 'error');
                return;
            }

            toast(result.message || 'Customer records cleared.');

            if ($('customerSearch')) $('customerSearch').value = '';
            if ($('monthFilter')) $('monthFilter').value = '';
            if ($('dateFilter')) $('dateFilter').value = '';

            await load();
        } catch (error) {
            console.error(error);
            toast('Unable to clear customer records. Please check the Flask terminal.', 'error');
        } finally {
            button.disabled = false;
        }
    };
}

// Automatically load customer records when this script runs.
load();
