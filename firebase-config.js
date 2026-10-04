/*
  Copiloto IA gratuito con Gemini mediante Firebase AI Logic (plan Spark, sin tarjeta).

  1. https://console.firebase.google.com → tu proyecto → "AI Logic" → Empezar → "Gemini Developer API".
  2. Configuración del proyecto → Tus apps → Añadir app web → copia el objeto firebaseConfig.
  3. Pégalo abajo (o, sin tocar código, en TrailMeteo → Copiloto → ⚙ Ajustes).
  4. Recomendado: activa App Check y añade tu dominio de GitHub Pages en "Dominios autorizados".

  La configuración web de Firebase no es una contraseña: identifica el proyecto y se publica en cualquier web que lo use.
*/
window.TRAILMETEO_FIREBASE = window.TRAILMETEO_FIREBASE || null;
// Ejemplo:
// window.TRAILMETEO_FIREBASE = { apiKey: "AIza...", authDomain: "tu-proyecto.firebaseapp.com", projectId: "tu-proyecto", appId: "1:123:web:abc" };
window.TRAILMETEO_AI_MODEL = window.TRAILMETEO_AI_MODEL || 'gemini-2.5-flash';
