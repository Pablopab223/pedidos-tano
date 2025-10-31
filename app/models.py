from datetime import datetime
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Order(db.Model):
	__tablename__ = "orders"

	id = db.Column(db.Integer, primary_key=True)
	customer_name = db.Column(db.String(120), nullable=False)
	email = db.Column(db.String(120), nullable=True)
	phone = db.Column(db.String(40), nullable=False)
	pickup_datetime = db.Column(db.DateTime, nullable=False)
	product = db.Column(db.String(120), nullable=False)
	quantity = db.Column(db.Integer, nullable=False, default=1)
	message = db.Column(db.Text, nullable=True)
	status = db.Column(db.String(32), nullable=False, default="pendiente")
	location = db.Column(db.String(32), nullable=False, default="vilanova")
	created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

	# Relación con items (para nuevas órdenes multi-producto). Los campos product/quantity quedan para compatibilidad.
	items = db.relationship(
		"OrderItem",
		backref="order",
		cascade="all, delete-orphan",
		lazy="joined",
	)

	def __repr__(self) -> str:
		return f"<Order {self.id} - {self.customer_name} - {self.product}>"


class OrderItem(db.Model):
	__tablename__ = "order_items"

	id = db.Column(db.Integer, primary_key=True)
	order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
	product = db.Column(db.String(120), nullable=False)
	quantity = db.Column(db.Integer, nullable=False, default=1)
