// Copyright (c) 2025, xcode and contributors
// For license information, please see license.txt

frappe.query_reports["GFCT Customers Statements"] = {
	filters: [
		{
			fieldname: "from_date",
			label: "From Date",
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: "To Date",
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: "Company",
			fieldtype: "Link",
			options: "Company",
			reqd: 0,
		},
		{
			fieldname: "customer",
			label: "Customer",
			fieldtype: "Link",
			options: "Customer",
			reqd: 0,
		},
		{
			fieldname: "customer_group",
			label: "Customer Group",
			fieldtype: "Link",
			options: "Customer Group",
			reqd: 0,
			depends_on: "eval:!doc.customer",
		},
	],

	onload: function(report) {
		// ── Custom print: one page per customer ──────────────────────────────
		// Override print_report so clicking Print opens a styled window
		// with each customer on its own page (screen view unchanged).
		const _orig_print = report.print_report
			? report.print_report.bind(report)
			: null;

		report.print_report = function(print_settings) {
			const data = report.data || [];
			if (!data.length) {
				frappe.msgprint(__("No data to print."));
				return;
			}

			// ── Group flat data into per-customer sections ───────────────────
			const sections = [];
			let current = null;
			for (const row of data) {
				// Customer header rows have indent === 0
				if (row.indent === 0 && row.customer) {
					if (current) sections.push(current);
					current = {
						customer: row.customer,
						customer_name: row.ref_inv || row.customer,
						rows: [],
					};
				} else if (current) {
					current.rows.push(row);
				}
			}
			if (current) sections.push(current);

			// ── Helpers ──────────────────────────────────────────────────────
			const fmt_num = (v) => {
				if (v === "" || v === null || v === undefined) return "";
				const n = parseFloat(v);
				if (isNaN(n)) return "";
				return n.toLocaleString("en-US", {
					minimumFractionDigits: 2,
					maximumFractionDigits: 2,
				});
			};
			const fmt_date = (d) =>
				d ? frappe.datetime.str_to_user(d) : "";

			const company =
				report.get_filter_value
					? report.get_filter_value("company") || ""
					: "";
			const from_d = report.get_filter_value
				? frappe.datetime.str_to_user(
						report.get_filter_value("from_date") || ""
					)
				: "";
			const to_d = report.get_filter_value
				? frappe.datetime.str_to_user(
						report.get_filter_value("to_date") || ""
					)
				: "";

			// ── Build HTML ───────────────────────────────────────────────────
			let html = `<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<title>GFCT Customers Statements</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: Arial, sans-serif; font-size: 9pt; color: #222; }

  /* Each customer fills one printed page */
  .cust-section {
    padding: 18px 22px 22px;
    page-break-after: always;
    min-height: 97vh;
    display: flex;
    flex-direction: column;
  }
  .cust-section:last-child { page-break-after: avoid; }

  /* Report title (repeated per customer) */
  .rpt-title { text-align: center; margin-bottom: 10px; }
  .rpt-title h3 { font-size: 14pt; color: #1a3d5c; }
  .rpt-title p  { font-size: 9pt; color: #555; margin-top: 2px; }

  /* Customer header bar */
  .cust-hdr {
    background: #1a3d5c;
    color: #fff;
    padding: 7px 12px;
    margin-bottom: 8px;
    border-radius: 3px;
    display: flex;
    align-items: baseline;
    gap: 16px;
  }
  .cust-hdr .cname { font-size: 11pt; font-weight: bold; }
  .cust-hdr .ccode { font-size: 9pt; opacity: 0.82; }

  /* Transactions table */
  table { width: 100%; border-collapse: collapse; margin-bottom: 6px; }
  thead th {
    background: #2c5f8a;
    color: #fff;
    padding: 5px 7px;
    font-size: 8.5pt;
    text-align: left;
  }
  thead th.r { text-align: right; }
  tbody td { padding: 3px 7px; border-bottom: 1px solid #e8e8e8; font-size: 8.5pt; }
  tbody td.r { text-align: right; }
  tr.row-bold td { font-weight: bold; background: #f0f4f8; }
  tr.row-pdc-hdr td {
    font-weight: bold;
    color: #8b0000;
    background: #fff5f5;
    border-top: 1px solid #f5c6cb;
  }
  tr.row-pdc td { color: #555; font-style: italic; }

  /* Signature section */
  .sig-section {
    display: flex;
    justify-content: space-around;
    margin-top: auto;
    padding-top: 18px;
    border-top: 1px solid #ccc;
  }
  .sig-box { text-align: center; min-width: 160px; }
  .sig-title { font-weight: bold; font-size: 9pt; margin-bottom: 38px; }
  .sig-line { border-top: 1px solid #000; padding-top: 4px; font-weight: bold; font-size: 8.5pt; }

  @media print {
    .cust-section { page-break-after: always; }
    .cust-section:last-child { page-break-after: avoid; }
  }
</style>
</head><body>`;

			sections.forEach((section) => {
				html += `<div class="cust-section">`;

				// Report title header (repeats on each customer page)
				html += `<div class="rpt-title">
  <h3>Customers Statement</h3>
  <p>${company}${from_d ? " &nbsp;|&nbsp; " + from_d + " to " + to_d : ""}</p>
</div>`;

				// Customer header bar
				html += `<div class="cust-hdr">
  <span class="cname">${section.customer_name}</span>
  <span class="ccode">Code: ${section.customer}</span>
</div>`;

				// Transactions table
				html += `<table>
  <thead><tr>
    <th>Date</th>
    <th>Invoice / Ref #</th>
    <th>PO #</th>
    <th class="r">Invoice Amount</th>
    <th class="r">Outstanding</th>
    <th class="r">Balance</th>
  </tr></thead>
  <tbody>`;

				let in_pdc = false;
				for (const row of section.rows) {
					const ref = row.ref_inv || "";
					if (ref === "Pending PDC Cheques (Not Deposited)") {
						in_pdc = true;
						html += `<tr class="row-pdc-hdr"><td colspan="6">${ref}</td></tr>`;
					} else if (in_pdc) {
						html += `<tr class="row-pdc">
  <td>${fmt_date(row.date)}</td>
  <td>${ref}</td>
  <td>PDC Cheque</td>
  <td class="r"></td>
  <td class="r">${fmt_num(row.outstanding)}</td>
  <td class="r"></td>
</tr>`;
					} else if (row.bold) {
						html += `<tr class="row-bold">
  <td>${fmt_date(row.date)}</td>
  <td>${ref}</td>
  <td></td>
  <td class="r"></td>
  <td class="r">${fmt_num(row.outstanding)}</td>
  <td class="r">${fmt_num(row.balance)}</td>
</tr>`;
					} else {
						html += `<tr>
  <td>${fmt_date(row.date)}</td>
  <td>${ref}</td>
  <td>${row.po_no || ""}</td>
  <td class="r">${fmt_num(row.invoice_amount)}</td>
  <td class="r">${fmt_num(row.outstanding)}</td>
  <td class="r">${fmt_num(row.balance)}</td>
</tr>`;
					}
				}

				html += `  </tbody>
</table>`;

				// Signature block (appears on every customer page)
				html += `<div class="sig-section">
  <div class="sig-box">
    <div class="sig-title">CHECKED AND VERIFIED</div>
    <div class="sig-line">Signature &amp; Stamp</div>
  </div>
  <div class="sig-box">
    <div class="sig-title">CHECKED AND VERIFIED</div>
    <div class="sig-line">Signature &amp; Stamp</div>
  </div>
</div>`;

				html += `</div>`; // .cust-section
			});

			html += `</body></html>`;

			// Open in new window and trigger browser print dialog
			const w = window.open("", "_blank", "width=960,height=720");
			if (!w) {
				frappe.msgprint(__(
					"Pop-up blocked. Please allow pop-ups for this site and try again."
				));
				return;
			}
			w.document.open();
			w.document.write(html);
			w.document.close();
			w.focus();
			setTimeout(() => { w.print(); }, 700);
		};
		// ── End custom print ─────────────────────────────────────────────────
	},
};
