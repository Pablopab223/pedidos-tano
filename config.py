import os


class BaseConfig:
	SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure")
	SQLALCHEMY_DATABASE_URI = os.getenv(
		"DATABASE_URL",
		"sqlite:///instance/pedidos.db",
	)
	SQLALCHEMY_TRACK_MODIFICATIONS = False
	CREATE_DB_ON_START = False


class DevelopmentConfig(BaseConfig):
	DEBUG = True
	CREATE_DB_ON_START = True


class ProductionConfig(BaseConfig):
	DEBUG = False
	CREATE_DB_ON_START = False


class TestingConfig(BaseConfig):
	TESTING = True
	SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
	CREATE_DB_ON_START = True
