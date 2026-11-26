/**
 * Versión del motor, en un solo lugar.
 *
 * src/index.js reexporta esta misma constante para que el build del
 * navegador (src/browser-entry.js) no tenga que importar todo el motor
 * en el hilo principal solo para leer la versión.
 */
export const ENGINE_VERSION = "0.1.0";
