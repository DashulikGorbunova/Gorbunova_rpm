-- Equality prefix, then ordered range; INCLUDE covers the response projection.
CREATE INDEX idx_service_orders_user_created
 ON service.orders(user_id,created_at DESC,id DESC)
 INCLUDE(amount,status);
CREATE INDEX idx_service_orders_paid_user_created
 ON service.orders(user_id,created_at DESC,id DESC)
 INCLUDE(amount,status) WHERE status='PAID';
