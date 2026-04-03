/**
 * api/monitor-alert.ts
 * 
 * Función serverless en Vercel que recibe el webhook de UptimeRobot
 * cuando Railway cae o se recupera, y manda WhatsApp via Twilio.
 * 
 * Cómo configurar en UptimeRobot:
 * 1. Creá cuenta gratis en uptimerobot.com
 * 2. Add New Monitor → HTTP(s)
 * 3. URL: https://bot-peluqueria-production.up.railway.app/health
 * 4. Monitoring Interval: 5 minutes
 * 5. Alert Contacts → Add Alert Contact → Webhook
 * 6. Webhook URL: https://turnosbot-landing.vercel.app/api/monitor-alert
 * 7. POST value: { "monitorURL": "*monitorURL*", "alertType": "*alertType*", "alertTypeFriendlyName": "*alertTypeFriendlyName*" }
 */

import type { VercelRequest, VercelResponse } from '@vercel/node';

const TWILIO_ACCOUNT_SID = process.env.TWILIO_ACCOUNT_SID!;
const TWILIO_AUTH_TOKEN = process.env.TWILIO_AUTH_TOKEN!;
const TWILIO_WHATSAPP_NUMBER = process.env.TWILIO_WHATSAPP_NUMBER!; // ej: whatsapp:+14155238886
const ADMIN_WHATSAPP = process.env.ADMIN_WHATSAPP!;                  // ej: +5492974924147
const WEBHOOK_SECRET = process.env.MONITOR_WEBHOOK_SECRET!;          // clave que pongo en UptimeRobot

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Solo POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Verificar secret para que nadie más pueda llamar este endpoint
  const secret = req.headers['x-webhook-secret'] || req.query.secret;
  if (secret !== WEBHOOK_SECRET) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  const { alertType, alertTypeFriendlyName, monitorURL } = req.body;

  // alertType: 1 = caído, 2 = recuperado
  const esCaida = alertType === '1' || alertType === 1;
  const esRecuperado = alertType === '2' || alertType === 2;

  if (!esCaida && !esRecuperado) {
    return res.status(200).json({ status: 'ignored' });
  }

  const emoji = esCaida ? '🔴' : '🟢';
  const estado = esCaida ? 'CAÍDO' : 'RECUPERADO';
  const hora = new Date().toLocaleString('es-AR', { timeZone: 'America/Argentina/Buenos_Aires' });

  const mensaje = (
    `${emoji} *TurnosBot Backend - ${estado}*\n\n` +
    `🕐 ${hora}\n` +
    `🌐 ${monitorURL || 'Railway'}\n\n` +
    (esCaida
      ? '⚠️ El bot no está respondiendo. Los clientes no pueden reservar turnos.\n\nRevisá Railway urgente.'
      : '✅ El backend volvió a funcionar correctamente.')
  );

  try {
    // Enviar WhatsApp via Twilio
    const twilioUrl = `https://api.twilio.com/2010-04-01/Accounts/${TWILIO_ACCOUNT_SID}/Messages.json`;

    const body = new URLSearchParams({
      From: TWILIO_WHATSAPP_NUMBER,
      To: `whatsapp:${ADMIN_WHATSAPP}`,
      Body: mensaje,
    });

    const response = await fetch(twilioUrl, {
      method: 'POST',
      headers: {
        Authorization: 'Basic ' + Buffer.from(`${TWILIO_ACCOUNT_SID}:${TWILIO_AUTH_TOKEN}`).toString('base64'),
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: body.toString(),
    });

    if (!response.ok) {
      const error = await response.text();
      console.error('Error Twilio:', error);
      return res.status(500).json({ error: 'Failed to send WhatsApp' });
    }

    console.log(`✅ Alerta enviada: ${estado}`);
    return res.status(200).json({ status: 'ok', estado });

  } catch (error) {
    console.error('Error en monitor-alert:', error);
    return res.status(500).json({ error: String(error) });
  }
}