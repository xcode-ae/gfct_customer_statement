import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = []

	# 1. Opening balances per customer (invoices + unallocated Pay PEs before from_date)
	opening_map = get_opening_balance(filters)

	# 2. Period outstanding invoices (from_date → to_date)
	invoices = get_invoices(filters)

	# 3. Period unallocated Pay PEs (company paid customer, customer owes back)
	pay_entries = get_pay_entries(filters)

	# 4a. Period unallocated Receive PEs (customer advance / credit not yet applied to an invoice)
	receive_advances = get_receive_advances(filters)

	# 4. Merge invoices, pay entries, and receive advances per customer, sorted by date
	by_customer = {}
	for inv in invoices:
		inv["_row_type"] = "invoice"
		by_customer.setdefault(inv["customer"], []).append(inv)
	for pe in pay_entries:
		pe["_row_type"] = "pay_pe"
		by_customer.setdefault(pe["customer"], []).append(pe)
	for adv in receive_advances:
		adv["_row_type"] = "receive_adv"
		by_customer.setdefault(adv["customer"], []).append(adv)
	for cust in by_customer:
		by_customer[cust].sort(key=lambda r: (r.get("posting_date") or "", r.get("name") or ""))

	# 5. All customers = union of opening balance, invoices, pay entries
	all_customers = sorted(set(list(by_customer.keys()) + list(opening_map.keys())))

	# 5a. PDC rows grouped by customer (shown inline after each customer's closing balance)
	pdc_rows = get_pending_pdc(filters)
	pdc_by_customer = {}
	for pdc in pdc_rows:
		pdc_by_customer.setdefault(pdc["customer"], []).append(pdc)

	# 6. Build per-customer blocks
	for customer in all_customers:
		rows = by_customer.get(customer, [])
		opening = flt(opening_map.get(customer, 0.0))
		inv_rows = [r for r in rows if r.get("_row_type") == "invoice"]
		customer_name = inv_rows[0]["customer_name"] if inv_rows else customer

		# Customer header row
		data.append({
			"customer": customer,
			"ref_inv": customer_name,
			"bold": 1,
			"indent": 0,
		})

		# Opening balance row (always shown — even if 0.00)
		data.append({
			"date": filters.from_date,
			"ref_inv": "Opening Balance",
			"outstanding": opening,
			"balance": opening,
			"bold": 1,
			"indent": 1,
		})

		running = opening

		# Invoice + Pay PE rows merged by date
		for row in rows:
			if row["_row_type"] == "invoice":
				outstanding = flt(row["outstanding_amount"])
				running += outstanding
				data.append({
					"date": row["posting_date"],
					"ref_inv": row["name"],
					"po_no": row.get("po_no") or "",
					"invoice_amount": flt(row["grand_total"]),
					"outstanding": outstanding,
					"balance": running,
					"indent": 1,
				})
			elif row["_row_type"] == "pay_pe":
				outstanding = flt(row["outstanding_amount"])
				running += outstanding
				data.append({
					"date": row["posting_date"],
					"ref_inv": row["name"],
					"po_no": "Pay to Customer",
					"outstanding": outstanding,
					"balance": running,
					"indent": 1,
				})
			else:  # receive_adv
				outstanding = flt(row["outstanding_amount"])  # negative value (credit)
				running += outstanding
				data.append({
					"date": row["posting_date"],
					"ref_inv": row["name"],
					"po_no": "Customer Advance (Unallocated)",
					"outstanding": outstanding,
					"balance": running,
					"indent": 1,
				})

		# Closing balance row
		data.append({
			"date": filters.to_date,
			"ref_inv": "Closing Balance",
			"outstanding": running,
			"balance": running,
			"bold": 1,
			"indent": 1,
		})

		# PDC rows for this customer (shown right after closing balance)
		cust_pdcs = pdc_by_customer.get(customer, [])
		if cust_pdcs:
			data.append({
				"ref_inv": "Pending PDC Cheques (Not Deposited)",
				"bold": 1,
				"indent": 1,
			})
			for pdc in cust_pdcs:
				data.append({
					"date": pdc["reference_date"],
					"ref_inv": pdc["reference_no"] or "",
					"po_no": "PDC",
					"outstanding": flt(pdc["amount"]),
					"balance": "",
					"indent": 1,
				})

	return columns, data


def get_columns():
	return [
		{
			"label": "Customer",
			"fieldname": "customer",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 120,
		},
		{
			"label": "Date",
			"fieldname": "date",
			"fieldtype": "Date",
			"width": 100,
		},
		{
			"label": "Invoice / Ref #",
			"fieldname": "ref_inv",
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"label": "PO",
			"fieldname": "po_no",
			"fieldtype": "Data",
			"width": 120,
		},
		{
			"label": "Invoice Amount",
			"fieldname": "invoice_amount",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": "Outstanding",
			"fieldname": "outstanding",
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"label": "Balance",
			"fieldname": "balance",
			"fieldtype": "Currency",
			"width": 130,
		},
	]


def get_opening_balance(filters):
	"""
	Returns {customer: sum_outstanding} for:
	  - submitted Sales Invoices posted BEFORE from_date still outstanding
	  - unallocated 'Pay' type Payment Entries posted BEFORE from_date
	"""
	values = {"from_date": filters.from_date}

	# SI conditions
	si_conditions = [
		"si.docstatus = 1",
		"si.outstanding_amount > 0",
		"si.posting_date < %(from_date)s",
	]
	if filters.get("company"):
		si_conditions.append("si.company = %(company)s")
		values["company"] = filters.company
	if filters.get("customer"):
		si_conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.customer
	if filters.get("customer_group"):
		si_conditions.append("c.customer_group = %(customer_group)s")
		values["customer_group"] = filters.customer_group

	si_query = """
		SELECT si.customer, SUM(si.outstanding_amount) AS opening
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {conditions}
		GROUP BY si.customer
	""".format(conditions=" AND ".join(si_conditions))

	result = {}
	for r in frappe.db.sql(si_query, values, as_dict=True):
		result[r["customer"]] = flt(r["opening"])

	# Pay PE opening balance via Payment Ledger Entry (PLE) — same logic as AR report.
	# pe.unallocated_amount can be stale; PLE is the authoritative net outstanding.
	pe_conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Pay'",
		"pe.party_type = 'Customer'",
		"pe.posting_date < %(from_date)s",
		"ple.party_type = 'Customer'",
		"ple.voucher_type = 'Payment Entry'",
		"ple.delinked = 0",
		"ple.posting_date < %(from_date)s",
	]
	if filters.get("company"):
		pe_conditions.append("pe.company = %(company)s")
	if filters.get("customer"):
		pe_conditions.append("ple.party = %(customer)s")

	pe_query = """
		SELECT ple.party AS customer, SUM(ple.amount) AS opening
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Ledger Entry` ple ON ple.against_voucher_no = pe.name
		WHERE {conditions}
		GROUP BY ple.party, ple.against_voucher_no
		HAVING SUM(ple.amount) > 0
	""".format(conditions=" AND ".join(pe_conditions))

	for r in frappe.db.sql(pe_query, values, as_dict=True):
		result[r["customer"]] = result.get(r["customer"], 0.0) + flt(r["opening"])

	# Receive PE opening balance: unallocated customer advances before from_date.
	# These appear in PLE as self-referencing entries (against_voucher_no = voucher_no)
	# with a negative amount (credit to the customer). AR report includes these.
	recv_conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Receive'",
		"pe.party_type = 'Customer'",
		"pe.posting_date < %(from_date)s",
		"ple.party_type = 'Customer'",
		"ple.voucher_type = 'Payment Entry'",
		"ple.against_voucher_no = pe.name",
		"ple.delinked = 0",
		"ple.posting_date < %(from_date)s",
	]
	if filters.get("company"):
		recv_conditions.append("pe.company = %(company)s")
	if filters.get("customer"):
		recv_conditions.append("ple.party = %(customer)s")

	recv_query = """
		SELECT ple.party AS customer, SUM(ple.amount) AS opening
		FROL `tabPayment Entry` pe
		INNER JOIN `tabPayment Ledger Entry` ple ON ple.voucher_no = pe.name
		WHERE {conditions}
		GROUP BY ple.party, ple.against_voucher_no
		HAVING SUM(ple.amount) < 0
	""".format(conditions=" AND ".join(recv_conditions))

	for r in frappe.db.sql(recv_query, values, as_dict=True):
		result[r["customer"]] = result.get(r["customer"], 0.0) + flt(r["opening"])

	return result


def get_invoices(filters):
	"""
	Returns submitted Sales Invoices with outstanding_amount > 0
	posted between from_date and to_date.
	Selects both grand_total (Invoice Amount) and outstanding_amount.
	"""
	conditions = [
		"si.docstatus = 1",
		"si.outstanding_amount > 0",
	]
	values = {}

	if filters.get("from_date"):
		conditions.append("si.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("si.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("company"):
		conditions.append("si.company = %(company)s")
		values["company"] = filters.company

	if filters.get("customer"):
		conditions.append("si.customer = %(customer)s")
		values["customer"] = filters.customer

	if filters.get("customer_group"):
		conditions.append("c.customer_group = %(customer_group)s")
		values["customer_group"] = filters.customer_group

	query = """
		SELECT
			si.customer,
			si.customer_name,
			si.posting_date,
			si.name,
			si.po_no,
			si.grand_total,
			si.outstanding_amount
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {conditions}
		ORDER BY si.customer, si.posting_date, si.name
	""".format(conditions=" AND ".join(conditions))

	return frappe.db.sql(query, values, as_dict=True)


def get_pay_entries(filters):
	"""
	Returns 'Pay' type Payment Entries posted in the report period that still
	have a net outstanding balance — using Payment Ledger Entry (PLE) as the
	source of truth, exactly as the AR report does.

	pe.unallocated_amount can be stale when a payment is settled through
	Payment Reconciliation or a direct return PE. PLE always reflects the
	current net (positive entries minus any settling negative entries).
	"""
	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Pay'",
		"pe.party_type = 'Customer'",
		"ple.party_type = 'Customer'",
		"ple.voucher_type = 'Payment Entry'",
		"ple.delinked = 0",
	]
	values = {}

	if filters.get("from_date"):
		conditions.append("pe.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("pe.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("company"):
		conditions.append("pe.company = %(company)s")
		values["company"] = filters.company

	if filters.get("customer"):
		conditions.append("ple.party = %(customer)s")
		values["customer"] = filters.customer

	query = """
		SELECT
			ple.party           AS customer,
			pe.posting_date,
			ple.against_voucher_no AS name,
			SUM(ple.amount)     AS outstanding_amount
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Ledger Entry` ple ON ple.against_voucher_no = pe.name
		WHERE {conditions}
		GROUP BY ple.party, ple.against_voucher_no, pe.posting_date
		HAVING SUM(ple.amount) > 0
		ORDER BY ple.party, pe.posting_date, ple.against_voucher_no
	""".format(conditions=" AND ".join(conditions))

	return frappe.db.sql(query, values, as_dict=True)


def get_receive_advances(filters):
	"""
	Returns 'Receive' type Payment Entries posted in the report period that have
	an unallocated amount (customer advance / credit not yet applied to an invoice).

	In PLE, the unallocated portion appears as a self-referencing entry:
	    ple.voucher_no = pe.name  AND  ple.against_voucher_no = pe.name
	with a negative amount (credit to the customer).

	The AR report shows these as negative outstanding rows, reducing the balance.
	We must match that behaviour.
	"""
	conditions = [
		"pe.docstatus = 1",
		"pe.payment_type = 'Receive'",
		"pe.party_type = 'Customer'",
		"ple.party_type = 'Customer'",
		"ple.voucher_type = 'Payment Entry'",
		"ple.against_voucher_no = pe.name",
		"ple.delinked = 0",
	]
	values = {}

	if filters.get("from_date"):
		conditions.append("pe.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date

	if filters.get("to_date"):
		conditions.append("pe.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date

	if filters.get("company"):
		conditions.append("pe.company = %(company)s")
		values["company"] = filters.company

	if filters.get("customer"):
		conditions.append("ple.party = %(customer)s")
		values["customer"] = filters.customer

	query = """
		SELECT
			ple.party               AS customer,
			pe.posting_date,
			ple.against_voucher_no  AS name,
			SUM(ple.amount)         AS outstanding_amount
		FROM `tabPayment Entry` pe
		INNER JOIN `tabPayment Ledger Entry` ple ON ple.voucher_no = pe.name
		WHERE {conditions}
		GROUP BY ple.party, ple.against_voucher_no, pe.posting_date
		HAVING SUM(ple.amount) < 0
		ORDER BY ple.party, pe.posting_date, ple.against_voucher_no
	""".format(conditions=" AND ".join(conditions))

	return frappe.db.sql(query, values, as_dict=True)


def get_pending_pdc(filters):
	"""
	Returns individual PDC cheque rows that have NOT been deposited/reconciled.
	Source: tabPDC Cheque (header) + tabPDC Cheque Entry Reference (child).

	Notes:
	- reconcelled = 0  means pending  (field name has a typo — double-l, intentional)
	- Use pdc.amount (full cheque amount), NOT pcr.total_paid (per-customer allocated portion)
	"""
	conditions = [
		"pdc.docstatus = 1",
		"pdc.reconcelled = 0",
	]
	values = {}

	if filters.get("company"):
		conditions.append("pdc.company = %(company)s")
		values["company"] = filters.company

	if filters.get("customer"):
		conditions.append("pcr.party = %(customer)s")
		values["customer"] = filters.customer

	query = """
		SELECT
			pcr.party           AS customer,
			pcr.customer_name,
			pdc.reference_no,
			pdc.reference_date,
			pdc.amount          AS amount
		FROM `tabPDC Cheque` pdc
		INNER JOIN `tabPDC Cheque Entry Reference` pcr ON pcr.parent = pdc.name
		WHERE {conditions}
		ORDER BY pcr.party, pdc.reference_date, pdc.name
	""".format(conditions=" AND ".join(conditions))

	return frappe.db.sql(query, values, as_dict=True)
