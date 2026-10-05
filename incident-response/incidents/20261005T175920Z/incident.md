# Incident

- alert: OrderTracker5xx
- status: resolved
- endpoint: /api/orders/{order_id}
- summary: 5xx responses on /api/orders/{order_id} in the last 2 minutes
- dashboard: http://localhost:3000/d/order-tracker-observability?viewPanel=2
- test: None
