let salesChart = null;
let productChart = null;
let monthDailyChart = null;
async function loadDashboard() {
  try {
    const response = await fetch('/api/dashboard');
    const d = await response.json();
    if (!response.ok) throw new Error(d.message || 'Dashboard loading failed');
    document.getElementById('totalSales').textContent = money(d.total_sales);
    document.getElementById('totalCustomers').textContent = d.total_customers;
    document.getElementById('productsUsed').textContent = d.products_used;
    document.getElementById('activeMonths').textContent = d.active_months;
    const salesCanvas = document.getElementById('salesChart');
    salesChart = new Chart(salesCanvas, {
      type: 'bar',
      data: { labels: d.month_labels, datasets: [{ label: 'Sales', data: d.month_sales, borderWidth: 1 }] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => `Sales: ${money(c.raw)}` } } },
        onClick: async (_event, elements) => {
          if (!elements.length) return;
          const month = d.month_labels[elements[0].index];
          await showMonthDetails(month);
        },
        onHover: (event, elements) => { event.native.target.style.cursor = elements.length ? 'pointer' : 'default'; }
      }
    });
    productChart = new Chart(document.getElementById('productChart'), {
      type: 'bar', data: { labels: d.top_products.map(x => x.name), datasets: [{ label: 'Quantity sold', data: d.top_products.map(x => x.quantity) }] },
      options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } } }
    });
    document.getElementById('backToMonths').onclick = () => {
      document.getElementById('monthDetails').hidden = true;
      document.getElementById('monthDetails').scrollIntoView({ behavior: 'smooth', block: 'start' });
    };
  } catch (error) { console.error(error); toast(`Dashboard could not load: ${error.message}`, 'error'); }
}
async function showMonthDetails(month) {
  try {
    const response = await fetch(`/api/month-details?month=${encodeURIComponent(month)}`);
    const d = await response.json();
    if (!response.ok) throw new Error(d.message || 'Could not load month details');
    const box = document.getElementById('monthDetails'); box.hidden = false;
    document.getElementById('monthDetailTitle').textContent = `${month} — Daily Sales & Customers`;
    document.getElementById('detailMonthSales').textContent = money(d.total_amount);
    document.getElementById('detailMonthCustomers').textContent = d.total_customers;
    document.getElementById('minimumDailyAmount').textContent = d.minimum_daily_amount ? money(d.minimum_daily_amount.amount) : '₹0';
    document.getElementById('minimumDailyAmountDate').textContent = d.minimum_daily_amount ? `Lowest on ${d.minimum_daily_amount.date}` : 'No records';
    document.getElementById('minimumDailyCustomers').textContent = d.minimum_daily_customers ? d.minimum_daily_customers.customers : 0;
    document.getElementById('minimumDailyCustomersDate').textContent = d.minimum_daily_customers ? `Lowest on ${d.minimum_daily_customers.date}` : 'No records';
    if (monthDailyChart) monthDailyChart.destroy();
    monthDailyChart = new Chart(document.getElementById('monthDailyChart'), {
      type: 'line', data: { labels: d.days.map(x => x.date), datasets: [
        { label: 'Daily sales (₹)', data: d.days.map(x => x.amount), yAxisID: 'y', tension: .25 },
        { label: 'Customer visits', data: d.days.map(x => x.customers), yAxisID: 'y1', tension: .25 }
      ] }, options: { responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        scales: { y: { beginAtZero: true, title: { display: true, text: 'Sales amount (₹)' } }, y1: { beginAtZero: true, position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'Customer visits' }, ticks: { precision: 0 } } }
      }
    });
    box.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) { toast(error.message, 'error'); }
}
loadDashboard();
