from datetime import datetime, timedelta
from io import StringIO
import csv
import json
from flask import Blueprint, render_template, request, redirect, url_for, flash, make_response, abort
import os
from .models import db, Order, OrderItem


bp = Blueprint("main", __name__)

# Estados permitidos de pedido (completado == listo)
ALLOWED_STATUSES = ("pendiente", "completado", "entregado")
ALLOWED_LOCATIONS = ("vilanova", "hospital")
ALLOWED_PRODUCTS = (
	"chocotano",
	"croissant farcit",
	"mamelleta",
	"pastiset tomaca",
	"pastiset pessols",
	"pastissets espinacs",
	"tartas",
	"otro",
)


@bp.get("/")
def index():
	# Uso interno simple: llevar directamente al panel de pedidos
	return redirect(url_for("main.admin_pedidos"))


@bp.route("/admin/pedidos/nuevo", methods=["GET", "POST"])
def admin_pedido_nuevo():
	if request.method == "GET":
		return render_template("order_form.html")

	# POST: validación con cesta de items
	customer_name = (request.form.get("customer_name") or "").strip()
	phone = (request.form.get("phone") or "").strip()
	location = (request.form.get("location") or "").strip().lower()
	message = (request.form.get("message") or "").strip()
	pickup_date = (request.form.get("pickup_date") or "").strip()
	pickup_time = (request.form.get("pickup_time") or "").strip()
	items_json = request.form.get("items_json") or "[]"

	errors: list[str] = []
	if not customer_name:
		errors.append("El nombre es obligatorio.")
	if not phone:
		errors.append("El teléfono es obligatorio.")
	if location not in ALLOWED_LOCATIONS:
		errors.append("Selecciona un local válido.")

	try:
		pickup_datetime = datetime.fromisoformat(f"{pickup_date}T{pickup_time}")
	except ValueError:
		errors.append("Fecha u hora de retiro inválidas.")
		pickup_datetime = datetime.utcnow()

	try:
		items = json.loads(items_json)
	except json.JSONDecodeError:
		errors.append("Cesta inválida.")
		items = []

	valid_items: list[dict] = []
	for i in items:
		p = str((i.get("product") or "")).strip().lower()
		q_raw = i.get("quantity")
		custom = str((i.get("custom_name") or "")).strip()
		try:
			q = int(q_raw)
		except Exception:
			q = 0
		if q < 1:
			errors.append("Cada item debe tener cantidad >= 1.")
			continue
		if p not in ALLOWED_PRODUCTS:
			errors.append("Producto inválido en la cesta.")
			continue
		if p == "otro":
			if not custom:
				errors.append("Falta especificar el producto en 'Otro'.")
				continue
			name_final = custom
		else:
			name_final = p
		valid_items.append({"product": name_final, "quantity": q})

	if not valid_items:
		errors.append("La cesta debe tener al menos un producto.")

	if errors:
		for e in errors:
			flash(e, "error")
		return render_template("order_form.html", form=request.form)

	order = Order(
		customer_name=customer_name,
		email=None,
		phone=phone,
		pickup_datetime=pickup_datetime,
		product=valid_items[0]["product"],  # compatibilidad mínima
		quantity=valid_items[0]["quantity"],
		message=message or None,
		location=location,
	)
	db.session.add(order)
	db.session.flush()

	for it in valid_items:
		item = OrderItem(order_id=order.id, product=it["product"], quantity=it["quantity"])
		db.session.add(item)

	db.session.commit()

	flash("Pedido creado.", "success")
	return redirect(url_for("main.admin_pedidos"))


@bp.get("/admin/pedidos")
def admin_pedidos():
	# Solo pedidos activos (no entregados) y ordenar por fecha/hora de retiro
	orders = (
		Order.query
		.filter(Order.status != "entregado")
		.order_by(Order.pickup_datetime.asc(), Order.created_at.desc())
		.all()
	)

	# Agrupación por día de retiro para separadores visuales en la tabla
	groups: list[dict] = []
	current_label: str | None = None
	# Nombres de días en español (lunes=0)
	weekday_names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
	for o in orders:
		day_name = weekday_names[o.pickup_datetime.weekday()]
		label = f"{day_name} {o.pickup_datetime.strftime('%d/%m/%Y')}"
		if label != current_label:
			groups.append({"label": label, "orders": []})
			current_label = label
		groups[-1]["orders"].append(o)

	return render_template("admin_orders.html", groups=groups, allowed_statuses=ALLOWED_STATUSES)


@bp.get("/admin/pedidos.csv")
def admin_pedidos_csv():
	orders = Order.query.order_by(Order.created_at.desc()).all()
	output = StringIO()
	writer = csv.writer(output)
	writer.writerow(["id", "created_at", "customer_name", "items", "pickup_datetime", "phone", "location", "status", "message"])
	for o in orders:
		items_text = ", ".join([f"{it.product} x{it.quantity}" for it in (o.items or [])]) if hasattr(o, 'items') else f"{o.product} x{o.quantity}"
		writer.writerow([
			o.id,
			o.created_at.strftime('%d/%m/%Y %H:%M'),
			o.customer_name,
			items_text,
			o.pickup_datetime.strftime('%d/%m/%Y %H:%M'),
			o.phone,
			o.location,
			o.status,
			o.message or "",
		])
	csv_data = output.getvalue()
	resp = make_response(csv_data)
	resp.headers["Content-Type"] = "text/csv; charset=utf-8"
	resp.headers["Content-Disposition"] = "attachment; filename=pedidos.csv"
	return resp


@bp.post("/admin/pedidos/<int:order_id>/status")
def update_order_status(order_id: int):
	new_status = (request.form.get("status") or "").strip().lower()
	if new_status not in ALLOWED_STATUSES:
		flash("Estado inválido.", "error")
		return redirect(url_for("main.admin_pedidos"))

	order = Order.query.get_or_404(order_id)
	order.status = new_status
	db.session.commit()
	flash("Estado actualizado.", "success")
	# Si se marcó como entregado, mantener UX redirigiendo a la vista actual
	return redirect(url_for("main.admin_pedidos"))


@bp.get("/admin/resumen")
def admin_resumen():
	"""Resumen mensual de pedidos entregados.

	Parámetro opcional ?month=YYYY-MM para seleccionar mes.
	"""
	month_param = (request.args.get("month") or "").strip()
	try:
		if month_param:
			start = datetime.fromisoformat(month_param + "-01")
		else:
			now = datetime.utcnow()
			start = datetime(year=now.year, month=now.month, day=1)
	except Exception:
		now = datetime.utcnow()
		start = datetime(year=now.year, month=now.month, day=1)

	# Calcular fin de mes
	if start.month == 12:
		end = datetime(year=start.year + 1, month=1, day=1)
	else:
		end = datetime(year=start.year, month=start.month + 1, day=1)

	# Solo entregados en el mes según fecha de retiro
	delivered = (
		Order.query
		.filter(Order.status == "entregado")
		.filter(Order.pickup_datetime >= start, Order.pickup_datetime < end)
		.order_by(Order.pickup_datetime.asc())
		.all()
	)

	# Agrupar por día (con nombre del día)
	weekday_names = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")
	groups: list[dict] = []
	current_label: str | None = None
	for o in delivered:
		day_name = weekday_names[o.pickup_datetime.weekday()]
		label = f"{day_name} {o.pickup_datetime.strftime('%d/%m/%Y')}"
		if label != current_label:
			groups.append({"label": label, "orders": []})
			current_label = label
		groups[-1]["orders"].append(o)

	# Métricas simples
	total_orders = len(delivered)
	# Conteo por producto (sumando cantidades)
	product_counts: dict[str, int] = {}
	for o in delivered:
		if getattr(o, "items", None):
			for it in o.items:
				product_counts[it.product] = product_counts.get(it.product, 0) + int(it.quantity or 0)
		else:
			product_counts[o.product] = product_counts.get(o.product, 0) + int(o.quantity or 0)

	# Conteo por local
	location_counts: dict[str, int] = {}
	for o in delivered:
		location_counts[o.location] = location_counts.get(o.location, 0) + 1

	# Orden y máximos para gráficos sencillos
	sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)
	sorted_locations = sorted(location_counts.items(), key=lambda x: x[1], reverse=True)
	max_product_count = max([c for _, c in sorted_products], default=0)
	max_location_count = max([c for _, c in sorted_locations], default=0)

	# Datos para donuts (ruedas) con CSS conic-gradient
	total_location = sum([c for _, c in sorted_locations]) or 0
	total_product_units = sum([c for _, c in sorted_products]) or 0

	# Reducimos productos a top 5 + Otros para una rueda legible
	_top5 = sorted_products[:5]
	rest_units = sum([c for _, c in sorted_products[5:]])
	if rest_units > 0:
		_top5 = _top5 + [("Otros", rest_units)]

	palette = ["#111827", "#6B7280", "#A3A3A3", "#D4D4D4", "#22C55E", "#F59E0B"]

	def build_segments(pairs: list[tuple[str, int]], total: int) -> tuple[list[dict], str]:
		segments: list[dict] = []
		acc = 0.0
		for idx, (label, count) in enumerate(pairs):
			pct = (float(count) / float(total)) if total else 0.0
			start = acc
			end = acc + pct
			color = palette[idx % len(palette)]
			segments.append({
				"label": label,
				"count": int(count),
				"start": start,
				"end": end,
				"color": color,
			})
			acc = end
		stops = []
		for s in segments:
			stops.append(f"{s['color']} {round(s['start']*100,2)}% {round(s['end']*100,2)}%")
		gradient = "conic-gradient(" + ", ".join(stops) + ")"
		return segments, gradient

	location_segments, location_gradient = build_segments(sorted_locations, total_location)
	product_segments, product_gradient = build_segments(_top5, sum([c for _, c in _top5]) or 0)

	month_label = start.strftime('%m/%Y')
	return render_template(
		"summary.html",
		groups=groups,
		month_label=month_label,
		total_orders=total_orders,
		product_counts=product_counts,
		location_counts=location_counts,
		sorted_products=sorted_products,
		sorted_locations=sorted_locations,
		max_product_count=max_product_count,
		max_location_count=max_location_count,
		location_segments=location_segments,
		location_gradient=location_gradient,
		total_location=total_location,
		product_segments=product_segments,
		product_gradient=product_gradient,
		total_product_units=total_product_units,
	)


@bp.get("/admin/dev/seed-demo")
def seed_demo():
	"""Genera datos de demostración (solo desarrollo)."""
	if (os.getenv("APP_ENV", "development").lower() == "production"):
		abort(404)

	# Semillas: varios pedidos en estado pendiente/completado y entregado
	names = [
		"Ana", "Luis", "Marta", "Pablo", "Lucía", "Carlos", "Nora", "Dani", "Sergio", "Irene",
	]
	customs = [
		"tarta queso", "tarta choc", "pastissets espinacs", "croissant farcit", "pastiset tomaca",
	]

	base = datetime.utcnow()

	def add_order(customer: str, pickup_dt: datetime, location: str, status: str, items: list[tuple[str, int]]):
		order = Order(
			customer_name=customer,
			email=None,
			phone="+34 600 000 000",
			pickup_datetime=pickup_dt,
			product=items[0][0],
			quantity=items[0][1],
			message=None,
			location=location,
			status=status,
		)
		db.session.add(order)
		db.session.flush()
		for prod, qty in items:
			it = OrderItem(order_id=order.id, product=prod, quantity=qty)
			db.session.add(it)

	# Activos (pendiente/completado) próximos 3 días
	for i in range(15):
		day_offset = i % 3
		pickup = (base + timedelta(days=day_offset)).replace(hour=9 + (i % 8), minute=15*(i % 4), second=0, microsecond=0)
		loc = ALLOWED_LOCATIONS[i % len(ALLOWED_LOCATIONS)]
		status = "pendiente" if i % 3 != 0 else "completado"
		items = [
			(customs[i % len(customs)], 1 + (i % 3)),
			("chocotano", 1),
		]
		add_order(names[i % len(names)], pickup, loc, status, items)

	# Entregados del mes actual (resumen)
	start_month = datetime(year=base.year, month=base.month, day=1)
	for i in range(25):
		pickup = (start_month + timedelta(days=(i % 20))).replace(hour=8 + (i % 9), minute=30, second=0, microsecond=0)
		loc = ALLOWED_LOCATIONS[(i + 1) % len(ALLOWED_LOCATIONS)]
		status = "entregado"
		items = [
			("pastissets espinacs", 2 + (i % 4)),
			("pastiset tomaca", 1 + (i % 2)),
		]
		add_order(names[(i + 3) % len(names)], pickup, loc, status, items)

	db.session.commit()
	flash("Datos de demostración generados.", "success")
	return redirect(url_for("main.admin_pedidos"))
