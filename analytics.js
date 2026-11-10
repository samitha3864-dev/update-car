let dailyChart = null;
let customerChart = null;


/* =========================
   ANALYTICS DATA
========================= */

let analyticsData = {
    repeat_customers: [],
    repeat_customer_count: 0,
    one_time_customers: 0,
    repeat_products: 0,
    unique_vehicles: 0,

    daily_data: [],
    daily_labels: [],
    daily_sales: [],

    top_products: [],
    sold_products: [],
    unsold_products: []
};


/* =========================
   LOAD ANALYTICS
========================= */

async function loadAnalytics() {

    try {

        const response =
            await fetch("/api/analytics");

        const data =
            await response.json();

        if (!response.ok) {

            throw new Error(
                data.message ||
                "Analytics loading failed"
            );
        }

        analyticsData = data;


        /* UPDATE STAT CARDS */

        updateStats();


        /* MAXIMUM ONE DAY SALES */

        showMaximumDayAmount();


        /* REPEAT CUSTOMERS */

        renderRepeatCustomers();


        /* DATE SELECTOR */

        renderDateSelector();


        /* DAILY SALES GRAPH */

        renderDailyChart();


        /* CUSTOMER GRAPH */

        renderCustomerChart();


        /* PRODUCT ACTIVITY */

        renderProductActivity();


    } catch (error) {

        console.error(
            "Analytics error:",
            error
        );


        const repeatList =
            document.getElementById(
                "repeatCustomerList"
            );

        if (repeatList) {

            repeatList.innerHTML = `
                <div style="
                    padding:20px;
                    color:#d92d20;
                    text-align:center;
                ">
                    Failed to load analytics.
                </div>
            `;
        }

    }
}


/* =========================
   STAT CARDS
========================= */

function updateStats() {

    document.getElementById(
        "repeatCustomerCount"
    ).textContent =
        analyticsData.repeat_customer_count || 0;


    document.getElementById(
        "oneTimeCustomers"
    ).textContent =
        analyticsData.one_time_customers || 0;


    document.getElementById(
        "repeatProducts"
    ).textContent =
        analyticsData.repeat_products || 0;


    document.getElementById(
        "uniqueVehicles"
    ).textContent =
        analyticsData.unique_vehicles || 0;
}


/* =========================
   MAXIMUM ONE DAY SALES
========================= */

function showMaximumDayAmount() {

    const amountElement =
        document.getElementById(
            "maximumDayAmount"
        );

    const dateElement =
        document.getElementById(
            "maximumDayDate"
        );


    if (!amountElement || !dateElement) {
        return;
    }


    const dailyData =
        analyticsData.daily_data || [];


    const validDays =
        dailyData.filter(item =>
            Number(item.amount || 0) > 0
        );


    if (!validDays.length) {

        amountElement.textContent =
            "₹0";

        dateElement.textContent =
            "No sales data";

        return;
    }


    const maximumDay =
        validDays.reduce(
            (max, current) => {

                return Number(current.amount) >
                       Number(max.amount)
                    ? current
                    : max;

            }
        );


    amountElement.textContent =
        formatCurrency(
            maximumDay.amount
        );


    dateElement.textContent =
        "Highest on " +
        formatDate(
            maximumDay.date
        );
}


/* =========================
   REPEAT CUSTOMERS
========================= */

function renderRepeatCustomers() {

    const container =
        document.getElementById(
            "repeatCustomerList"
        );


    if (!container) {
        return;
    }


    container.innerHTML = "";


    const customers =
        analyticsData.repeat_customers || [];


    if (!customers.length) {

        container.innerHTML = `
            <div style="
                padding:20px;
                text-align:center;
                color:#667085;
            ">
                No repeat customers found.
            </div>
        `;

        return;
    }


    customers.forEach(customer => {

        const name =
            customer.name || "Nil";


        const mobile =
            customer.mobile || "Nil";


        const visits =
            customer.visits || 0;


        const item =
            document.createElement("div");


        item.style.cssText = `
            padding:14px;
            margin-bottom:10px;
            border:1px solid #e4e7ec;
            border-radius:10px;
            background:#ffffff;
        `;


        item.innerHTML = `

            <div style="
                font-weight:700;
                font-size:15px;
                color:#101828;
            ">
                ${escapeHtml(name)}
            </div>

            <div style="
                margin-top:5px;
                color:#667085;
                font-size:14px;
            ">
                📱 ${escapeHtml(mobile)}
            </div>

            <div style="
                margin-top:5px;
                color:#475467;
                font-size:13px;
            ">
                🔄 ${visits} visits
            </div>

        `;


        container.appendChild(item);

    });
}


/* =========================
   DATE SELECTOR
========================= */

function renderDateSelector() {

    const selector =
        document.getElementById(
            "dateSelector"
        );


    if (!selector) {
        return;
    }


    selector.innerHTML =
        `<option value="">
            Select a date
        </option>`;


    const dailyData =
        analyticsData.daily_data || [];


    dailyData.forEach(item => {

        const option =
            document.createElement("option");


        option.value =
            item.date;


        option.textContent =
            formatDate(item.date);


        selector.appendChild(option);

    });


    selector.onchange =
        function () {

            const selectedDate =
                this.value;


            showSelectedDay(
                selectedDate
            );


            highlightSelectedDay(
                selectedDate
            );

        };


    /* AUTO SELECT LATEST DATE */

    if (dailyData.length) {

        const latest =
            dailyData[
                dailyData.length - 1
            ].date;


        selector.value =
            latest;


        showSelectedDay(
            latest
        );


        /* GRAPH POINT HIGHLIGHT */

        highlightSelectedDay(
            latest
        );
    }
}


/* =========================
   SELECTED DAY
========================= */

function showSelectedDay(date) {

    const amountElement =
        document.getElementById(
            "selectedDayAmount"
        );


    const dateElement =
        document.getElementById(
            "selectedDayDate"
        );


    if (!amountElement || !dateElement) {
        return;
    }


    if (!date) {

        amountElement.textContent =
            "₹0";


        dateElement.textContent =
            "Select a date";


        return;
    }


    const record =
        (analyticsData.daily_data || [])
        .find(item =>
            item.date === date
        );


    if (!record) {

        amountElement.textContent =
            "₹0";


        dateElement.textContent =
            formatDate(date);


        return;
    }


    amountElement.textContent =
        formatCurrency(
            record.amount
        );


    dateElement.textContent =
        formatDate(date);
}


/* =========================
   DAILY SALES CHART
========================= */

function renderDailyChart() {

    const canvas =
        document.getElementById(
            "dailyChart"
        );


    if (!canvas) {
        return;
    }


    const labels =
        analyticsData.daily_labels || [];


    const values =
        analyticsData.daily_sales || [];


    /* DESTROY OLD CHART */

    if (dailyChart) {

        dailyChart.destroy();

        dailyChart = null;
    }


    /* NO DATA */

    if (!labels.length) {

        return;
    }


    dailyChart =
        new Chart(
            canvas,
            {

                type: "line",

                data: {

                    labels:
                        labels.map(
                            formatDate
                        ),

                    datasets: [

                        {

                            label:
                                "Daily Sales",

                            data:
                                values,

                            fill:
                                true,

                            tension:
                                0.35,

                            borderWidth:
                                3,

                            pointRadius:
                                4,

                            pointHoverRadius:
                                7

                        }

                    ]

                },


                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,


                    interaction: {

                        mode:
                            "index",

                        intersect:
                            false

                    },


                    plugins: {

                        legend: {

                            display:
                                true,

                            position:
                                "top"

                        },


                        tooltip: {

                            callbacks: {

                                title:
                                    function(context) {

                                        if (
                                            !context.length
                                        ) {
                                            return "";
                                        }

                                        return formatDate(
                                            labels[
                                                context[0].dataIndex
                                            ]
                                        );
                                    },


                                label:
                                    function(context) {

                                        return (
                                            " Sales: " +
                                            formatCurrency(
                                                context.raw
                                            )
                                        );

                                    }

                            }

                        }

                    },


                    scales: {

                        x: {

                            title: {

                                display:
                                    true,

                                text:
                                    "Date"

                            },

                            ticks: {

                                autoSkip:
                                    true,

                                maxTicksLimit:
                                    12

                            }

                        },


                        y: {

                            beginAtZero:
                                true,

                            title: {

                                display:
                                    true,

                                text:
                                    "Sales Amount"

                            },

                            ticks: {

                                callback:
                                    function(value) {

                                        return "₹" +
                                            Number(value)
                                            .toLocaleString(
                                                "en-IN"
                                            );

                                    }

                            }

                        }

                    },


                    onClick:
                        function(
                            event,
                            elements
                        ) {

                            if (
                                !elements.length
                            ) {
                                return;
                            }


                            const index =
                                elements[0]
                                .index;


                            const date =
                                labels[index];


                            const selector =
                                document.getElementById(
                                    "dateSelector"
                                );


                            if (selector) {

                                selector.value =
                                    date;

                            }


                            showSelectedDay(
                                date
                            );


                            highlightSelectedDay(
                                date
                            );

                        }

                }

            }
        );
}


/* =========================
   HIGHLIGHT SELECTED DATE
========================= */

function highlightSelectedDay(date) {

    if (!dailyChart) {
        return;
    }


    const labels =
        analyticsData.daily_labels || [];


    const index =
        labels.indexOf(date);


    if (index === -1) {
        return;
    }


    const dataset =
        dailyChart.data.datasets[0];


    dataset.pointRadius =
        labels.map(
            (_, i) =>
                i === index
                    ? 8
                    : 4
        );


    dataset.pointHoverRadius =
        labels.map(
            (_, i) =>
                i === index
                    ? 10
                    : 7
        );


    dailyChart.update();
}


/* =========================
   CUSTOMER CHART
========================= */

function renderCustomerChart() {

    const canvas =
        document.getElementById(
            "customerChart"
        );


    if (!canvas) {
        return;
    }


    if (customerChart) {

        customerChart.destroy();

        customerChart = null;
    }


    const repeat =
        analyticsData
        .repeat_customer_count || 0;


    const oneTime =
        analyticsData
        .one_time_customers || 0;


    customerChart =
        new Chart(
            canvas,
            {

                type:
                    "doughnut",


                data: {

                    labels: [

                        "Repeat Customers",

                        "One-time Customers"

                    ],


                    datasets: [

                        {

                            data: [

                                repeat,

                                oneTime

                            ],

                            borderWidth:
                                2

                        }

                    ]

                },


                options: {

                    responsive:
                        true,

                    maintainAspectRatio:
                        false,


                    plugins: {

                        legend: {

                            position:
                                "bottom"

                        }

                    }

                }

            }
        );
}


/* =========================
   PRODUCT ACTIVITY
========================= */

function renderProductActivity() {

    const container =
        document.getElementById(
            "analyticsLists"
        );


    if (!container) {
        return;
    }


    const topProducts =
        analyticsData.sold_products || analyticsData.top_products || [];


    const unsoldProducts =
        analyticsData.unsold_products || [];


    let html = "";


    /* TOP PRODUCTS */

    html += `

        <div style="
            margin-bottom:25px;
        ">

            <h3 style="
                margin-bottom:12px;
            ">
                Products Sold
            </h3>

    `;


    if (!topProducts.length) {

        html += `

            <p style="
                color:#667085;
            ">
                No product sales found.
            </p>

        `;

    } else {

        topProducts.forEach(
            (product, index) => {

                html += `

                    <div style="
                        display:flex;
                        justify-content:space-between;
                        align-items:center;
                        padding:12px;
                        margin-bottom:8px;
                        border:1px solid #e4e7ec;
                        border-radius:10px;
                    ">

                        <span>
                            ${index + 1}.
                            <strong>${escapeHtml(product.name)}</strong>
                            <small style="display:block;color:#667085;margin-top:3px">${escapeHtml(product.category || 'Other')}</small>
                        </span>

                        <strong>
                            ${product.quantity}
                        </strong>

                    </div>

                `;

            }
        );

    }


    html += `</div>`;


    /* UNSOLD PRODUCTS */

    html += `

        <div>

            <h3 style="
                margin-bottom:12px;
            ">
                Not Sold Products
            </h3>

    `;


    if (!unsoldProducts.length) {

        html += `

            <p style="
                color:#12b76a;
            ">
                All catalogue products have sales.
            </p>

        `;

    } else {

        unsoldProducts.forEach(
            product => {

                html += `

                    <span style="
                        display:inline-block;
                        padding:7px 11px;
                        margin:4px;
                        border-radius:20px;
                        background:#f2f4f7;
                        color:#344054;
                        font-size:13px;
                    ">
                        ${escapeHtml(product.name || product)}
                        ${product.category ? `<small style="display:block;margin-top:3px;color:#667085">${escapeHtml(product.category)}</small>` : ''}
                    </span>

                `;

            }
        );

    }


    html += `</div>`;


    container.innerHTML =
        html;
}


/* =========================
   DATE FORMAT
========================= */

function formatDate(value) {

    if (!value) {
        return "";
    }


    const text =
        String(value);


    const parts =
        text.split("-");


    if (parts.length === 3) {

        return (
            parts[2] +
            "-" +
            parts[1] +
            "-" +
            parts[0]
        );

    }


    return value;
}


/* =========================
   CURRENCY
========================= */

function formatCurrency(value) {

    return "₹" +
        Number(value || 0)
        .toLocaleString(
            "en-IN",
            {
                maximumFractionDigits: 2
            }
        );
}


/* =========================
   HTML SAFETY
========================= */

function escapeHtml(value) {

    return String(
        value ?? ""
    )

    .replace(
        /&/g,
        "&amp;"
    )

    .replace(
        /</g,
        "&lt;"
    )

    .replace(
        />/g,
        "&gt;"
    )

    .replace(
        /"/g,
        "&quot;"
    )

    .replace(
        /'/g,
        "&#039;"
    );
}


/* =========================
   START
========================= */

document.addEventListener(
    "DOMContentLoaded",
    loadAnalytics
);