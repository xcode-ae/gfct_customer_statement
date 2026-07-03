import frappe
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	data = []

	# 1. Opening balances per customer (invoices before from_date still outstanding)
	opening_map = get_opening_balance(filters)

	# 2. Period outstanding invoices (from_date → to_date)
	invoices = get_invoices(filters)

	# 3. Group period invoices by customer
	by_customer = {}
	for inv in invoices:
		by_customer.setdefault(inv["customer"], []).append(inv)

	# 4. All customers = union of those with opening balance OR period invoices
	all_customers = sorted(set(list(by_customer.keys()) + list(opening_map.keys())))

	# 5. Build per-customer blocks
	for customer in all_customers:
		rows = by_customer.get(customer, [])
		opening = flt(opening_map.get(customer, 0.0))
		customer_name = rows[0]["customer_name"] if rows else customer

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

		# Invoice rows (outstanding > 0, posted in period)
		for inv in rows:
			outstanding = flt(inv["outstanding_amount"])
			running += outstanding
			data.append({
				"date": inv["posting_date"],
				"ref_inv": inv["name"],
				"po_no": inv.get("po_no") or "",
				"invoice_amount": flt(inv["grand_total"]),
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

	# 6. Pending PDC section at the very end of the table
	pdc_rows = get_pending_pdc(filters)
	if pdc_rows:
		# Section header
		data.append({
			"ref_inv": "Pending PDC Cheques (Not Deposited)",
			"bold": 1,
			"indent": 0,
		})

		pdc_running = 0.0
		for pdc in pdc_rows:
			pdc_running += flt(pdc["amount"])
			data.append({
				"customer": pdc["customer"],
				"date": pdc["reference_date"],
				"ref_inv": pdc["reference_no"] or "",
				"outstanding": flt(pdc["amount"]),
				"balance": pdc_running,
				"indent": 1,
			})

		# PDC total row
		data.append({
			"ref_inv": "Total Pending PDC",
			"outstanding": pdc_running,
			"balance": pdc_running,
			"bold": 1,
			"indent": 0,
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
	Returns {customer: sum_outstanding} for submitted Sales Invoices
	posted BEFORE from_date that still have outstanding_amount > 0.
	"""
	conditions = [
		"si.docstatus = 1",
		"si.outstanding_amount > 0",
		"si.posting_date < %(from_date)s",
	]
	values = {"from_date": filters.from_date}

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
			SUM(si.outstanding_amount) AS opening
		FROM `tabSales Invoice` si
		LEFT JOIN `tabCustomer` c ON c.name = si.customer
		WHERE {conditions}
		GROUP BY si.customer
	""".format(conditions=" AND ".join(conditions))

	rows = frappe.db.sql(query, values, as_dict=True)
	return {r["customer"]: flt(r["opening"]) for r in rows}


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


def get_pending_pdc(filters):
	"""
	Returns individual PDC cheque rows that have NOT been deposited/reconciled.
	Source: tabPDC Cheque (header) + tabPDC Cheque Entry Reference (child).

	Notes:
	- reconcelled = 0  means pending  (field name has a typo — double-l, intentional)
	- Use pcr.total_paid, NOT pcr.allocated_amount (allocated_amount is always 0 for pending cheques)
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
			pcr.total_paid      AS amount
		FROM `tabPDC Cheque` pdc
		INNER JOIN `tabPDC Cheque Entry Reference` pcr ON pcr.parent = pdc.name
		WHERE {conditions}
		ORDER BY pcr.party, pdc.reference_date, pdc.name
	""".format(conditions=" AND ".join(conditions))

	return frappe.db.sql(query, values, as_dict=True)
