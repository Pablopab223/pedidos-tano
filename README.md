# Pastelería Tano - Panel interno (Flask + Tailwind)

Panel interno para registrar y gestionar pedidos de la pastelería (sustituye el papel). Sin autenticación: el dependiente usa el ordenador de la tienda.

## Puesta en marcha rápida (Windows)
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item env.example .env
flask --app wsgi run --debug
```
Visita `http://127.0.0.1:5000`.

## Flujo de uso
- Ver pedidos: `/admin/pedidos`
- Crear pedido: `/admin/pedidos/nuevo`
- Cambiar estado: en la tabla (pendiente, listo, entregado)
- Exportar CSV: `/admin/pedidos.csv`

## Variables (.env)
```
APP_ENV=development
SECRET_KEY=cambia-esta-clave
DATABASE_URL=sqlite:///instance/pedidos.db
```

## Notas
- Se crea la base de datos automáticamente en desarrollo.
- Para producción, configura `APP_ENV=production` y una base de datos gestionada.
