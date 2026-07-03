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
		// Inject CSS for signature section (print only)
		if (!document.getElementById('report-signature-style')) {
			const style = document.createElement('style');
			style.id = 'report-signature-style';
			style.textContent = `
				@media print {
					.report-signature-section {
						display: flex !important;
						justify-content: space-between;
						margin-top: 60px;
						padding-top: 30px;
						border-top: 1px solid #d1d8dd;
						page-break-inside: avoid;
					}
					.signature-box {
						text-align: center;
						min-width: 200px;
					}
					.signature-title {
						font-weight: bold;
						margin-bottom: 50px;
						font-size: 11pt;
					}
					.signature-label {
						border-top: 1px solid #000;
						padding-top: 5px;
						font-weight: bold;
						font-size: 10pt;
					}
				}
				@media screen {
					.report-signature-section {
						display: none;
					}
				}
			`;
			document.head.appendChild(style);
		}

		// Function to add signature section
		const addSignatureSection = () => {
			const wrapper = report.page.main.find('.page-content');

			if (wrapper && wrapper.length && !wrapper.find('.report-signature-section').length) {
				console.log("Adding signature section to the report...");
				const signatureHTML = `
					<div class="report-signature-section">
						<div class="signature-box">
							<div class="signature-title">CHECKED AND VERIFIED</div>
							<div class="signature-label">Signature & Stamp</div>
						</div>
						<div class="signature-box">
							<div class="signature-title">CHECKED AND VERIFIED</div>
							<div class="signature-label">Signature & Stamp</div>
						</div>
					</div>
				`;
				wrapper.append(signatureHTML);
			}
			else{
				console.log("Signature section already exists or wrapper not found.");
			}
		};

		// Add on initial load and after refresh
		setTimeout(addSignatureSection, 500);

		// Re-add after report refresh
		report.page.main.on('report:refresh', addSignatureSection);
	},
};
