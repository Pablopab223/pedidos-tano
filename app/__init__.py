import os
from typing import Optional
from flask import Flask
from .models import db


def create_app(config_name: Optional[str] = None) -> Flask:
	app = Flask(__name__, instance_relative_config=True)

	# Asegura la carpeta de instancia (para SQLite)
	os.makedirs(app.instance_path, exist_ok=True)

	# Configuración por entorno
	if config_name is None:
		config_name = os.getenv("APP_ENV", "development").lower()

	if config_name == "production":
		from config import ProductionConfig as Config
	elif config_name == "testing":
		from config import TestingConfig as Config
	else:
		from config import DevelopmentConfig as Config

	app.config.from_object(Config)

	# Normaliza la ruta SQLite si apunta a 'instance/' relativa
	db_uri = app.config.get("SQLALCHEMY_DATABASE_URI", "")
	prefix = "sqlite:///instance/"
	if isinstance(db_uri, str) and db_uri.startswith(prefix):
		rel_name = db_uri[len(prefix):]
		absolute_sqlite = "sqlite:///" + os.path.join(app.instance_path, rel_name)
		app.config["SQLALCHEMY_DATABASE_URI"] = absolute_sqlite

	# Extensiones
	db.init_app(app)

	# Registra rutas
	from .routes import bp as main_bp  # noqa: E402
	app.register_blueprint(main_bp)

	# Crea tablas y migración ligera (añadir columna si falta)
	with app.app_context():
		if app.config.get("CREATE_DB_ON_START", False):
			db.create_all()
			try:
				# Verificar si existe la columna 'location'
				res = db.session.execute(db.text("PRAGMA table_info('orders')")).all()
				cols = {r[1] for r in res}
				if "location" not in cols:
					db.session.execute(db.text("ALTER TABLE orders ADD COLUMN location VARCHAR(32) NOT NULL DEFAULT 'vilanova'"))
					db.session.commit()
			except Exception:
				pass

	return app
