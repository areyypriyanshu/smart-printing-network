"""Sprint 10: WebSocket Live Updates Implementation

Date: 2026-10-24

## Context

Phase 3 of the Smart Printing Network (SPN) aims to implement WebSocket live updates for real-time order status changes and shop notifications. This replaces polling with bidirectional WebSockets that push updates as they happen.

The requirement is part of the broader live updates functionality that includes:
- WebSocket endpoints for vendor queue and customer orders with token auth
- In-process publish on each committed transition  
- Polling fallback when sockets drop
- Frontend subscription with reconnect and backoff

## Problem Statement

Current order status updates are delivered through periodic polling every 5 seconds. This results in delays for customers and shops, creates unnecessary load on the API, and provides a poor user experience.

WebSockets offer a persistent connection that can push real-time updates, reducing latency and API load.

## Solution

### Backend Architecture

**WebSocket Endpoints:**
- `/ws/vendor` - Vendor board connects to receive orders for their shop
- `/ws/orders/{id}` - Customer connects to receive updates for their specific order

**Protocol:**
- First-frame authentication: Accept `spn.v1` subprotocol, then read one `{"type":"authenticate","token":...}` frame (≤16KB frame, ≤8192 token)
- Periodic reauth every 30s via `REAUTH_INTERVAL_SECONDS`
- Server sends `subscribed` message after auth confirms subscription

**Connection Lifecycle:**
- Origin validation via `app.domain.origin.origin_allowed` (exact normalized origins)
- Per-connection auth rate limit on `ws-auth:{host}` (10/min)
- First-frame auth: token frame before subscribe
- Periodic reauth every 30s

**Message Flow:**
- PostgreSQL `LISTEN/NOTIFY` (`spn_order_transition` channel) as commit-aware bridge
- `pg_notify` must run inside same transaction as order event, before commit; rollback discards notification
- EventHub: thread-safe per-app fan-out, bounded queues (maxsize=32), per-connection-key limits
- Listener outage closes all sockets forcing polling fallback

**Implementation Files:**
- `backend/app/routers/ws.py` - WebSocket endpoints and message forwarding
- `backend/app/services/live_service.py` - EventHub, _Subscription, notification bridge
- `backend/app/services/order_service.py` - Called after `session.flush()` to emit opening events and each transition
- `backend/app/services/authorization_service.py` - Shared auth helpers
- `backend/app/main.py` - EventHub initialization and listener lifecycle

### Frontend Architecture

**WebSocket Client:**
- Custom `useLiveChannel` hook that creates one authenticated socket with bounded lifetime
- Visible-only work: socket closes when tab is hidden, reconnects when visible
- Exponential backoff reconnect (1s, 2s, 4s, 8s, up to 15s)
- First-frame auth pattern matches backend protocol

**Polling Fallback:**
- If WebSocket fails to connect or drops, polling continues with 5s intervals
- Connection state visible to users via `LiveConnectionLabel`
- Queue and order pages show "Polling every 5 seconds" when not live

**Queue Page (`/vendor`):**
- Uses `useQueue` which includes `useLiveChannel`
- Updates local cache via live messages, refetches via polling when not live
- Shows "Live updates on" vs "Polling every 5 seconds"

**Order Page (`/orders/{id}`):**  
- Same pattern as queue, individual order subscriptions
- Stops polling for terminal orders (PAID, COLLECTED, etc.)

### Testing

**Backend Integration Tests:**
- `tests/integration/test_live_updates.py` - Full request/response cycle tests
  - Shop can only receive their own order updates
  - Customer cannot subscribe to other customers' orders
  - Polling fallback when WebSocket disconnects
  - Authentication and authorization edge cases
- `tests/integration/test_main_live.py` - Listener lifecycle tests
- `tests/unit/test_live_service.py` - EventHub and _Subscription unit tests

**Frontend Component Tests:**
- `src/features/live/use-live-channel.test.tsx` - Custom hook lifecycle tests
- `src/features/vendor-queue/queue-page.test.tsx` - Queue page unit tests
- `src/features/orders/order-page.test.tsx` - Order page unit tests

**E2E Playwright Tests:**
- `e2e/tests/order-journey.spec.ts` - Complete customer-to-shop flow
- Verifies polling fallback during vendor queue operations
- Tests real-time updates through WebSocket when available

### Performance and Reliability

**Resource Management:**
- Bounded queues (maxsize=32) prevent memory growth
- Per-connection key limits (8 per key, 100 total) prevent DoS
- Connection limits and cleanup prevent resource leaks

**Failure Handling:**
- Listener outage closes all sockets, forcing polling fallback
- Network errors trigger reconnect with backoff
- Visibility changes close sockets, reconnect on focus
- Invalid tokens/reauth failures close connection

**Security:**
- Token-based auth with origin validation
- Rate limiting per connection key
- Bounded message sizes (16KB frame, 8192 token)
- No sensitive data in logs or responses

## Key Decisions

### Why WebSockets Instead of Polling?

1. **Latency**: WebSocket pushes updates immediately vs 5s polling delays
2. **Load**: Fewer API requests, reduced database hits
3. **User Experience**: Real-time updates provide better UX
4. **Resource Efficiency**: Persistent connection better than repeated connections

### Why Bounded Queues?

1. **Memory Protection**: Prevents unbounded growth from dropped listeners
2. **Backpressure**: Coalesces messages when listener cannot keep up
3. **Reliability**: Resync messages when listener misses updates

### Why Origin Validation?

1. **Security**: Prevents WebSocket upgrade attacks
2. **Protection**: Ensures only trusted browsers can subscribe
3. **Compliance**: Follows browser security policies

## Migration Path

The transition preserves polling as a fallback, ensuring reliability while enabling real-time updates. Users gradually benefit from WebSockets as adoption increases, with graceful degradation when issues occur.

## Testing Strategy

**A/B Testing Approach:**
- New users can opt into WebSocket for better UX
- Old users continue with polling until migration
- Gradual rollout based on feature flags

**Monitoring and Observability:**
- Track WebSocket connection health
- Monitor polling fallback usage
- Measure user experience improvements
- Identify and resolve connection issues

## Future Enhancements

1. **WebSocket Compression**: Reduce bandwidth for mobile users
2. **Presence Indicators**: Show when shop is online/away
3. **Message Prioritization**: Critical updates always delivered
4. **WebSocket Pooling**: Reuse connections for multiple tabs
5. **Analytics**: Track real-time user engagement

## Migration Notes

This implementation supersedes ADR 007 "Polling before websockets" and updates the architecture to use WebSockets while maintaining polling as a reliable fallback. All references to polling-only approaches should be updated to this new implementation.

## Conclusion

This implementation provides real-time order updates through WebSockets while maintaining polling as a reliable fallback. The solution addresses latency, load, and user experience requirements while providing a clear migration path for users.

The architecture is modular, testable, and follows established patterns in the SPN codebase, ensuring maintainability and reliability.

## Reference

Sprint 10 of the Implementation Plan (docs/IMPLEMENTATION_PLAN.md): Live updates implementation
Phase 3.2 of the overall roadmap: Real-time updates for improved user experience
FR-35: Live update WebSocket infrastructure