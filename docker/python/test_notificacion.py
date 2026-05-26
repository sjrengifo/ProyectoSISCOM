"""
test_notificacion.py — Inyecta una alerta de prueba para verificar
que el canal de notificaciones (correo) esta correctamente configurado.

Uso desde Docker:
  docker compose run --rm alertas python /app/docker/python/test_notificacion.py

Por que existe este script:
  El servicio de alertas evalua umbrales agronomicos sobre los indicadores
  calculados por Node-RED. Dependiendo de las condiciones simuladas, puede
  que no se genere ninguna alerta real durante una sesion de prueba corta.
  Este script envia directamente un correo de prueba sin depender de los
  datos de los sensores, permitiendo verificar la configuracion SMTP de
  forma aislada.
"""
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587
SMTP_USER     = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
DEST_EMAIL    = os.environ.get("SMTP_DEST", SMTP_USER)   # por defecto se envia a si mismo

def main():
    if not SMTP_USER or not SMTP_PASSWORD:
        print("ERROR: Variables SMTP_USER y SMTP_PASSWORD no configuradas.")
        print("       Edita docker/.env con tus credenciales de Gmail.")
        sys.exit(1)

    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    subject = "[SISCOM] Alerta de prueba — sistema funcionando correctamente"
    body = f"""\
<html><body style="font-family:Arial,sans-serif;max-width:600px;">
<h2 style="color:#e74c3c;">🚨 ALERTA DE PRUEBA — SISCOM</h2>
<p>Este correo confirma que el servicio de notificaciones esta correctamente configurado.</p>
<table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%">
  <tr style="background:#f2f2f2"><th>Campo</th><th>Valor</th></tr>
  <tr><td><b>Parcela</b></td><td>parcela_1 — Palmira (Valle del Cauca)</td></tr>
  <tr><td><b>Cultivo</b></td><td>Caña de azucar</td></tr>
  <tr><td><b>Variable</b></td><td>Temperatura del aire</td></tr>
  <tr><td><b>Valor medido</b></td><td>38.5 °C</td></tr>
  <tr><td><b>Umbral critico</b></td><td>&gt; 36 °C</td></tr>
  <tr><td><b>Nivel</b></td><td style="color:red"><b>CRITICO</b></td></tr>
  <tr><td><b>Mensaje</b></td><td>Temperatura extrema — riesgo de estres termico severo en caña</td></tr>
  <tr><td><b>Accion sugerida</b></td><td>Activar riego de emergencia y revisar proteccion de cultivo</td></tr>
  <tr><td><b>Fecha/Hora</b></td><td>{ahora}</td></tr>
</table>
<br>
<p style="color:#888;font-size:12px;">
  Este es un mensaje de prueba generado por SISCOM — Sistema Integral de
  Seguimiento de Cultivos. Universidad ICESI — Sistemas y Comunicaciones I.
</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = DEST_EMAIL
    msg.attach(MIMEText(body, "html"))

    print(f"Enviando alerta de prueba a {DEST_EMAIL} ...")
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, DEST_EMAIL, msg.as_string())
        print(f"✅ Correo enviado correctamente a {DEST_EMAIL}")
        print(f"   Revisa tu bandeja de entrada (y la carpeta Spam si no aparece).")
    except smtplib.SMTPAuthenticationError:
        print("❌ Error de autenticacion: usuario o contrasena incorrectos.")
        print("   Si usas Gmail con verificacion en 2 pasos, configura una")
        print("   Contrasena de Aplicacion (ver instrucciones en el README).")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error al enviar: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
