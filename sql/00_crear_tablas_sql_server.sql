/*
  Prueba tecnica retail - Paso 00
  Crea una base de datos y tablas compatibles con SQL Server.

  Nota importante:
  No se crean llaves foraneas estrictas porque la auditoria de calidad debe detectar
  productos con vendor_id inexistente. Si se forzara la FK products -> vendors,
  la carga fallaria y se perderia ese hallazgo.
*/

IF DB_ID(N'RetailPruebaTecnica') IS NULL
BEGIN
  CREATE DATABASE RetailPruebaTecnica;
END;
GO

USE RetailPruebaTecnica;
GO

DROP TABLE IF EXISTS dbo.transaction_items;
DROP TABLE IF EXISTS dbo.transactions;
DROP TABLE IF EXISTS dbo.store_promotions;
DROP TABLE IF EXISTS dbo.products;
DROP TABLE IF EXISTS dbo.stores;
DROP TABLE IF EXISTS dbo.vendors;
GO

CREATE TABLE dbo.vendors (
  vendor_id NVARCHAR(20) NOT NULL,
  vendor_name NVARCHAR(120) NOT NULL,
  country NVARCHAR(10) NOT NULL,
  tier NVARCHAR(5) NOT NULL,
  is_shared_catalog BIT NOT NULL,
  CONSTRAINT PK_vendors PRIMARY KEY (vendor_id)
);

CREATE TABLE dbo.products (
  item_id NVARCHAR(20) NOT NULL,
  item_name NVARCHAR(160) NOT NULL,
  brand NVARCHAR(80) NOT NULL,
  vendor_id NVARCHAR(20) NOT NULL,
  category NVARCHAR(80) NOT NULL,
  department NVARCHAR(80) NOT NULL,
  cost DECIMAL(18, 2) NOT NULL,
  CONSTRAINT PK_products PRIMARY KEY (item_id)
);

CREATE TABLE dbo.stores (
  store_id NVARCHAR(20) NOT NULL,
  store_name NVARCHAR(160) NOT NULL,
  country NVARCHAR(10) NOT NULL,
  city NVARCHAR(120) NOT NULL,
  format NVARCHAR(40) NOT NULL,
  size_sqm INT NOT NULL,
  opening_date DATE NOT NULL,
  region NVARCHAR(80) NOT NULL,
  CONSTRAINT PK_stores PRIMARY KEY (store_id)
);

CREATE TABLE dbo.transactions (
  transaction_id NVARCHAR(30) NOT NULL,
  customer_id NVARCHAR(30) NULL,
  transaction_date DATE NOT NULL,
  store_id NVARCHAR(20) NOT NULL,
  total_amount DECIMAL(18, 2) NOT NULL,
  payment_method NVARCHAR(20) NOT NULL,
  loyalty_card BIT NOT NULL,
  status NVARCHAR(20) NOT NULL,
  CONSTRAINT PK_transactions PRIMARY KEY (transaction_id)
);

CREATE TABLE dbo.transaction_items (
  transaction_item_id NVARCHAR(30) NOT NULL,
  transaction_id NVARCHAR(30) NOT NULL,
  item_id NVARCHAR(20) NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(18, 2) NOT NULL,
  was_on_promo BIT NOT NULL,
  CONSTRAINT PK_transaction_items PRIMARY KEY (transaction_item_id)
);

CREATE TABLE dbo.store_promotions (
  store_id NVARCHAR(20) NOT NULL,
  promo_name NVARCHAR(120) NOT NULL,
  variant NVARCHAR(20) NOT NULL,
  start_date DATE NOT NULL,
  end_date DATE NOT NULL,
  promo_type NVARCHAR(40) NOT NULL
);
GO

CREATE INDEX IX_transactions_store_date ON dbo.transactions (store_id, transaction_date);
CREATE INDEX IX_transactions_customer_date ON dbo.transactions (customer_id, transaction_date) WHERE customer_id IS NOT NULL;
CREATE INDEX IX_transaction_items_transaction ON dbo.transaction_items (transaction_id);
CREATE INDEX IX_transaction_items_item ON dbo.transaction_items (item_id);
CREATE INDEX IX_products_vendor_category ON dbo.products (vendor_id, category);
CREATE INDEX IX_store_promotions_store_dates ON dbo.store_promotions (store_id, start_date, end_date);
GO
