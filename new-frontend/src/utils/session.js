// Generar ID de sesión único para esta instancia del navegador
export function generateSessionId() {
  return `session-${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
}
