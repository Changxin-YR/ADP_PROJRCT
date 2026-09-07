# Agent Permission Matrix

> Generated from `app.url_map` and `build_registry()`; 171 business operations.

| Method | Route | Agent Permission | Backend Permission | Agent Tool | Status |
| --- | --- | --- | --- | --- | --- |
| GET | `/api/v1/admin/applications` | `auth.review` | `auth.review (route guard + super_admin)` | `admin.applications` | PASS |
| POST | `/api/v1/admin/applications/{application_id}/approve` | `auth.review` | `auth.review (route guard + super_admin)` | `admin.approve` | PASS |
| POST | `/api/v1/admin/applications/{application_id}/reject` | `auth.review` | `auth.review (route guard + super_admin)` | `admin.reject` | PASS |
| PATCH | `/api/v1/admin/applications/{application_id}/review` | `auth.review` | `auth.review (route guard + super_admin)` | `admin.review_application` | PASS |
| GET | `/api/v1/admin/audit-logs` | `audit.view` | `audit.view (route guard + super_admin)` | `admin.audit` | PASS |
| GET | `/api/v1/admin/options` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.options` | PASS |
| GET | `/api/v1/admin/roles` | `auth.role.manage` | `auth.role.manage (route guard + super_admin)` | `admin.roles` | PASS |
| POST | `/api/v1/admin/roles/{role_id}/copies` | `auth.role.manage` | `auth.role.manage (route guard + super_admin)` | `admin.copy` | PASS |
| PUT | `/api/v1/admin/roles/{role_id}/permissions` | `auth.role.manage` | `auth.role.manage (route guard + super_admin)` | `admin.update_role_permissions` | PASS |
| POST | `/api/v1/admin/users` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.create_user` | PASS |
| GET | `/api/v1/admin/users` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.users` | PASS |
| DELETE | `/api/v1/admin/users/{user_id}` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.delete` | PASS |
| PUT | `/api/v1/admin/users/{user_id}/grants` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.update_grants` | PASS |
| POST | `/api/v1/admin/users/{user_id}/password-reset` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.reset_password` | PASS |
| POST | `/api/v1/admin/users/{user_id}/reset-password` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.reset_password:post` | PASS |
| POST | `/api/v1/admin/users/{user_id}/retire` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.retire_user` | PASS |
| PATCH | `/api/v1/admin/users/{user_id}/status` | `auth.user.manage` | `auth.user.manage (route guard + super_admin)` | `admin.set_status` | PASS |
| GET | `/api/v1/auth/application` | `none` | `session guard` | `api.auth_application_get_api_v1_auth_application` | PASS |
| PATCH | `/api/v1/auth/application` | `none` | `session guard` | `api.auth_resubmit_application_patch_api_v1_auth_application` | PASS |
| GET | `/api/v1/auth/csrf` | `none` | `session guard` | `api.auth_csrf_get_api_v1_auth_csrf` | PASS |
| POST | `/api/v1/auth/login` | `none` | `session guard` | `api.auth_login_post_api_v1_auth_login` | PASS |
| POST | `/api/v1/auth/logout` | `none` | `session guard` | `api.auth_logout_post_api_v1_auth_logout` | PASS |
| GET | `/api/v1/auth/me` | `none` | `session guard` | `api.auth_me_get_api_v1_auth_me` | PASS |
| POST | `/api/v1/auth/password/change` | `none` | `session guard` | `api.auth_change_password_post_api_v1_auth_password_change` | PASS |
| POST | `/api/v1/auth/register` | `none` | `session guard` | `api.auth_register_post_api_v1_auth_register` | PASS |
| GET | `/api/v1/auth/register/options` | `none` | `session guard` | `api.auth_register_options_get_api_v1_auth_register_options` | PASS |
| GET | `/api/v1/auth/workbench` | `none` | `session guard` | `api.auth_workbench_get_api_v1_auth_workbench` | PASS |
| GET | `/api/v1/cost/allocation-rules` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_allocation_rules_get_api_v1_cost_allocation_rules` | PASS |
| PUT | `/api/v1/cost/allocation-rules` | `cost.allocation.manage` | `cost.allocation.manage (service guard not statically exposed)` | `api.cost_save_allocation_rules_put_api_v1_cost_allocation_rules` | PASS |
| POST | `/api/v1/cost/allocations` | `cost.allocation.manage` | `cost.allocation.manage (service guard not statically exposed)` | `api.cost_run_allocation_post_api_v1_cost_allocations` | PASS |
| POST | `/api/v1/cost/assets` | `cost.asset.manage` | `cost.asset.manage (service guard not statically exposed)` | `api.cost_create_asset_post_api_v1_cost_assets` | PASS |
| GET | `/api/v1/cost/assets` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_list_assets_get_api_v1_cost_assets` | PASS |
| GET | `/api/v1/cost/assets/{record_id}` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_asset_get_api_v1_cost_assets_record_id` | PASS |
| DELETE | `/api/v1/cost/assets/{record_id}` | `cost.asset.manage` | `cost.asset.manage (service guard not statically exposed)` | `api.cost_delete_asset_delete_api_v1_cost_assets_record_id` | PASS |
| PATCH | `/api/v1/cost/assets/{record_id}` | `cost.asset.manage` | `cost.asset.manage (service guard not statically exposed)` | `api.cost_update_asset_patch_api_v1_cost_assets_record_id` | PASS |
| POST | `/api/v1/cost/assets/{record_id}/confirm` | `cost.asset.confirm` | `cost.asset.confirm` | `api.cost_confirm_asset_post_api_v1_cost_assets_record_id_confirm` | PASS |
| POST | `/api/v1/cost/assets/{record_id}/depreciate` | `cost.asset.manage` | `cost.asset.manage (service guard not statically exposed)` | `api.cost_depreciate_asset_post_api_v1_cost_assets_record_id_depreciate` | PASS |
| POST | `/api/v1/cost/assets/{record_id}/submit` | `cost.asset.manage` | `cost.asset.manage` | `api.cost_submit_asset_post_api_v1_cost_assets_record_id_submit` | PASS |
| POST | `/api/v1/cost/assets/{record_id}/verify` | `cost.asset.verify` | `cost.asset.verify` | `api.cost_verify_asset_post_api_v1_cost_assets_record_id_verify` | PASS |
| POST | `/api/v1/cost/entries` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_create_entry_post_api_v1_cost_entries` | PASS |
| GET | `/api/v1/cost/entries` | `cost.view` | `cost.view (service guard not statically exposed)` | `cost.list_entries` | PASS |
| DELETE | `/api/v1/cost/entries/{entry_id}` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_delete_draft_delete_api_v1_cost_entries_entry_id` | PASS |
| PATCH | `/api/v1/cost/entries/{entry_id}` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_update_entry_patch_api_v1_cost_entries_entry_id` | PASS |
| POST | `/api/v1/cost/entries/{entry_id}/confirm` | `cost.entry.confirm` | `cost.entry.confirm` | `api.cost_confirm_entry_post_api_v1_cost_entries_entry_id_confirm` | PASS |
| POST | `/api/v1/cost/entries/{entry_id}/reverse` | `cost.entry.reverse` | `cost.entry.reverse (service guard not statically exposed)` | `api.cost_reverse_entry_post_api_v1_cost_entries_entry_id_reverse` | PASS |
| POST | `/api/v1/cost/entries/{entry_id}/submit` | `cost.entry.manage` | `cost.entry.manage` | `api.cost_submit_entry_post_api_v1_cost_entries_entry_id_submit` | PASS |
| POST | `/api/v1/cost/entries/{entry_id}/verify` | `cost.entry.verify` | `cost.entry.verify` | `api.cost_verify_entry_post_api_v1_cost_entries_entry_id_verify` | PASS |
| POST | `/api/v1/cost/expenses` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_create_expense_post_api_v1_cost_expenses` | PASS |
| GET | `/api/v1/cost/expenses` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_list_expenses_get_api_v1_cost_expenses` | PASS |
| DELETE | `/api/v1/cost/expenses/{record_id}` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_delete_expense_delete_api_v1_cost_expenses_record_id` | PASS |
| GET | `/api/v1/cost/expenses/{record_id}` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_expense_get_api_v1_cost_expenses_record_id` | PASS |
| PATCH | `/api/v1/cost/expenses/{record_id}` | `cost.entry.manage` | `cost.entry.manage (service guard not statically exposed)` | `api.cost_update_expense_patch_api_v1_cost_expenses_record_id` | PASS |
| POST | `/api/v1/cost/expenses/{record_id}/confirm` | `cost.entry.confirm` | `cost.entry.confirm` | `api.cost_confirm_expense_post_api_v1_cost_expenses_record_id_confirm` | PASS |
| POST | `/api/v1/cost/expenses/{record_id}/reverse` | `cost.entry.reverse` | `cost.entry.reverse (service guard not statically exposed)` | `api.cost_reverse_expense_post_api_v1_cost_expenses_record_id_reverse` | PASS |
| POST | `/api/v1/cost/expenses/{record_id}/submit` | `cost.entry.manage` | `cost.entry.manage` | `api.cost_submit_expense_post_api_v1_cost_expenses_record_id_submit` | PASS |
| POST | `/api/v1/cost/expenses/{record_id}/verify` | `cost.entry.verify` | `cost.entry.verify` | `api.cost_verify_expense_post_api_v1_cost_expenses_record_id_verify` | PASS |
| GET | `/api/v1/cost/reports/net` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_net_report_get_api_v1_cost_reports_net` | PASS |
| POST | `/api/v1/cost/settlements` | `cost.settlement.manage` | `cost.settlement.manage (service guard not statically exposed)` | `api.cost_create_settlement_post_api_v1_cost_settlements` | PASS |
| GET | `/api/v1/cost/settlements` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_list_settlements_get_api_v1_cost_settlements` | PASS |
| DELETE | `/api/v1/cost/settlements/{record_id}` | `cost.settlement.manage` | `cost.settlement.manage (service guard not statically exposed)` | `api.cost_delete_settlement_delete_api_v1_cost_settlements_record_id` | PASS |
| GET | `/api/v1/cost/settlements/{record_id}` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_settlement_get_api_v1_cost_settlements_record_id` | PASS |
| PATCH | `/api/v1/cost/settlements/{record_id}` | `cost.settlement.manage` | `cost.settlement.manage (service guard not statically exposed)` | `api.cost_update_settlement_patch_api_v1_cost_settlements_record_id` | PASS |
| POST | `/api/v1/cost/settlements/{record_id}/confirm` | `cost.settlement.confirm` | `cost.settlement.confirm` | `api.cost_confirm_settlement_post_api_v1_cost_settlements_record_id_confirm` | PASS |
| POST | `/api/v1/cost/settlements/{record_id}/reverse` | `cost.settlement.reverse` | `cost.settlement.reverse (service guard not statically exposed)` | `api.cost_reverse_settlement_post_api_v1_cost_settlements_record_id_reverse` | PASS |
| POST | `/api/v1/cost/settlements/{record_id}/submit` | `cost.settlement.manage` | `cost.settlement.manage` | `api.cost_submit_settlement_post_api_v1_cost_settlements_record_id_submit` | PASS |
| POST | `/api/v1/cost/settlements/{record_id}/verify` | `cost.settlement.verify` | `cost.settlement.verify` | `api.cost_verify_settlement_post_api_v1_cost_settlements_record_id_verify` | PASS |
| GET | `/api/v1/cost/structure` | `cost.view` | `cost.view (service guard not statically exposed)` | `api.cost_structure_get_api_v1_cost_structure` | PASS |
| GET | `/api/v1/data-exchange/attachments` | `attachment.manage` | `attachment.manage (service guard not statically exposed)` | `api.data_exchange_attachments_get_api_v1_data_exchange_attachments` | PASS |
| POST | `/api/v1/data-exchange/attachments` | `attachment.manage` | `attachment.manage (service guard not statically exposed)` | `api.data_exchange_upload_attachment_post_api_v1_data_exchange_attachments` | PASS |
| GET | `/api/v1/data-exchange/attachments/{attachment_id}/download` | `attachment.manage` | `attachment.manage (service guard not statically exposed)` | `api.data_exchange_download_attachment_get_api_v1_data_exchange_attachments_attachment_id_download` | PASS |
| POST | `/api/v1/data-exchange/exports` | `data_exchange.export` | `data_exchange.export (service guard not statically exposed)` | `api.data_exchange_export_post_api_v1_data_exchange_exports` | PASS |
| GET | `/api/v1/data-exchange/imports` | `data_exchange.view` | `data_exchange.view (service guard not statically exposed)` | `api.data_exchange_imports_get_api_v1_data_exchange_imports` | PASS |
| POST | `/api/v1/data-exchange/imports/{batch_id}/confirm` | `data_exchange.import` | `data_exchange.import (service guard not statically exposed)` | `api.data_exchange_confirm_post_api_v1_data_exchange_imports_batch_id_confirm` | PASS |
| GET | `/api/v1/data-exchange/imports/{batch_id}/errors` | `data_exchange.view` | `data_exchange.view (service guard not statically exposed)` | `api.data_exchange_errors_get_api_v1_data_exchange_imports_batch_id_errors` | PASS |
| POST | `/api/v1/data-exchange/imports/{batch_id}/revoke` | `data_exchange.import` | `data_exchange.import (service guard not statically exposed)` | `api.data_exchange_revoke_post_api_v1_data_exchange_imports_batch_id_revoke` | PASS |
| POST | `/api/v1/data-exchange/imports/preview` | `data_exchange.import` | `data_exchange.import (service guard not statically exposed)` | `data_exchange.preview_import` | PASS |
| GET | `/api/v1/data-exchange/templates` | `data_exchange.view` | `data_exchange.view (service guard not statically exposed)` | `api.data_exchange_templates_get_api_v1_data_exchange_templates` | PASS |
| GET | `/api/v1/data-exchange/templates/{code}/download` | `data_exchange.view` | `data_exchange.view (service guard not statically exposed)` | `api.data_exchange_download_template_get_api_v1_data_exchange_templates_code_download` | PASS |
| GET | `/api/v1/health` | `none` | `none` | `api.health_get_api_v1_health` | PASS |
| POST | `/api/v1/master-data/{resource}` | `master_data.manage` | `master_data.manage (resource-specific)` | `master_data.create_record` | PASS |
| GET | `/api/v1/master-data/{resource}` | `master_data.view` | `master_data.view (resource-specific)` | `master_data.list_records` | PASS |
| DELETE | `/api/v1/master-data/{resource}/{record_id}` | `master_data.manage` | `master_data.manage (resource-specific)` | `api.master_data_delete_record_delete_api_v1_master_data_resource_record_id` | PASS |
| GET | `/api/v1/master-data/{resource}/{record_id}` | `master_data.view` | `master_data.view (resource-specific)` | `master_data.get_record` | PASS |
| PATCH | `/api/v1/master-data/{resource}/{record_id}` | `master_data.manage` | `master_data.manage (resource-specific)` | `api.master_data_update_record_patch_api_v1_master_data_resource_record_id` | PASS |
| POST | `/api/v1/master-data/{resource}/{record_id}/archive` | `master_data.manage` | `master_data.manage (resource-specific)` | `api.master_data_archive_record_post_api_v1_master_data_resource_record_id_archive` | PASS |
| POST | `/api/v1/master-data/{resource}/{record_id}/submit` | `master_data.manage` | `master_data.manage (resource-specific)` | `api.master_data_submit_record_post_api_v1_master_data_resource_record_id_submit` | PASS |
| POST | `/api/v1/master-data/{resource}/{record_id}/verify` | `master_data.verify` | `master_data.verify (resource-specific)` | `api.master_data_verify_record_post_api_v1_master_data_resource_record_id_verify` | PASS |
| POST | `/api/v1/master-data/ponds/{pond_id}/status-changes` | `master_data.manage` | `master_data.manage (service guard not statically exposed)` | `api.master_data_request_pond_status_change_post_api_v1_master_data_ponds_pond_id_status_changes` | PASS |
| POST | `/api/v1/master-data/ponds/{pond_id}/status-changes/{request_id}/verify` | `master_data.verify` | `master_data.verify (service guard not statically exposed)` | `api.master_data_verify_pond_status_change_post_api_v1_master_data_ponds_pond_id_status_changes_request_id_verify` | PASS |
| GET | `/api/v1/notifications` | `work_item.view` | `work_item.view (service guard not statically exposed)` | `api.workbench_api_notifications_get_api_v1_notifications` | PASS |
| PATCH | `/api/v1/notifications/{notification_id}` | `work_item.manage` | `work_item.manage (service guard not statically exposed)` | `api.workbench_api_update_notification_patch_api_v1_notifications_notification_id` | PASS |
| POST | `/api/v1/production/{resource}` | `production.manage` | `production.manage (resource-specific)` | `api.production_create_post_api_v1_production_resource` | PASS |
| GET | `/api/v1/production/{resource}` | `production.view` | `production.view (resource-specific)` | `production.list_records` | PASS |
| DELETE | `/api/v1/production/{resource}/{record_id}` | `production.manage` | `production.manage (resource-specific)` | `api.production_delete_delete_api_v1_production_resource_record_id` | PASS |
| GET | `/api/v1/production/{resource}/{record_id}` | `production.view` | `production.view (resource-specific)` | `api.production_get_record_get_api_v1_production_resource_record_id` | PASS |
| PATCH | `/api/v1/production/{resource}/{record_id}` | `production.manage` | `production.manage (resource-specific)` | `api.production_update_patch_api_v1_production_resource_record_id` | PASS |
| POST | `/api/v1/production/{resource}/{record_id}/corrections` | `production.manage` | `production.manage (resource-specific)` | `api.production_correct_post_api_v1_production_resource_record_id_corrections` | PASS |
| POST | `/api/v1/production/{resource}/{record_id}/submit` | `production.manage` | `production.manage (resource-specific)` | `api.production_submit_post_api_v1_production_resource_record_id_submit` | PASS |
| POST | `/api/v1/production/{resource}/{record_id}/verify` | `production.verify` | `production.verify (resource-specific)` | `api.production_verify_post_api_v1_production_resource_record_id_verify` | PASS |
| GET | `/api/v1/production/batches/{batch_id}/reconciliation` | `production.view` | `production.view (service guard not statically exposed)` | `api.production_reconciliation_get_api_v1_production_batches_batch_id_reconciliation` | PASS |
| POST | `/api/v1/production/batches/{batch_id}/status` | `production.manage` | `production.manage (service guard not statically exposed)` | `api.production_change_batch_status_post_api_v1_production_batches_batch_id_status` | PASS |
| POST | `/api/v1/purchase/orders` | `purchase.manage` | `purchase.manage (service guard not statically exposed)` | `api.purchase_create_order_post_api_v1_purchase_orders` | PASS |
| GET | `/api/v1/purchase/orders` | `purchase.view` | `purchase.view (service guard not statically exposed)` | `purchase.list_orders` | PASS |
| DELETE | `/api/v1/purchase/orders/{record_id}` | `purchase.manage` | `purchase.manage (service guard not statically exposed)` | `api.purchase_delete_order_delete_api_v1_purchase_orders_record_id` | PASS |
| PATCH | `/api/v1/purchase/orders/{record_id}` | `purchase.manage` | `purchase.manage (service guard not statically exposed)` | `api.purchase_update_order_patch_api_v1_purchase_orders_record_id` | PASS |
| POST | `/api/v1/purchase/orders/{record_id}/approve` | `purchase.verify` | `purchase.verify (service guard not statically exposed)` | `api.purchase_approve_order_post_api_v1_purchase_orders_record_id_approve` | PASS |
| POST | `/api/v1/purchase/orders/{record_id}/cancel` | `purchase.verify` | `purchase.verify (service guard not statically exposed)` | `api.purchase_cancel_order_post_api_v1_purchase_orders_record_id_cancel` | PASS |
| POST | `/api/v1/purchase/orders/{record_id}/submit` | `purchase.manage` | `purchase.manage (service guard not statically exposed)` | `api.purchase_submit_order_post_api_v1_purchase_orders_record_id_submit` | PASS |
| GET | `/api/v1/purchase/payables` | `finance.payable.view` | `finance.payable.view (service guard not statically exposed)` | `api.purchase_payables_get_api_v1_purchase_payables` | PASS |
| POST | `/api/v1/purchase/payments` | `finance.payment.manage` | `finance.payment.manage (service guard not statically exposed)` | `api.purchase_create_payment_post_api_v1_purchase_payments` | PASS |
| GET | `/api/v1/purchase/payments` | `finance.payable.view` | `finance.payable.view (service guard not statically exposed)` | `api.purchase_payments_get_api_v1_purchase_payments` | PASS |
| DELETE | `/api/v1/purchase/payments/{record_id}` | `finance.payment.manage` | `finance.payment.manage (service guard not statically exposed)` | `api.purchase_delete_payment_delete_api_v1_purchase_payments_record_id` | PASS |
| PATCH | `/api/v1/purchase/payments/{record_id}` | `finance.payment.manage` | `finance.payment.manage (service guard not statically exposed)` | `api.purchase_update_payment_patch_api_v1_purchase_payments_record_id` | PASS |
| POST | `/api/v1/purchase/payments/{record_id}/cancel` | `finance.payment.verify` | `finance.payment.verify (service guard not statically exposed)` | `api.purchase_cancel_payment_post_api_v1_purchase_payments_record_id_cancel` | PASS |
| POST | `/api/v1/purchase/payments/{record_id}/reverse` | `finance.payment.verify` | `finance.payment.verify (service guard not statically exposed)` | `api.purchase_reverse_payment_post_api_v1_purchase_payments_record_id_reverse` | PASS |
| POST | `/api/v1/purchase/payments/{record_id}/submit` | `finance.payment.manage` | `finance.payment.manage (service guard not statically exposed)` | `api.purchase_submit_payment_post_api_v1_purchase_payments_record_id_submit` | PASS |
| POST | `/api/v1/purchase/payments/{record_id}/verify` | `finance.payment.verify` | `finance.payment.verify (service guard not statically exposed)` | `api.purchase_verify_payment_post_api_v1_purchase_payments_record_id_verify` | PASS |
| POST | `/api/v1/purchase/returns` | `purchase.return.manage` | `purchase.manage / purchase.return.manage` | `api.purchase_create_return` | PASS |
| GET | `/api/v1/purchase/returns` | `purchase.view` | `purchase.view (service guard not statically exposed)` | `api.purchase_list_returns` | PASS |
| DELETE | `/api/v1/purchase/returns/{record_id}` | `purchase.return.manage` | `purchase.manage / purchase.return.manage` | `api.purchase_delete_return` | PASS |
| POST | `/api/v1/purchase/returns/{record_id}/cancel` | `purchase.return.verify` | `purchase.return.verify / purchase.verify` | `api.purchase_cancel_return` | PASS |
| POST | `/api/v1/purchase/returns/{record_id}/submit` | `purchase.return.manage` | `purchase.manage / purchase.return.manage` | `api.purchase_submit_return` | PASS |
| POST | `/api/v1/purchase/returns/{record_id}/verify` | `purchase.return.verify` | `purchase.return.verify / purchase.verify` | `api.purchase_verify_return` | PASS |
| POST | `/api/v1/sales/deliveries` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_create_delivery_post_api_v1_sales_deliveries` | PASS |
| GET | `/api/v1/sales/deliveries` | `sales.view` | `sales.view (service guard not statically exposed)` | `api.sales_deliveries_get_api_v1_sales_deliveries` | PASS |
| DELETE | `/api/v1/sales/deliveries/{record_id}` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_delete_delivery_delete_api_v1_sales_deliveries_record_id` | PASS |
| PATCH | `/api/v1/sales/deliveries/{record_id}` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_update_delivery_patch_api_v1_sales_deliveries_record_id` | PASS |
| POST | `/api/v1/sales/deliveries/{record_id}/cancel` | `sales.verify` | `sales.verify (service guard not statically exposed)` | `api.sales_cancel_delivery_post_api_v1_sales_deliveries_record_id_cancel` | PASS |
| POST | `/api/v1/sales/deliveries/{record_id}/correct` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_correct_delivery_post_api_v1_sales_deliveries_record_id_correct` | PASS |
| POST | `/api/v1/sales/deliveries/{record_id}/submit` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_submit_delivery_post_api_v1_sales_deliveries_record_id_submit` | PASS |
| POST | `/api/v1/sales/deliveries/{record_id}/verify` | `sales.verify` | `sales.verify (service guard not statically exposed)` | `api.sales_verify_delivery_post_api_v1_sales_deliveries_record_id_verify` | PASS |
| POST | `/api/v1/sales/orders` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_create_order_post_api_v1_sales_orders` | PASS |
| GET | `/api/v1/sales/orders` | `sales.view` | `sales.view (service guard not statically exposed)` | `sales.list_orders` | PASS |
| DELETE | `/api/v1/sales/orders/{record_id}` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_delete_order_delete_api_v1_sales_orders_record_id` | PASS |
| PATCH | `/api/v1/sales/orders/{record_id}` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_update_order_patch_api_v1_sales_orders_record_id` | PASS |
| POST | `/api/v1/sales/orders/{record_id}/approve` | `sales.verify` | `sales.verify (service guard not statically exposed)` | `api.sales_approve_order_post_api_v1_sales_orders_record_id_approve` | PASS |
| POST | `/api/v1/sales/orders/{record_id}/cancel` | `sales.verify` | `sales.verify (service guard not statically exposed)` | `api.sales_cancel_order_post_api_v1_sales_orders_record_id_cancel` | PASS |
| POST | `/api/v1/sales/orders/{record_id}/submit` | `sales.manage` | `sales.manage (service guard not statically exposed)` | `api.sales_submit_order_post_api_v1_sales_orders_record_id_submit` | PASS |
| POST | `/api/v1/sales/receipts` | `finance.receipt.manage` | `finance.receipt.manage (service guard not statically exposed)` | `api.sales_create_receipt_post_api_v1_sales_receipts` | PASS |
| GET | `/api/v1/sales/receipts` | `finance.receivable.view` | `finance.receivable.view (service guard not statically exposed)` | `api.sales_receipts_get_api_v1_sales_receipts` | PASS |
| DELETE | `/api/v1/sales/receipts/{record_id}` | `finance.receipt.manage` | `finance.receipt.manage (service guard not statically exposed)` | `api.sales_delete_receipt_delete_api_v1_sales_receipts_record_id` | PASS |
| PATCH | `/api/v1/sales/receipts/{record_id}` | `finance.receipt.manage` | `finance.receipt.manage (service guard not statically exposed)` | `api.sales_update_receipt_patch_api_v1_sales_receipts_record_id` | PASS |
| POST | `/api/v1/sales/receipts/{record_id}/cancel` | `finance.receipt.verify` | `finance.receipt.verify (service guard not statically exposed)` | `api.sales_cancel_receipt_post_api_v1_sales_receipts_record_id_cancel` | PASS |
| POST | `/api/v1/sales/receipts/{record_id}/reverse` | `finance.receipt.verify` | `finance.receipt.verify (service guard not statically exposed)` | `api.sales_reverse_receipt_post_api_v1_sales_receipts_record_id_reverse` | PASS |
| POST | `/api/v1/sales/receipts/{record_id}/submit` | `finance.receipt.manage` | `finance.receipt.manage (service guard not statically exposed)` | `api.sales_submit_receipt_post_api_v1_sales_receipts_record_id_submit` | PASS |
| POST | `/api/v1/sales/receipts/{record_id}/verify` | `finance.receipt.verify` | `finance.receipt.verify (service guard not statically exposed)` | `api.sales_verify_receipt_post_api_v1_sales_receipts_record_id_verify` | PASS |
| GET | `/api/v1/sales/receivables` | `finance.receivable.view` | `finance.receivable.view (service guard not statically exposed)` | `api.sales_receivables_get_api_v1_sales_receivables` | PASS |
| POST | `/api/v1/sales/returns` | `sales.return.manage` | `sales.manage / sales.return.manage` | `api.sales_create_return` | PASS |
| GET | `/api/v1/sales/returns` | `sales.view` | `sales.view (service guard not statically exposed)` | `api.sales_list_returns` | PASS |
| DELETE | `/api/v1/sales/returns/{record_id}` | `sales.return.manage` | `sales.manage / sales.return.manage` | `api.sales_delete_return` | PASS |
| POST | `/api/v1/sales/returns/{record_id}/cancel` | `sales.return.verify` | `sales.return.verify / sales.verify` | `api.sales_cancel_return` | PASS |
| POST | `/api/v1/sales/returns/{record_id}/submit` | `sales.return.manage` | `sales.manage / sales.return.manage` | `api.sales_submit_return` | PASS |
| POST | `/api/v1/sales/returns/{record_id}/verify` | `sales.return.verify` | `sales.return.verify / sales.verify` | `api.sales_verify_return` | PASS |
| POST | `/api/v1/warehouse/{resource}` | `warehouse.manage` | `warehouse.manage (resource-specific)` | `api.warehouse_create_post_api_v1_warehouse_resource` | PASS |
| GET | `/api/v1/warehouse/{resource}` | `warehouse.view` | `warehouse.view (resource-specific)` | `warehouse.list_records` | PASS |
| DELETE | `/api/v1/warehouse/{resource}/{record_id}` | `warehouse.manage` | `warehouse.manage (resource-specific)` | `api.warehouse_delete_delete_api_v1_warehouse_resource_record_id` | PASS |
| GET | `/api/v1/warehouse/{resource}/{record_id}` | `warehouse.view` | `warehouse.view (resource-specific)` | `api.warehouse_get_record_get_api_v1_warehouse_resource_record_id` | PASS |
| PATCH | `/api/v1/warehouse/{resource}/{record_id}` | `warehouse.manage` | `warehouse.manage (resource-specific)` | `api.warehouse_update_patch_api_v1_warehouse_resource_record_id` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/cancel` | `warehouse.verify` | `warehouse.verify (resource-specific)` | `api.warehouse_cancel_transfer_post_api_v1_warehouse_resource_record_id_cancel` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/corrections` | `warehouse.manage` | `warehouse.manage (resource-specific)` | `api.warehouse_correct_post_api_v1_warehouse_resource_record_id_corrections` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/dispatch` | `warehouse.verify` | `warehouse.verify (resource-specific)` | `api.warehouse_dispatch_post_api_v1_warehouse_resource_record_id_dispatch` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/receive` | `warehouse.verify` | `warehouse.verify (resource-specific)` | `api.warehouse_receive_post_api_v1_warehouse_resource_record_id_receive` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/submit` | `warehouse.manage` | `warehouse.manage (service guard not statically exposed)` | `api.warehouse_submit_post_api_v1_warehouse_resource_record_id_submit` | PASS |
| POST | `/api/v1/warehouse/{resource}/{record_id}/verify` | `warehouse.verify` | `warehouse.verify (resource-specific)` | `api.warehouse_verify_post_api_v1_warehouse_resource_record_id_verify` | PASS |
| GET | `/api/v1/warehouse/alerts` | `warehouse.view` | `warehouse.view (service guard not statically exposed)` | `api.warehouse_alerts_get_api_v1_warehouse_alerts` | PASS |
| POST | `/api/v1/warehouse/alerts/{alert_key}/handle` | `warehouse.manage` | `warehouse.manage (service guard not statically exposed)` | `api.warehouse_handle_alert_post_api_v1_warehouse_alerts_alert_key_handle` | PASS |
| GET | `/api/v1/warehouse/ledger` | `warehouse.view` | `warehouse.view (service guard not statically exposed)` | `api.warehouse_ledger_get_api_v1_warehouse_ledger` | PASS |
| GET | `/api/v1/warehouse/warehouses` | `warehouse.view` | `warehouse.view (service guard not statically exposed)` | `api.warehouse_warehouses_get_api_v1_warehouse_warehouses` | PASS |
| GET | `/api/v1/work-items` | `work_item.view` | `work_item.view (service guard not statically exposed)` | `workbench.list_work_items` | PASS |
| PATCH | `/api/v1/work-items/{item_id}` | `work_item.manage` | `work_item.manage (service guard not statically exposed)` | `workbench.update_work_item` | PASS |
| GET | `/api/v1/workbench/summary` | `workbench.enter` | `workbench.enter (service guard not statically exposed)` | `api.workbench_api_summary_get_api_v1_workbench_summary` | PASS |
