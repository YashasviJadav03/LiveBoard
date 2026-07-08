import { useEffect, useRef, useState, useCallback } from 'react';

/**
 * Custom hook for WebSocket connection to the LiveBoard backend.
 * Reconnects automatically on disconnect.
 */
export default function useWebSocket(lbId, userId, onMessage) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);

  const connect = useCallback(() => {
    if (!lbId || !userId) return;

    const wsBase = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';
    const url = `${wsBase}/ws/${lbId}/${userId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      console.log(`[WS] Connected: ${url}`);
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        onMessage?.(data);
      } catch (err) {
        console.warn('[WS] Non-JSON message:', event.data);
      }
    };

    ws.onclose = () => {
      setConnected(false);
      console.log('[WS] Disconnected, reconnecting in 3s...');
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      ws.close();
    };
  }, [lbId, userId, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected, ws: wsRef };
}
